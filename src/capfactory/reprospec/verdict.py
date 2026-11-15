"""P0-4：逐 SAU 静态判定（GGR 蓝图 §5 R6、§6 评估）。

**dry 也能用**：不依赖实跑值，只用图上已有的静态证据判
``aligned / mismatch / stub / absent``；需要执行才能判的一律 ``unverified``
并计入 coverage 分母之外，**绝不伪装成通过**。

这解决 SA-Bench (arXiv 2608.24252) 指出的核心问题：只看 ``Perf Gap``
无法发现「代码能跑但实现与论文不符」的 semantic drift。

判定规则（全部确定性、零 LLM）：

==============  ============================================================
SAU kind        静态证据
==============  ============================================================
method          mechanism 非空 + 同模块有 code_grounding SAU → aligned
                有 mechanism 但无实现 → mismatch；mechanism 缺失 → absent
code_grounding  CodeFunction 节点存在且非 stub → aligned
                purpose/comment 含 TODO/pass/placeholder → stub
                节点不存在 → absent；signature/file 全空 → mismatch
protocol        input_form + output_form 齐 → aligned（标 execution_unverified）
                缺任一 → absent
numeric         results 提供实跑值 → 按 direction + tolerance 比对
                dry 无 results → unverified
ordering        before/after 在 code_plan.order 中且顺序正确 → aligned
                环依赖 / 声明顺序 → unverified；顺序颠倒 → mismatch
==============  ============================================================

    from capfactory.reprospec import compile_reprospec
    from capfactory.reprospec.verdict import evaluate_sau

    spec = compile_reprospec(graph, paper_id="paper:2411.06608")
    rep = evaluate_sau(spec, graph)          # dry
    rep.sau_score, rep.coverage, rep.drift_rate
    rep.save(out_dir)
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .contract import SAU_KINDS, ReproSpec

VERDICTS = ("aligned", "mismatch", "stub", "absent", "unverified")

DRIFT_OF_KIND = {
    "method": "methodological",
    "code_grounding": "methodological",
    "protocol": "protocol",
    "numeric": "numerical",
    "ordering": "ordering",
}

_STUB_MARKERS = ("todo", "not implemented", "placeholder", "stub",
                 "raise notimplementederror", "pass  #", " FIXME")


@dataclass
class SAUReport:
    paper_id: str
    spec_hash: str
    effort: str = "dry"
    verdicts: List[Dict[str, Any]] = field(default_factory=list)
    counts: Dict[str, Dict[str, int]] = field(default_factory=dict)
    score_by_kind: Dict[str, float] = field(default_factory=dict)
    sau_score: float = 0.0
    coverage: float = 0.0
    drift_rate: float = 0.0
    by_drift: Dict[str, int] = field(default_factory=dict)
    n_total: int = 0
    n_decidable: int = 0
    n_aligned: int = 0
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save(self, out_dir: str | Path) -> Dict[str, str]:
        p = Path(out_dir)
        p.mkdir(parents=True, exist_ok=True)
        f = p / "SAU_VERDICTS.json"
        f.write_text(json.dumps(self.to_dict(), ensure_ascii=False,
                                indent=2, default=str), encoding="utf-8")
        return {"SAU_VERDICTS.json": str(f)}


def _node(g: Any, nid: str) -> Any:
    return (getattr(g, "nodes", {}) or {}).get(nid)


def _attrs(n: Any) -> Dict[str, Any]:
    return dict(getattr(n, "attrs", {}) or {}) if n else {}


def _is_stub(a: Dict[str, Any]) -> bool:
    text = " ".join(str(a.get(k) or "")
                    for k in ("purpose", "comment", "docstring", "name")).lower()
    return any(m in text for m in _STUB_MARKERS)


def _numeric_verdict(s: Any, results: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """有实跑值才判；否则 unverified（dry 的核心诚实约束）。"""
    chk = s.check
    if not results:
        return {"verdict": "unverified", "evidence": [],
                "note": "dry 无实跑值，R6 不得据此判 PASS"}
    target = chk.get("target")
    observed = None
    if isinstance(results, dict):
        # P1-5：执行器返回 {"entry_values": {entry_id: value}, "rows": [...]}
        entry_values = results.get("entry_values") or {}
        if target in entry_values:
            observed = entry_values[target]
        elif target in results:
            observed = results[target]
        else:
            for k, v in results.items():
                if isinstance(v, dict) and k == chk.get("metric"):
                    observed = v.get("value")
                    break
    if observed is None:
        return {"verdict": "unverified", "evidence": [],
                "note": "results 中无该榜单行/指标的实跑值"}
    try:
        got = float(observed)
        want = float(chk.get("value_num") if chk.get("value_num") is not None
                     else chk.get("value"))
    except (TypeError, ValueError):
        return {"verdict": "unverified", "evidence": [],
                "note": "实跑值或论文值非数值"}
    denom = max(abs(want), abs(got), 1e-12)
    gap = abs(got - want) / denom
    tol = float(chk.get("tolerance") or 0.05)
    ok = gap <= tol
    return {
        "verdict": "aligned" if ok else "mismatch",
        "evidence": [{"observed": got, "expected": want,
                      "relative_gap": round(gap, 6), "tolerance": tol}],
        "note": "" if ok else f"偏差 {gap:.4f} 超过 {tol}",
    }


def evaluate_sau(spec: ReproSpec, graph: Any, *,
                 results: Optional[Dict[str, Any]] = None,
                 effort: str = "dry") -> SAUReport:
    """逐 SAU 判定；返回 SAUReport。

    参数
        spec    : P0-2 编译的 ReproSpec
        graph   : 应用层/语义层图（只读，提供 CodeFunction 等静态证据）
        results : 实跑值映射（dry 传 None）
        effort  : dry / lite / full，仅写入报告
    """
    rep = SAUReport(paper_id=spec.paper_id, spec_hash=spec.spec_hash,
                    effort=effort)
    code_by_module: Dict[str, List[str]] = {}
    for s in spec.by_kind("code_grounding"):
        for m in s.source_node_ids:
            code_by_module.setdefault(m, []).append(s.id)
    order = (spec.code_plan or {}).get("order") or []
    order_idx = {m: i for i, m in enumerate(order)}

    for s in spec.sau:
        chk = s.check
        v: Dict[str, Any] = {"sau_id": s.id, "kind": s.kind,
                            "required": s.required, "verdict": "unverified",
                            "drift_type": DRIFT_OF_KIND.get(s.kind, "other"),
                            "evidence": [], "note": ""}
        if s.kind == "method":
            mod = chk.get("target")
            impl = code_by_module.get(mod, [])
            if not chk.get("mechanism"):
                v.update(verdict="absent", note="mechanism 缺失")
            elif impl:
                v.update(verdict="aligned", evidence=impl[:5],
                         note=f"{len(impl)} 个代码符号落地")
            else:
                v.update(verdict="mismatch",
                         note="模块无 MODULE_IMPLEMENTED_BY / BELONGS_TO_MODULE 边")
        elif s.kind == "code_grounding":
            fn = _node(graph, chk.get("target"))
            if fn is None:
                v.update(verdict="absent", note="CodeFunction 节点不存在")
            else:
                a = _attrs(fn)
                if _is_stub(a):
                    v.update(verdict="stub", note="函数体标记 TODO/pass/placeholder")
                elif not (chk.get("signature") or a.get("name") or a.get("params")):
                    v.update(verdict="mismatch",
                             note="无 signature/name/params，无法确认实现")
                else:
                    v.update(verdict="aligned", evidence=[fn.id],
                             note="AST 符号存在且非 stub")
        elif s.kind == "protocol":
            if chk.get("input_form") and chk.get("output_form"):
                v.update(verdict="aligned", evidence=list(s.source_node_ids),
                         note="静态数据契约齐；shape 待 R3.5 实测",
                         execution_unverified=True)
            else:
                v.update(verdict="absent", note="input/output_form 缺失")
        elif s.kind == "numeric":
            r = _numeric_verdict(s, results)
            v.update(verdict=r["verdict"], evidence=r["evidence"],
                     note=r["note"])
        elif s.kind == "ordering":
            if chk.get("cycle"):
                v.update(verdict="unverified",
                         note="环依赖，需人工或执行确认")
            elif chk.get("op") == "declared_order":
                # P3-1：scope 归一化后图上可能不再有 inputs/outputs 共享词元，
                # 编译器会降级成「声明顺序」。它与 code_plan.order 的一致性
                # 是可以静态验证的事实（和 protocol SAU 同口径），但仍显式标
                # declaration_only / execution_unverified，绝不冒充执行验证。
                b, a = chk.get("before"), chk.get("after")
                if b in order_idx and a in order_idx:
                    ok = order_idx[b] < order_idx[a]
                    v.update(verdict="aligned" if ok else "mismatch",
                             evidence=[{"before": order_idx[b],
                                        "after": order_idx[a]}],
                             note="声明顺序与 code_plan.order 一致（无数据流证据）"
                                  if ok else "声明顺序与 code_plan.order 颠倒",
                             declaration_only=True,
                             execution_unverified=True)
                else:
                    v.update(verdict="mismatch", note="节点不在 code_plan.order")
            else:
                b, a = chk.get("before"), chk.get("after")
                if b in order_idx and a in order_idx:
                    ok = order_idx[b] < order_idx[a]
                    v.update(verdict="aligned" if ok else "mismatch",
                             evidence=[{"before": order_idx[b],
                                        "after": order_idx[a]}],
                             note="" if ok else "code_plan.order 顺序颠倒")
                else:
                    v.update(verdict="mismatch", note="节点不在 code_plan.order")
        rep.verdicts.append(v)

    # ---- 汇总 -------------------------------------------------------------
    rep.counts = {
        k: {x: sum(1 for v in rep.verdicts
                   if v["kind"] == k and v["verdict"] == x) for x in VERDICTS}
        for k in SAU_KINDS}
    rep.n_total = len(rep.verdicts)
    rep.n_aligned = sum(1 for v in rep.verdicts
                        if v["verdict"] == "aligned")
    rep.n_decidable = sum(1 for v in rep.verdicts
                          if v["verdict"] != "unverified")
    rep.sau_score = (round(rep.n_aligned / rep.n_decidable, 4)
                     if rep.n_decidable else 0.0)
    rep.coverage = (round(rep.n_decidable / rep.n_total, 4)
                    if rep.n_total else 0.0)
    drift = rep.n_decidable - rep.n_aligned
    rep.drift_rate = (round(drift / rep.n_decidable, 4)
                      if rep.n_decidable else 0.0)
    rep.by_drift = {
        d: sum(1 for v in rep.verdicts
               if v["drift_type"] == d and v["verdict"] in
               ("mismatch", "stub", "absent")) for d in
        ("numerical", "methodological", "protocol", "ordering")}
    rep.score_by_kind = {}
    for k in SAU_KINDS:
        decidable_k = sum(rep.counts[k][x] for x in VERDICTS
                          if x != "unverified")
        rep.score_by_kind[k] = (round(rep.counts[k]["aligned"] /
                                      decidable_k, 4)
                                if decidable_k else 0.0)
    unverified = rep.n_total - rep.n_decidable
    if unverified:
        rep.warnings.append(
            f"{unverified} 条 SAU 因无实跑值/环依赖标 unverified，不计入 sau_score")
    if rep.drift_rate > 0.2:
        rep.warnings.append(
            f"drift_rate={rep.drift_rate} 超过 0.20，R6 语义门应判 PARTIAL")
    return rep


def sau_drift_acceptable(report: SAUReport,
                         max_drift: float = 0.20) -> Dict[str, Any]:
    """P1 可接入 R6 的辅助语义门（当前不改变 R6 既有 verdict）。"""
    reasons: List[str] = []
    if report.n_decidable == 0:
        return {"verdict": "BLOCKED", "reasons": ["no_decidable_sau"],
                "sau_score": report.sau_score,
                "drift_rate": report.drift_rate}
    if report.drift_rate > max_drift:
        reasons.append(f"drift_rate {report.drift_rate} > {max_drift}")
    if report.coverage < 0.5:
        reasons.append(f"coverage {report.coverage} < 0.5")
    return {"verdict": "PASS" if not reasons else "PARTIAL",
            "reasons": reasons, "sau_score": report.sau_score,
            "coverage": report.coverage, "drift_rate": report.drift_rate}
