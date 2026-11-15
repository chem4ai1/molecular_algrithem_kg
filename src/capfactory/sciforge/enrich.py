"""三件「交给大模型对齐并填充」的任务（大上下文版）。

1. **基准归一**：把各篇私有的 Benchmark 名按「是不是同一个基准」分组，
   建共享节点，解决「跨论文共享 = 0」。
2. **问题层检查/补建**：确认 `ResearchQuestion` 与 `ProblemCategory` 已由
   重抽产出；给 Benchmark 填 `problem_ids`。
3. **证据锚定**：对 `filled_by` 里 `inferred` / `unspecified` 的字段，
   把全文（最多 128K 字符）交给大模型找支持句，建 `Evidence` 节点：
   找到 → 字段升级 `extracted`；找不到 → 标 `unsupported` + `needs_review`。

所有调用走 ``PoloClient`` 计量；输入预算默认 128K 字符，不做小截断。
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Sequence

from ..po import POGraph
from ..utils import parse_llm_json
from .polo import PoloClient

MAX_CHARS = 128000

BENCH_PROMPT = """下面是多篇论文各自报告的「基准/数据集/实验」名称与原文片段。
请把**实际是同一个基准**的名称归为一组，给出规范名。

规则：
- 只依据名称与原文片段；不同切分/子集如果底层数据相同，仍算同一基准；
- 无法确认与其它任何名称相同的，单独成组；
- 规范名用学界常用写法（如 GEOM-Drugs、ZINC-15、QM9）；
- 每组给一句 evidence 说明为什么合并/不合并。

输出严格 JSON：
{"groups":[{"canonical_name":"", "members":["原始名称"], "reason":"",
            "modality":"", "task_family":""}]}

## 基准清单
{items}

只输出 JSON。"""

EVIDENCE_PROMPT = """你在审计一张知识图谱里由大模型**推断填充**的字段。

对每个字段，判断下面的论文原文里是否有**直接支持句**：
- 有 → status="supported"，给 quote（原文连续片段，<=120 字符）与 section；
- 没有，但语义与论文明显一致（属于合理推断）→ status="inferred_ok"，quote 留空；
- 与论文矛盾或完全找不到依据 → status="unsupported"。

只输出严格 JSON：
{"checks":[{"node_id":"", "field":"", "status":"supported|inferred_ok|unsupported",
            "quote":"", "section":""}]}

## 待审字段
{fields}

## 论文原文（可能较长，请通读）
{paper}

