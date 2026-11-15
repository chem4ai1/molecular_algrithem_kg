"""R0–R4 装配：从 POGraph 的节点属性 + 关系链生成 ReproPlan（不调 LLM、不编造）。

P0-1 变更（关系名统一，见 capfactory/reprospec/relations.py）：
  * 关系比较统一走 ``resolve_relation()``，历史别名可识别但**输出仍保留原关系名**
    （不改变既有 plan 结构，确保 879 项回归不退化）
  * ``relation_index.json`` 的派生链通过 ``RELATION_INDEX_CHAINS`` **显式声明**，
    不再让 chain 名与 TBox 关系名混用
  * Paper 属性读取加规范名 fallback（research_question / flow_family），
    旧字段名优先，保证行为兼容

注意：本模块只生成 ReproPlan（执行计划）。可验证规格 ReproSpec/SAU 由
``capfactory.reprospec.compile_reprospec`` 编译，两者职责不同、不互相替代。
"""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any, Dict, List, Optional

from capfactory.reprospec.relations import (RELATION_INDEX_CHAINS,
                                            resolve_relation)

from .contract import ReproPlan

REL_INDEX = Path("storage_cf/sciforge/relation_index.json")


def _rel_chain(node_id: str, chain: str) -> List[Dict[str, str]]:
    """读 relation_index.json 的**预计算多跳链**（不是 TBox 关系）。

    chain 必须在 RELATION_INDEX_CHAINS 显式登记；未登记的链名一律返回空，
    避免把派生链误当成图上关系写进 plan。
    """
    if chain not in RELATION_INDEX_CHAINS or not REL_INDEX.exists():
        return []
    try:
        idx = json.loads(REL_INDEX.read_text(encoding="utf-8"))
        return [{"target_id": x["target_id"],
                 "target_label": x["target_label"],
                 "relation": x["relation"]}
                for x in (idx.get(node_id, {}).get(chain) or [])[:20]]
    except Exception:  # noqa: BLE001
        return []


def _read_attr(attrs: Dict[str, Any], *names: str) -> str:
    """按优先级读属性；便于旧字段名 → 语义层 v4 规范名平滑过渡。"""
    for k in names:
        v = attrs.get(k)
        if v not in (None, ""):
            return str(v)
    return ""


def _sha(parts: List[Any]) -> str:
    blob = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def build_plan(graph: Any, paper_id: str) -> ReproPlan:
    p = graph.nodes.get(paper_id)
    if not p or p.type != "Paper":
        return ReproPlan(paper_id=paper_id, arxiv_id=paper_id.split(":")[-1],
                         gaps=[{"phase": "R0", "reason": "paper_not_found"}])
    a = p.attrs
    plan = ReproPlan(
        paper_id=paper_id,
        arxiv_id=str(a.get("arxiv_id") or paper_id.split(":")[-1]),
        research_problem=_read_attr(a, "research_problem", "research_question"),
        domain=_read_attr(a, "domain"),
        algorithm_family=_read_attr(a, "algorithm_family", "flow_family"))
    out = graph.outgoing(paper_id)
    # R1：论文 → 算法（关系名先规范化再比较）
    for x in out:
        if resolve_relation(x.relation) not in ("PROPOSES_METHOD", "RELATED_TO") or \
                x.target not in graph.nodes:
            continue
        n = graph.nodes[x.target]
        if n.type != "Algorithm":
            continue
        na = n.attrs
        plan.methods.append({
            "id": n.id, "name": n.label,
            "task_type": na.get("task_type"),
            "task_type_label": na.get("task_type_label"),
            "problems_solved": na.get("problems_solved") or [],
            "mechanism": na.get("mechanism"),
            "why_it_works": na.get("why_it_works"),
            "family": na.get("schema_family"),
            "relation": x.relation})   # 保留原始关系名，不改变既有输出
    # R2：算法 → 代码（relation_index 派生链，显式登记）
    for m in plan.methods:
        for c in _rel_chain(m["id"], "algorithm_code"):
            plan.code.append({"algorithm": m["name"], **c})
    for x in out:
        if resolve_relation(x.relation) == "HAS_CODE" and x.target in graph.nodes:
            plan.code.append({"algorithm": "(paper-level)",
                              "target_id": x.target,
                              "target_label": graph.nodes[x.target].label,
                              "relation": x.relation})
    # R3：论文 → 数据
    for x in out:
        if resolve_relation(x.relation) != "EVALUATED_ON" or x.target not in graph.nodes:
            continue
        n = graph.nodes[x.target]
        if n.type != "Benchmark":
            continue
        na = n.attrs
        plan.data.append({
            "id": n.id, "name": n.label,
            "input_form": na.get("input_form"),
            "output_form": na.get("output_form"),
            "n_samples": na.get("n_samples"),
            "scale": na.get("scale"),
            "is_evaluation": na.get("is_evaluation", True),
            "source_papers": [z["target_label"]
                              for z in _rel_chain(n.id, "data_paper")],
            "relation": x.relation})
        # R4：指标与 SOTA 基线
        for mt in (na.get("metrics") or []):
            plan.metrics.append({
                "benchmark": n.label, "name": mt.get("name"),
                "unit": mt.get("unit"),
                "direction": mt.get("direction"),
                "direction_source": mt.get("direction_source"),
                "sota_model": mt.get("sota_model"),
                "sota_value": mt.get("sota_value"),
                "ties": mt.get("ties") or []})
        sota = na.get("sota_by_metric") or {}
        for k, v in sota.items():
            plan.sota_baselines[f"{n.label}:{k}"] = v
    plan.chains = {
        "paper_algorithm": _rel_chain(paper_id, "paper_algorithm"),
        "paper_data": _rel_chain(paper_id, "paper_data"),
        "paper_paper": _rel_chain(paper_id, "paper_paper"),
        "paper_code": _rel_chain(paper_id, "paper_code")}
    # gaps：只报告缺失，不编造
    if not plan.research_problem or plan.research_problem.startswith("unknown"):
        plan.gaps.append({"phase": "R0", "reason": "no_research_problem"})
    if not plan.methods:
        plan.gaps.append({"phase": "R1", "reason": "no_method_relation"})
    if not plan.code:
        plan.gaps.append({"phase": "R2", "reason": "no_code_relation"})
    if not plan.data:
        plan.gaps.append({"phase": "R3", "reason": "no_benchmark_relation"})
    if not plan.metrics:
        plan.gaps.append({"phase": "R4", "reason": "no_metrics"})
    for m in plan.metrics:
        if m["direction_source"] == "heuristic":
            plan.warnings.append(
                f"metric {m['name']} 方向为启发式，需人工确认")
    plan.inputs_sha = _sha([plan.methods, plan.code, plan.data,
                            plan.metrics, plan.sota_baselines])
    return plan
