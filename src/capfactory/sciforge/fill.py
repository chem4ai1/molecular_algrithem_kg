"""阶段 2：把原文 + 代码结构 + 当前节点交给 polo 做对齐填充。

与阶段 1 的区别：阶段 1 是「抽取」（只写论文里明确有的），阶段 2 是
**「对齐 + 补全」**，允许大模型基于对算法与算法能力的认知推断缺失字段，
但必须逐字段标 ``fill_source``：

| source | 含义 |
|---|---|
| ``extracted`` | 原文/代码里直接能读到 |
| ``inferred`` | 基于算法机制的合理推断（如 Benchmark 的输入输出契约） |
| ``code`` | 从代码结构（AST 签名）推出 |

**硬约束**：只能 patch 图上已存在的 node_id 与白名单字段，不许新建节点、
不许改主键、不许编造论文/引用。这是「填充」不是「再抽一遍」。
"""

from __future__ import annotations

import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Sequence

from ..po import POGraph
from ..utils import parse_llm_json
from ..ingest.pdf import split_sections
from ..ontology.modules import code_structure, _compact_structure
from .batch10 import MD_DIR, REPO_DIR, paper_text, missing_fields
from .polo import PoloClient

ALLOWED_FIELDS: Dict[str, Sequence[str]] = {
    "Benchmark": ("input_schema", "output_schema", "research_object",
                  "split_type", "split_ratio", "metric_ids", "problem_ids",
                  "task_family", "n_samples", "modality", "stage"),
    "Algorithm": ("architecture", "algo_codes", "paper_ids", "aliases",
                  "description", "granularity"),
    "AlgorithmStep": ("equation_ref", "code_symbols", "inputs", "outputs",
                      "parameters", "mechanism", "causal_role",
                      "input_schema", "output_schema", "grounding_status"),
    "MetricDefinition": ("value_type", "unit", "direction", "aggregation"),
    "CodeFunction": ("matched_step_ids", "docstring", "causal_role"),
}

FILL_PROMPT = """你在完善一张「论文-算法-数据-指标-代码」知识图谱。下面是某篇论文已经抽出的
节点（很多关键字段为空），以及该论文的原文片段和代码仓库的 AST 符号清单。

任务：为每个节点补齐**允许的字段**。

规则：
1. 只能 patch 下面给出的 node_id，不许新建节点；只能写在 allow_fields 里的字段。
2. 逐字段标 fill_source：
   - extracted：原文或代码里直接能读到；
   - inferred：原文没明说，但基于算法机制/算法能力的合理推断（例如
     「口袋条件 3D 分子生成」基准的输入是靶标口袋结构、输出是 3D 配体坐标）；
   - code：从 AST 签名/函数名推出。
3. **允许你基于自己对算法与算法能力的认知做代码设计与填充**，
   但 inferred/code 的内容必须标清来源，不能伪装成原文事实。
4. benchmark 的 metric_ids / problem_ids 用图上已有节点的 id；找不到就留空数组。
5. AlgorithmStep 的 code_symbols 只能从下面代码清单里选真实符号；
   若代码里确实没有对应实现，可以给出一个「建议函数名」并标 inferred，
   同时把 grounding_status 写 conceptual_gap。
6. 输出 <= 2500 token，严格 JSON。

输出格式：
{"patches":[{"node_id":"", "node_type":"", "attrs":{},
             "fill_source":{"field":"extracted|inferred|code"}}]}

## 待补节点（含当前值与允许字段）
{nodes}

## 论文原文片段
{paper}

## 代码符号清单
{code}

只输出 JSON。"""