只输出 JSON，不要解释。"""


def _n(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s or "").lower()).strip("_")[:48]


# ---------------------------------------------------------------------------
# ① 基准归一
# ---------------------------------------------------------------------------
def _rule_canonicalize(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """LLM 输出被截断时的确定性兜底：名字包含/前缀相同即同组。"""
    def key(n: str) -> str:
        return re.sub(r"[^a-z0-9]", "", str(n).lower())
    groups: List[Dict[str, Any]] = []
    used: set = set()
    names = [str(x["name"]) for x in items]
    for i, n in enumerate(names):
        if n in used:
            continue
        members = [n]
        used.add(n)
        k = key(n)
        for j, m in enumerate(names[i + 1:], i + 1):
            if m in used:
                continue
            km = key(m)
            if km and k and (km in k or k in km):
                members.append(m)
                used.add(m)
        groups.append({"canonical_name": n, "members": members,
                       "reason": "规则兜底：规范化名称互相包含（LLM 输出被截断）",
                       "modality": "", "task_family": ""})
    return groups


def canonicalize_benchmarks(graph: POGraph, cli: PoloClient, *,
                            md_dir: str | Path = "/home/zengshuxin/xKG-main/data/docx",
                            max_tokens: int = 4000) -> Dict[str, Any]:
    benches = graph.by_type("Benchmark")
    if not benches:
        return {"groups": 0, "shared_nodes": 0, "note": "no benchmarks"}
    items = []
    for b in benches:
        pid = str(b.attrs.get("paper_id") or "")
        aid = pid.split(":", 1)[-1] if pid else ""
        excerpt = ""
        if aid:
            f = Path(md_dir) / f"{aid}.md"
            if f.exists():
                text = f.read_text(encoding="utf-8", errors="replace")
                m = re.search(re.escape(b.label[:24]), text, re.I)
                excerpt = text[max(0, m.start() - 200): m.start() + 500] if m else ""
        items.append({"name": b.label, "excerpt": excerpt[:700],
                      "input_schema": b.attrs.get("input_schema", ""),
                      "output_schema": b.attrs.get("output_schema", "")})
    prompt = BENCH_PROMPT.replace("{items}",
                                  json.dumps(items, ensure_ascii=False)[:14000])
    groups: List[Dict[str, Any]] = []
    source = "llm"
    for attempt in range(2):
        out = cli.chat(prompt, task="canonicalize_benchmarks",
                       max_tokens=max_tokens)
        raw = parse_llm_json(out) or {}
        groups = [g for g in (raw.get("groups") or [])
                  if isinstance(g, dict) and g.get("canonical_name")]
        if groups:
            break
    if not groups:
        groups = _rule_canonicalize(items)
        source = "rule_fallback"
    name_to_id = {b.label: b.id for b in benches}
    shared = 0
    for i, g in enumerate(groups):
        canonical = str(g["canonical_name"])
        cid = f"benchmark:canonical:{_n(canonical)}"
        if cid not in graph.nodes:
            graph.node(cid, "Benchmark", canonical, name=canonical,
                       canonical_id=cid, modality=g.get("modality", ""),
                       task_family=g.get("task_family", ""),
                       aliases=g.get("members") or [],
                       normalization_reason=g.get("reason", ""),
                       provenance="llm_canonicalized")
        for m in g.get("members") or []:
            bid = name_to_id.get(m)
            if bid and bid != cid:
                graph.nodes[bid].attrs["canonical_id"] = cid
                graph.nodes[bid].attrs["canonical_name"] = canonical
                # 把原来指向私有 Benchmark 的 EVALUATED_ON 也指向共享节点
                for a in graph.assertions:
                    if a.target == bid and a.relation == "EVALUATED_ON":
                        graph.assert_rel(a.source, cid, "EVALUATED_ON")
        shared += 1
    # 统计跨论文共享
    papers = Counter()
    for a in graph.assertions:
        if a.relation == "EVALUATED_ON" and str(a.target).startswith("benchmark:canonical:"):
            papers[a.target] += 1
    return {"groups": len(groups), "shared_nodes": shared, "source": source,
            "shared_by_2plus_papers": sum(1 for v in papers.values() if v >= 2),
            "groups_detail": groups,
            "note": "共享节点解决跨论文零共享；旧私有节点保留 canonical_id 指针"}


# ---------------------------------------------------------------------------
# ② 问题层检查
# ---------------------------------------------------------------------------
def problem_layer_report(graph: POGraph) -> Dict[str, Any]:
    qs = graph.by_type("ResearchQuestion")
    pcs = graph.by_type("ProblemCategory")
    benches = graph.by_type("Benchmark")
    filled = sum(1 for b in benches if b.attrs.get("problem_ids"))
    return {"research_questions": len(qs), "problem_categories": len(pcs),
            "benchmarks_with_problem_ids": filled,
            "benchmarks_total": len(benches),
            "questions_with_category": sum(
                1 for a in graph.assertions if a.relation == "BROADER"
                and a.source in {q.id for q in qs})}


# ---------------------------------------------------------------------------
# ③ 证据锚定
# ---------------------------------------------------------------------------
def _inferred_fields(graph: POGraph, aid: str) -> List[Dict[str, Any]]:
    root = f"paper:{aid}"
    reachable = {root}
    for _ in range(2):
        fr = set()
        for a in graph.assertions:
            if a.source in reachable:
                fr.add(a.target)
            if a.target in reachable:
                fr.add(a.source)
        reachable |= fr
    out = []
    for n in graph.nodes.values():
        if n.id not in reachable:
            continue
        filled = n.attrs.get("filled_by") or {}
        for field, src in filled.items():
            if src in ("inferred", "unspecified", "code"):
                out.append({"node_id": n.id, "field": field,
                            "value": str(n.attrs.get(field))[:120],
                            "fill_source": src})
        if len(out) >= 24:
            break
    return out


def anchor_evidence(graph: POGraph, cli: PoloClient, *,
                    md_dir: str | Path = "/home/zengshuxin/xKG-main/data/docx",
                    max_chars: int = MAX_CHARS, max_tokens: int = 6000,
                    workers: int = 3) -> Dict[str, Any]:
    papers = [n.attrs.get("arxiv_id") for n in graph.by_type("Paper")]
    papers = [x for x in papers if x]
    jobs = []
    for aid in papers:
        fields = _inferred_fields(graph, aid)
        f = Path(md_dir) / f"{aid}.md"
        if not fields or not f.exists():
            continue
        text = f.read_text(encoding="utf-8", errors="replace")[:max_chars]
        jobs.append((aid, fields, text))

    def one(job):
        aid, fields, text = job
        prompt = (EVIDENCE_PROMPT
                  .replace("{fields}", json.dumps(fields, ensure_ascii=False)[:6000])
                  .replace("{paper}", text))
        raw = parse_llm_json(cli.chat(prompt, task=f"evidence:{aid}",
                                      max_tokens=max_tokens)) or {}
        return aid, fields, raw.get("checks") or []

    st: Dict[str, Any] = {"papers": len(jobs), "fields_checked": 0,
                          "supported": 0, "inferred_ok": 0, "unsupported": 0,
                          "evidence_nodes": 0, "by_paper": []}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for aid, fields, checks in ex.map(one, jobs):
            by_key = {(c.get("node_id"), c.get("field")): c
                      for c in checks if isinstance(c, dict)}
            n_ok = 0
            for fld in fields:
                key = (fld["node_id"], fld["field"])
                c = by_key.get(key) or {}
                status = c.get("status") or "unreviewed"
                st["fields_checked"] += 1
                if status in st:
                    st[status] += 1
                node = graph.nodes.get(fld["node_id"])
                if node is None:
                    continue
                filled = node.attrs.setdefault("filled_by", {})
                if status == "supported" and c.get("quote"):
                    filled[fld["field"]] = "extracted"
                    eid = f"evidence:{aid}:{_n(fld['node_id'])}:{_n(fld['field'])}"
                    if eid not in graph.nodes:
                        graph.node(eid, "Evidence", c["quote"][:80],
                                   quote=c["quote"][:300],
                                   section=c.get("section", ""),
                                   paper_id=f"paper:{aid}",
                                   extraction_method="llm_grounded")
                        st["evidence_nodes"] += 1
                    graph.assert_rel(fld["node_id"], eid, "SUPPORTED_BY")
                    n_ok += 1
                elif status == "unsupported":
                    node.attrs.setdefault("needs_review", []).append(fld["field"])
            st["by_paper"].append({"arxiv_id": aid, "fields": len(fields),
                                   "upgraded": n_ok})
    return st
