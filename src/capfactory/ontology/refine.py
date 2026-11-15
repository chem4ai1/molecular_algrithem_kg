"""V2 试点的 7 个优化点中 ②③④⑤⑥⑦ 的确定性修正。

对应 ``docs/V2_PILOT_EGNN.md`` §2。①（论文组件名≠代码实现名）
已由 ``modules.py`` 的模块级抽取 + grounding 解决，这里只复用其结论。

设计原则：**能算出来的不让 LLM 填**。

| # | 问题 | 修正 |
|---|---|---|
| ② | DataForm 大量 mixed | ``derive_forms`` 从 schema 文本派生，多标签 |
| ③ | 基线混进 algorithms | ``split_methods`` 分 proposed/baseline，基线不进 PROPOSES_METHOD |
| ④ | 指标/基准只抽 1/1 | ``extract_experiments`` 按 Results 小节逐节抽 |
| ⑤ | linked=0 被误读 | ``sample_overlap`` 显式标注 + 预置 Paper |
| ⑥ | 第三方仓库 | ``provenance_of`` 记 is_original_repo |
| ⑦ | 图稀疏 | ``derive_edges`` 补族/共现边 + ``graph_quality`` 孤立率 |
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..po import POGraph
from ..po.concepts import Concept
from ..utils import parse_llm_json
from .layers import DATA_FORMS, ALGORITHM_ROLES
from .model import V2_CLASSES

# ---------------------------------------------------------------------------
# ② DataForm：从 schema 派生，不让 LLM 直接选
# ---------------------------------------------------------------------------
FORM_RULES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("3d_coordinates", ("coord", "coors", "position", "x_i", "x_j",
                        "3d", "geometry", "conformer", "pocket")),
    ("embedding", ("embedding", "embed", "hidden", "h_i", "h_j",
                   "node_feat", "latent", "feature vector")),
    ("2d_graph", ("graph", "edge", "adj", "adjacency", "node", "bond")),
    ("1d_sequence", ("sequence", "smiles", "amino", "peptide seq", "string")),
    ("scalar", ("scalar", "score", "energy", "loss", "mae", "mse",
                "rmsd", "value", "probability")),
    ("distribution", ("distribution", "histogram", "density", "sample")),
    ("text", ("text", "caption", "description", "prompt")),
    ("image", ("image", "figure", "pixel", "render")),
    ("table", ("table", "column", "row", "csv")),
)


def derive_forms(schema: str, *, fallback: str = "") -> List[str]:
    """从 schema 文本派生 DataForm（多标签）。

    例：``"node_embeddings, coordinates, edge_info"``
    → ``["embedding", "3d_coordinates", "2d_graph"]``。

    只有当 schema 完全无信号时才回退到 LLM 给的 ``fallback``；
    ``mixed`` 永远不作为派生结果（它是「偷懒值」，不是真实形式）。
    """
    low = str(schema or "").lower()
    hits = [form for form, keys in FORM_RULES if any(k in low for k in keys)]
    if hits:
        return hits
    if fallback and fallback in DATA_FORMS and fallback != "mixed":
        return [fallback]
    return ["mixed"]


def refine_forms_in_graph(graph: POGraph) -> Dict[str, Any]:
    """把图里所有 Step/Application 的 mixed 输入/输出按 schema 重算。"""
    stats: Dict[str, Any] = {"checked": 0, "refined": 0, "examples": []}

    def _forms(node: Concept, prefix: str) -> None:
        schema = node.attrs.get(f"{prefix}_schema")
        current = node.attrs.get(f"{prefix}_form") or ""
        if not schema:
            return
        stats["checked"] += 1
        derived = derive_forms(str(schema), fallback=str(current))
        if derived != [current] and "mixed" in (str(current),):
            node.attrs[f"{prefix}_form"] = derived[0]
            node.attrs[f"{prefix}_forms"] = derived
            stats["refined"] += 1
            if len(stats["examples"]) < 5:
                stats["examples"].append({"node": node.label[:30],
                                          "schema": str(schema)[:60],
                                          "forms": derived})
        else:
            node.attrs.setdefault(f"{prefix}_forms", derived)

    for n in graph.nodes.values():
        if n.type in ("AlgorithmStep", "MethodApplication"):
            _forms(n, "input")
            _forms(n, "output")
        if n.type == "DataForm":
            schema = n.attrs.get("schema")
            current = n.attrs.get("form") or ""
            if not schema:
                continue
            stats["checked"] += 1
            derived = derive_forms(str(schema), fallback=str(current))
            if "mixed" == current or current not in derived:
                n.attrs["form"] = derived[0]
                n.attrs["forms"] = derived
                stats["refined"] += 1
                if len(stats["examples"]) < 5:
                    stats["examples"].append({"node": n.label[:30],
                                              "schema": str(schema)[:60],
                                              "forms": derived})
    return stats


# ---------------------------------------------------------------------------
# ③ 基线分离
# ---------------------------------------------------------------------------
def split_methods(raw: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """把 LLM 输出的方法列表分成「本文方法」与「基线」两栏。

    兼容三种格式：

    * 新格式：``{"proposed_methods":[...], "baselines":[...]}``
    * 旧格式：``{"algorithms":[{name, kind}, ...]}``
    * 组合格式：``composition.steps`` 里 ``role=baseline``
    """
    proposed = list(raw.get("proposed_methods") or [])
    baselines = list(raw.get("baselines") or [])
    seen = {str(x.get("name", "")).lower() for x in proposed + baselines}
    for a in raw.get("algorithms") or []:
        if not isinstance(a, dict) or not a.get("name"):
            continue
        name = str(a["name"])
        if name.lower() in seen:
            continue
        if a.get("kind") == "baseline" or a.get("granularity") == "baseline":
            baselines.append({**a, "kind": "baseline", "is_baseline": True})
        else:
            proposed.append({**a, "kind": a.get("kind") or "method",
                             "is_baseline": False})
        seen.add(name.lower())
    for s in ((raw.get("composition") or {}).get("steps") or []):
        if isinstance(s, dict) and s.get("role") == "baseline":
            nm = str(s.get("algorithm") or "")
            if nm and nm.lower() not in {str(b.get("name", "")).lower()
                                         for b in baselines}:
                baselines.append({"name": nm, "kind": "baseline",
                                  "is_baseline": True})
    return {"proposed": proposed, "baselines": baselines}


def refine_baselines_in_graph(graph: POGraph,
                              raw: Dict[str, Any]) -> Dict[str, Any]:
    """给基线节点标 is_baseline，并删掉误建的 PROPOSES_METHOD 边。"""
    groups = split_methods(raw)
    base_names = {str(b.get("name", "")).lower() for b in groups["baselines"]}
    stats: Dict[str, Any] = {"proposed": len(groups["proposed"]),
                             "baselines": len(groups["baselines"]),
                             "relabeled": 0, "edges_removed": 0}
    paper_ids = [n.id for n in graph.nodes.values() if n.type == "Paper"]
    for n in graph.nodes.values():
        if n.type != "Algorithm":
            continue
        if n.label.lower() in base_names:
            n.attrs["kind"] = "baseline"
            n.attrs["is_baseline"] = True
            stats["relabeled"] += 1
    keep = []
    for a in graph.assertions:
        if (a.relation == "PROPOSES_METHOD" and a.source in paper_ids
                and graph.nodes.get(a.target)
                and graph.nodes[a.target].attrs.get("is_baseline")):
            stats["edges_removed"] += 1
            continue
        keep.append(a)
    graph.assertions[:] = keep
    return stats


# ---------------------------------------------------------------------------
# ④ 按 Results 小节逐节抽指标/基准
# ---------------------------------------------------------------------------
EXPERIMENT_PROMPT = """从下面这一节实验结果里抽取评测信息。只依据文本。