def nodes_for_paper(graph: POGraph, aid: str) -> List[Dict[str, Any]]:
    """取该论文可达（≤2 跳）的待补节点；共享节点按论文分别填充。"""
    root = f"paper:{aid}"
    if root not in graph.nodes:
        return []
    reachable = {root}
    for _ in range(2):
        frontier = set()
        for a in graph.assertions:
            if a.source in reachable:
                frontier.add(a.target)
            if a.target in reachable:
                frontier.add(a.source)
        reachable |= frontier
    out = []
    for n in graph.nodes.values():
        if n.id not in reachable or n.type not in ALLOWED_FIELDS:
            continue
        a = n.attrs or {}
        allow = list(ALLOWED_FIELDS[n.type])
        missing = [f for f in allow if a.get(f) in (None, "", [], {})]
        if not missing:
            continue
        out.append({"node_id": n.id, "node_type": n.type,
                    "label": n.label[:60],
                    "current": {k: a.get(k) for k in allow if k in a},
                    "missing": missing, "allow_fields": allow})
    return out


def build_prompt_for_paper(graph: POGraph, aid: str) -> str:
    nodes = nodes_for_paper(graph, aid)
    if not nodes:
        return ""
    paper = paper_text(aid, max_chars=6000)
    # 找该论文的仓库
    struct = {"symbols": []}
    for r in graph.nodes.values():
        if r.type == "CodeRepository" and graph.nodes.get(f"paper:{aid}"):
            if any(a.source == f"paper:{aid}" and a.target == r.id
                   for a in graph.assertions):
                struct = code_structure(REPO_DIR / r.attrs.get("repo_name", ""),
                                        max_symbols=30)
                break
    return (FILL_PROMPT.replace("{nodes}", json.dumps(nodes[:18], ensure_ascii=False)[:7000])
                       .replace("{paper}", paper)
                       .replace("{code}", _compact_structure(struct, limit=25)))


def apply_patches(graph: POGraph, raw: Dict[str, Any], *, aid: str,
                  allowed_ids: set) -> Dict[str, Any]:
    """把 LLM 回填写进图；只接受白名单节点与字段，并留审计标记。"""
    st: Dict[str, Any] = {"patches": 0, "applied": 0, "fields": 0,
                          "rejected": [], "by_source": Counter()}
    for p in raw.get("patches") or []:
        if not isinstance(p, dict):
            continue
        st["patches"] += 1
        nid, ntype = p.get("node_id", ""), p.get("node_type", "")
        node = graph.nodes.get(nid)
        if node is None or nid not in allowed_ids or node.type != ntype:
            st["rejected"].append(f"非法节点 {nid}")
            continue
        src = p.get("fill_source") or {}
        for k, v in (p.get("attrs") or {}).items():
            if k not in ALLOWED_FIELDS.get(ntype, ()):
                st["rejected"].append(f"{nid}.{k} 不在白名单")
                continue
            if v in (None, "", [], {}):
                continue
            node.attrs[k] = v
            node.attrs.setdefault("filled_by", {})[k] = str(src.get(k) or "unspecified")
            st["fields"] += 1
            st["by_source"][str(src.get(k) or "unspecified")] += 1
        st["applied"] += 1
    st["by_source"] = dict(st["by_source"])
    return st


def fill_all(graph: POGraph, paper_ids: Sequence[str], cli: PoloClient,
             *, workers: int = 3) -> Dict[str, Any]:
    out: Dict[str, Any] = {"before": missing_fields(graph), "per_paper": [],
                           "total_fields": 0, "rejected": []}
    prompts = [(aid, build_prompt_for_paper(graph, aid),
                {n["node_id"] for n in nodes_for_paper(graph, aid)})
               for aid in paper_ids]
    prompts = [(a, p, s) for a, p, s in prompts if p]

    def one(t):
        aid, prompt, allowed = t
        raw = parse_llm_json(cli.chat(prompt, task=f"fill:{aid}",
                                      max_tokens=3000)) or {}
        return aid, raw, allowed

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for aid, raw, allowed in ex.map(one, prompts):
            st = apply_patches(graph, raw, aid=aid, allowed_ids=allowed)
            out["per_paper"].append({"arxiv_id": aid, **st})
            out["total_fields"] += st["fields"]
            out["rejected"].extend(st["rejected"][:3])
    out["after"] = missing_fields(graph)
    out["usage"] = cli.meter.summary()
    return out
