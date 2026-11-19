"""抽取就绪度审计：判断每篇论文的字段是否足以支撑 P0–P11 推理。

声明式：阶段需求来自 data/extract_target/readiness.yaml。
输出 READY / PARTIAL / BLOCKED，并为 BLOCKED 给出补抽建议。
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List

READINESS_YAML = Path("data/extract_target/readiness.yaml")


def _load_spec() -> Dict[str, Any]:
    try:
        import yaml
        return (yaml.safe_load(READINESS_YAML.read_text(encoding="utf-8")) or {}).get("phases") or {}
    except Exception:  # noqa: BLE001
        return {}


def _ok(v: Any) -> bool:
    return v not in (None, "", [], {})


def audit_paper(attrs: Dict[str, Any], phases: Dict[str, Any] | None = None
                ) -> Dict[str, Any]:
    """单篇审计：返回 {phase: {status, missing, refine}}。"""
    phases = phases if phases is not None else _load_spec()
    out: Dict[str, Any] = {}
    for ph, spec in phases.items():
        missing: List[str] = []
        for f in spec.get("critical") or []:
            if not _ok(attrs.get(f)):
                missing.append(f)
        any_groups = spec.get("any_of") or []
        if any_groups:
            if not any(all(_ok(attrs.get(f)) for f in grp) for grp in any_groups):
                missing.append(" | ".join("+".join(g) for g in any_groups))
        if not missing:
            status = "READY"
        elif len(missing) < len(spec.get("critical") or []) + len(any_groups):
            status = "PARTIAL"
        else:
            status = "BLOCKED"
        out[ph] = {"status": status, "missing": missing,
                   "refine": spec.get("补抽") if missing else None}
    return out


# 这些需求项在 Algorithm 节点上（不在 Paper）
ALGO_LEVEL = {"arch_modules", "key_challenge", "why_not_other",
              "hyperparams", "ablation_hyperparams", "modules"}


def effective_attrs(graph, paper) -> Dict[str, Any]:
    """Paper 属性 + 关联 Algorithm 的算法级字段（合并成审计用视图）。"""
    eff = dict(paper.attrs)
    merged = {}
    for a in graph.outgoing(paper.id):
        if a.relation != "PROPOSES_METHOD" or a.target not in graph.nodes:
            continue
        for k in ALGO_LEVEL:
            v = graph.nodes[a.target].attrs.get(k)
            if v not in (None, "", [], {}):
                merged.setdefault(k, v)
    eff.update(merged)
    return eff


def audit_graph(graph, *, phases: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """全库审计：返回逐篇结果 + 各阶段统计 + 待补抽清单。"""
    phases = phases if phases is not None else _load_spec()
    per_paper = {}
    stats: Dict[str, Dict[str, int]] = {ph: {"READY": 0, "PARTIAL": 0, "BLOCKED": 0}
                                        for ph in phases}
    by_field: Dict[str, int] = {}
    pending: Dict[str, List[str]] = {}
    for p in graph.by_type("Paper"):
        aid = p.attrs.get("arxiv_id") or p.id.split(":")[-1]
        r = audit_paper(effective_attrs(graph, p), phases)
        per_paper[aid] = r
        for ph, v in r.items():
            stats[ph][v["status"]] += 1
            if v["status"] != "READY":
                for m in v["missing"]:
                    by_field[m] = by_field.get(m, 0) + 1
                if v.get("refine"):
                    pending.setdefault(v["refine"], []).append(aid)
    return {"n_papers": len(per_paper), "stats": stats,
            "missing_by_requirement": by_field,
            "pending_refine": {k: sorted(set(v)) for k, v in pending.items()},
            "per_paper": per_paper}