输出严格 JSON：
{
  "experiment": "本节实验名",
  "benchmarks": [{"name":"", "input_schema":"", "output_schema":"", "research_object":""}],
  "metrics": [{"name":"", "direction":"higher|lower|context_dependent", "unit":""}],
  "values": [{"metric":"", "value":0.0, "unit":"", "subject":"方法名"}]
}
指标名必须是论文里出现的名字；没有数值就留空 values。输出 <= 800 token。

## 本节
{text}
"""


def extract_experiments(sections: Dict[str, str], *, chat_fn: Any,
                        section_keywords: Sequence[str] = ("experiment", "result",
                                                           "evaluation", "5."),
                        limit: int = 6) -> Dict[str, Any]:
    """逐节抽指标/基准，再汇总去重（修掉「全文一次抽取只给 1/1」）。"""
    picked = [(k, v) for k, v in sections.items()
              if any(x in k.lower() for x in section_keywords)][:limit]
    out: Dict[str, Any] = {"sections": [], "metrics": [], "benchmarks": [],
                           "values": [], "n_calls": 0}
    seen_m, seen_b = set(), set()
    for name, body in picked:
        prompt = EXPERIMENT_PROMPT.replace("{text}", (name + "\n" + body)[:6000])
        raw = parse_llm_json(chat_fn(prompt)) or {}
        out["n_calls"] += 1
        out["sections"].append({"name": name,
                                "metrics": len(raw.get("metrics") or []),
                                "benchmarks": len(raw.get("benchmarks") or [])})
        for m in raw.get("metrics") or []:
            key = str(m.get("name", "")).lower()
            if key and key not in seen_m:
                seen_m.add(key)
                out["metrics"].append({**m, "source_section": name})
        for b in raw.get("benchmarks") or []:
            key = str(b.get("name", "")).lower()
            if key and key not in seen_b:
                seen_b.add(key)
                out["benchmarks"].append({**b, "source_section": name})
        for v in raw.get("values") or []:
            out["values"].append({**v, "source_section": name})
    return out


# ---------------------------------------------------------------------------
# ⑤ 样本重叠判定 + 预置 Paper
# ---------------------------------------------------------------------------
def sample_overlap(base: POGraph, doc_id: str) -> Dict[str, Any]:
    """判断目标论文是否本就在基线图里；给 linked=0 一个可解释原因。"""
    arxiv = {str(n.attrs.get("arxiv_id") or ""): n.id
             for n in base.by_type("Paper") if n.attrs.get("arxiv_id")}
    doi = {str(n.attrs.get("doi") or ""): n.id
           for n in base.by_type("Paper") if n.attrs.get("doi")}
    direct = arxiv.get(doc_id) or doi.get(doc_id)
    m = re.match(r"(\d{4})\.\d{4,5}", str(doc_id or ""))
    year = 2000 + int(m.group(1)[:2]) if m else 0
    years = [int(n.attrs["year"]) for n in base.by_type("Paper")
             if str(n.attrs.get("year") or "").isdigit()]
    same_era = bool(year and years and
                    abs(year - sum(years) / len(years)) <= 3)
    return {"in_base": bool(direct), "paper_id": direct or "",
            "base_papers": len(base.by_type("Paper")),
            "base_mean_year": round(sum(years) / len(years), 1) if years else None,
            "target_year": year or None, "same_era": same_era,
            "reason": ("同论文已在基线图中" if direct else
                       "样本与基线图不重叠：linked=0 不代表链接器失效"),
            "note": "链接前应预置 Paper 节点，避免把身份缺失误判为算法失败"}


def ensure_paper(graph: POGraph, doc_id: str, *, title: str = "") -> str:
    """链接前预置 Paper 节点（doc_id 是已知的，不该让 LLM 抽）。"""
    for n in graph.by_type("Paper"):
        if n.attrs.get("arxiv_id") == doc_id or n.id.endswith(doc_id):
            return n.id
    pid = f"paper:{doc_id}"
    graph.node(pid, "Paper", title or doc_id, title=title or doc_id,
               arxiv_id=doc_id, domain_codes=[], versions=[])
    return pid


# ---------------------------------------------------------------------------
# ⑥ 仓库 provenance
# ---------------------------------------------------------------------------
def provenance_of(actual_repo: str, declared_repo: str) -> Dict[str, Any]:
    """标注代码仓库是否为论文声明的原仓库。"""
    def norm(s: str) -> str:
        s = str(s or "").lower()
        s = re.sub(r"https?://(www\.)?(github\.com|gitlab\.com)/", "", s)
        s = re.sub(r"[^a-z0-9/_-]", "", s)
        return s.strip("/")
    a, d = norm(actual_repo), norm(declared_repo)
    is_original = bool(d) and (a == d or a.endswith(d) or d.endswith(a))
    return {"actual_repo": actual_repo, "declared_repo": declared_repo,
            "is_original_repo": is_original,
            "repo_provenance": ("paper_declared" if is_original else
                               "third_party_implementation"),
            "trust": "high" if is_original else "needs_verification"}


def annotate_repository(graph: POGraph, *, actual_repo: str,
                        declared_repo: str = "") -> Dict[str, Any]:
    prov = provenance_of(actual_repo, declared_repo)
    for n in graph.nodes.values():
        if n.type == "CodeRepository":
            n.attrs.update(prov)
    return prov


# ---------------------------------------------------------------------------
# ⑦ 派生边 + 图质量
# ---------------------------------------------------------------------------
def derive_edges(graph: POGraph) -> Dict[str, Any]:
    """给孤立算法补 USES_ALGO_FAMILY 与共现边。"""
    from ..po.taxonomy import classify
    fams = {n.attrs.get("code"): n.id for n in graph.nodes.values()
            if n.type == "AlgorithmFamily"}
    algs = [n for n in graph.nodes.values() if n.type == "Algorithm"]
    stats: Dict[str, Any] = {"algorithms": len(algs), "family_edges": 0,
                             "cooccur_edges": 0, "families_created": 0}
    for a in algs:
        if a.attrs.get("is_baseline"):
            continue
        codes = classify(f"{a.label} {a.attrs.get('architecture','')}", "algo",
                         limit=2)
        for c in codes:
            if c not in fams:
                fid = f"algorithmfamily:{c}"
                graph.node(fid, "AlgorithmFamily", c, code=c, label=c)
                fams[c] = fid
                stats["families_created"] += 1
            if graph.assert_rel(a.id, fams[c], "USES_ALGO_FAMILY"):
                stats["family_edges"] += 1
    # 同一 Composition 下的算法互为共现（弱关联，用于降低孤立率）
    comp_steps: Dict[str, List[str]] = {}
    for n in graph.nodes.values():
        if n.type == "AlgorithmStep":
            comp_steps.setdefault(n.attrs.get("composition_id", ""), []).append(
                n.attrs.get("algorithm_id", ""))
    for _cid, aids in comp_steps.items():
        uniq = [x for x in dict.fromkeys(aids) if x in graph.nodes]
        for i, a in enumerate(uniq):
            for b in uniq[i + 1:]:
                if graph.assert_rel(a, b, "CO_OCCURS_WITH"):
                    stats["cooccur_edges"] += 1
    return stats


def graph_quality(graph: POGraph) -> Dict[str, Any]:
    """图质量指标：孤立率、边/节点比、类分布。"""
    deg: Counter = Counter()
    for a in graph.assertions:
        deg[a.source] += 1
        deg[a.target] += 1
    n = len(graph.nodes)
    isolated = [x.id for x in graph.nodes.values() if deg[x.id] == 0]
    return {"nodes": n, "edges": len(graph.assertions),
            "edge_node_ratio": round(len(graph.assertions) / max(n, 1), 2),
            "isolated": len(isolated),
            "isolated_rate": round(len(isolated) / max(n, 1), 3),
            "isolated_samples": isolated[:6],
            "by_class": dict(Counter(x.type for x in graph.nodes.values()))}


# ---------------------------------------------------------------------------
# 一站式
# ---------------------------------------------------------------------------
def refine_all(graph: POGraph, raw: Dict[str, Any], *, base: POGraph,
               doc_id: str, actual_repo: str = "",
               declared_repo: str = "") -> Dict[str, Any]:
    return {
        "sample_overlap": sample_overlap(base, doc_id),
        "forms": refine_forms_in_graph(graph),
        "baselines": refine_baselines_in_graph(graph, raw),
        "provenance": annotate_repository(graph, actual_repo=actual_repo,
                                          declared_repo=declared_repo),
        "edges": derive_edges(graph),
        "quality_before": {},
    }


# ---------------------------------------------------------------------------
# ⑦-b 收敛：删未被模块引用的 CodeFunction + 给基线补弱关联边
# ---------------------------------------------------------------------------
CODE_BINDING_RELS = ("IMPLEMENTS_MODULE", "REALIZES", "IMPLEMENTS_METRIC",
                     "IMPLEMENTS_ALGORITHM", "CALLS", "FLOWS_DATA_TO")


def prune_unreferenced_code(graph: POGraph) -> Dict[str, Any]:
    """按 ① 的方向收敛：只保留被模块/指标/其他符号引用的代码函数。

    ``bind_code`` 早期版本把仓库里**所有**函数都建了节点，造成大量悬空项；
    新链路（``modules.build_module_graph``）只建被 ``code_symbols`` 引用的符号。
    这里提供事后清理，让旧图也能收敛到同一形态。
    """
    # 绑定边上**代码符号是 source**（CodeFunction -IMPLEMENTS_MODULE-> Step），
    # 收 target 会把所有函数误判为未引用。
    bound: set = set()
    for a in graph.assertions:
        if a.relation in CODE_BINDING_RELS:
            bound.add(a.source)
        if a.relation in ("CALLS", "FLOWS_DATA_TO"):
            bound.add(a.source)
            bound.add(a.target)
    drop = {n.id for n in graph.nodes.values()
            if n.type == "CodeFunction" and n.id not in bound}
    out: Dict[str, Any] = {"code_functions": len([n for n in graph.nodes.values()
                                                   if n.type == "CodeFunction"]),
                           "removed": len(drop), "samples": sorted(drop)[:5]}
    if drop:
        for i in list(drop):
            graph.nodes.pop(i, None)
        graph.assertions[:] = [a for a in graph.assertions
                              if a.source not in drop and a.target not in drop]
    return out


def attach_baselines(graph: POGraph) -> Dict[str, Any]:
    """给 baseline 算法补 ``RELATED_TO`` 弱关联，消除孤立节点但不冒充本文方法。"""
    papers = [n.id for n in graph.nodes.values() if n.type == "Paper"]
    out: Dict[str, Any] = {"baselines": 0, "edges_added": 0}
    if not papers:
        return out
    pid = papers[0]
    for n in graph.nodes.values():
        if n.type == "Algorithm" and n.attrs.get("is_baseline"):
            out["baselines"] += 1
            if graph.assert_rel(pid, n.id, "RELATED_TO",
                                attribution="analyst_synthesis"):
                out["edges_added"] += 1
    return out
