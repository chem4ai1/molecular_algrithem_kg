"""抽取就绪度审计：判断每篇论文的字段是否足以支撑 P0–P11 推理。

声明式：阶段需求与 NA 规则来自 data/extract_target/readiness.yaml。
状态：READY / READY_NA / PARTIAL / BLOCKED。
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List

READINESS_YAML = Path("data/extract_target/readiness.yaml")


def _load_spec() -> Dict[str, Any]:
    try:
        import yaml
        d = yaml.safe_load(READINESS_YAML.read_text(encoding="utf-8")) or {}
        return {"phases": d.get("phases") or {}, "na_rules": d.get("na_rules") or {}}
    except Exception:  # noqa: BLE001
        return {"phases": {}, "na_rules": {}}


def _ok(v: Any) -> bool:
    return v not in (None, "", [], {})


def _condition_hit(attrs: Dict[str, Any], c: Dict[str, Any]) -> bool:
    field = c.get("field")
    val = attrs.get(field)
    if "in" in c:
        return str(val or "").lower() in [str(x).lower() for x in (c.get("in") or [])]
    if "contains_any" in c:
        text = str(val or "").lower()
        return any(str(x).lower() in text for x in (c.get("contains_any") or []))
    return False


def _is_na(field_or_group: str, attrs: Dict[str, Any], na_rules: Dict[str, Any]) -> bool:
    """判断某个需求项是否不适用；any_of 组用 ' | ' 连接。"""
    fields = [x.strip() for x in field_or_group.split("|")]
    rules = na_rules.get(field_or_group) or {}
    if not rules:
        rules = {"any": []}
        for f in fields:
            rules["any"].extend(na_rules.get(f, {}).get("any", []))
    if not rules:
        return False
    if "any" in rules:
        return any(_condition_hit(attrs, c) for c in (rules.get("any") or []))
    if "all" in rules:
        return all(_condition_hit(attrs, c) for c in (rules.get("all") or []))
    return False


def audit_paper(attrs: Dict[str, Any], spec: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """单篇审计：返回 {phase: {status, missing, na, refine}}。"""
    if spec is None:
        spec = _load_spec()
    phases = spec.get("phases") or {}
    na_rules = spec.get("na_rules") or {}
    out: Dict[str, Any] = {}
    for ph, ps in phases.items():
        missing: List[str] = []
        na: List[str] = []
        for f in ps.get("critical") or []:
            if _ok(attrs.get(f)):
                continue
            if _is_na(f, attrs, na_rules):
                na.append(f)
            else:
                missing.append(f)
        any_groups = ps.get("any_of") or []
        if any_groups:
            satisfied = any(all(_ok(attrs.get(f)) for f in grp) for grp in any_groups)
            if not satisfied:
                reprs = [" | ".join("+".join(g) for g in any_groups)]
                for grp_repr, grp in zip(reprs, any_groups):
                    if all(_is_na(f, attrs, na_rules) for f in grp):
                        na.append(grp_repr)
                    else:
                        missing.append(grp_repr)
        if missing:
            has_critical_block = any(m in (ps.get("critical") or []) for m in missing)
            status = "BLOCKED" if has_critical_block else "PARTIAL"
        elif na:
            status = "READY_NA"
        else:
            status = "READY"
        out[ph] = {"status": status, "missing": missing, "na": na,
                   "refine": ps.get("补抽") if missing else None}
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


def audit_graph(graph, *, spec: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """全库审计：返回逐篇结果 + 各阶段统计 + 待补抽清单。"""
    if spec is None:
        spec = _load_spec()
    phases = spec.get("phases") or {}
    per_paper = {}
    stats: Dict[str, Dict[str, int]] = {
        ph: {"READY": 0, "READY_NA": 0, "PARTIAL": 0, "BLOCKED": 0}
        for ph in phases}
    by_field: Dict[str, int] = {}
    pending: Dict[str, List[str]] = {}
    for p in graph.by_type("Paper"):
        # 只审计已抽取论文：data3 元数据 proxy 不应算作 readiness 失败
        if p.attrs.get("extraction_status") == "proxy":
            continue
        aid = p.attrs.get("arxiv_id") or p.id.split(":")[-1]
        r = audit_paper(effective_attrs(graph, p), spec)
        per_paper[aid] = r
        for ph, v in r.items():
            stats[ph][v["status"]] += 1
            if v["status"] in ("PARTIAL", "BLOCKED"):
                for m in v["missing"]:
                    by_field[m] = by_field.get(m, 0) + 1
                if v.get("refine"):
                    pending.setdefault(v["refine"], []).append(aid)
    return {"n_papers": len(per_paper), "stats": stats,
            "missing_by_requirement": by_field,
            "pending_refine": {k: sorted(set(v)) for k, v in pending.items()},
            "per_paper": per_paper}
