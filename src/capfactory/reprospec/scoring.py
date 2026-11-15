"""P2-8：混合级对齐评分、Perf Gap、三哈希 ClaimAnchor 与最终判定。

对应 `REPRODUCTION_EVALUATION_DESIGN.md` §1–§2、§5 防作弊条款。
所有评分确定性、零 LLM；三层 Align-Score 以 mixed-level 为主
（AutoReproduce 实测 mixed 与人类判断相关性 0.81–0.83）。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .contract import SAU_KINDS


def _sha(obj: Any) -> str:
    blob = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def perf_gap(results: Dict[str, Any]) -> float:
    """``(1/n)Σ|V_ref − V_run| / max(|V_ref|,|V_run|,eps)``。"""
    vals = []
    for r in (results or {}).get("rows") or []:
        b, v = r.get("baseline"), r.get("value")
        try:
            fb, fv = float(b), float(v)
        except (TypeError, ValueError):
            continue
        denom = max(abs(fb), abs(fv), 1e-12)
        vals.append(abs(fb - fv) / denom)
    return round(sum(vals) / len(vals), 6) if vals else 1.0


def align_rubric(spec: Any, sau_report: Any,
                 exec_result: Any = None) -> Dict[str, Any]:
    """三层对齐评分（各 0–100）。

    paper-level：5 个关键点是否有 SAU 覆盖（method / mechanism / data /
                 metric / code），每个 20 分
    code-level ：4 维 × 25 分（符号存在 / 无 stub / 顺序 / 数值）
    mixed      ：0.3·paper + 0.7·code（关键点与代码证据联合）
    """
    counts = getattr(sau_report, "counts", {}) or {}
    total_k = {k: sum(v for x, v in (counts.get(k) or {}).items()
                      if x != "unverified") for k in SAU_KINDS}
    aligned_k = {k: (counts.get(k) or {}).get("aligned", 0) for k in SAU_KINDS}

    def frac(kind: str) -> float:
        return aligned_k[kind] / total_k[kind] if total_k[kind] else 0.0

    paper = {
        "method_sau": bool(total_k["method"]) * 20,
        "mechanism_declared": round(20 * frac("method")),
        "data_contract": round(20 * frac("protocol")),
        "metric_plan": 20 if spec.metric_plan else 0,
        "code_grounding": round(20 * frac("code_grounding")),
    }
    code = {
        "symbol_exists": round(25 * frac("code_grounding")),
        "no_stub": round(25 * (1 - (counts.get("code_grounding") or {})
                               .get("stub", 0) / max(1, total_k["code_grounding"]))),
        "ordering": round(25 * frac("ordering")),
        "numeric": round(25 * frac("numeric")) if total_k["numeric"] else 0,
    }
    p, c = sum(paper.values()), sum(code.values())
    mixed = round(0.3 * p + 0.7 * c, 2)
    return {
        "paper_level": {"score": p, "components": paper},
        "code_level": {"score": c, "components": code},
        "mixed_level": {"score": mixed, "weight": "0.3*paper + 0.7*code"},
        "primary": mixed,
        "note": "确定性实现；混合级与人类判断相关性文献值 0.81–0.83",
    }


def claim_anchors(spec: Any, exec_result: Any,
                  out_dir: str | Path,
                  second_run_sha: Optional[str] = None) -> Dict[str, Any]:
    """三哈希锚 + 漂移判定 + 双跑一致性。"""
    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)
    code_sha = getattr(exec_result, "code_sha", "") or _sha(
        (p / "REPRO_SCRIPT.py").read_text(encoding="utf-8")
        if (p / "REPRO_SCRIPT.py").exists() else "")
    inputs_sha = getattr(exec_result, "inputs_sha", "") or ""
    outputs_sha = getattr(exec_result, "outputs_sha", "") or _sha(
        json.loads((p / "raw_results.json").read_text(encoding="utf-8"))
        if (p / "raw_results.json").exists() else {})
    double_run = (second_run_sha is None) or (second_run_sha == outputs_sha)
    anchors = {
        "paper_id": spec.paper_id, "spec_hash": spec.spec_hash,
        "code_sha": code_sha, "inputs_sha": inputs_sha,
        "outputs_sha": outputs_sha,
        "double_run_equal": double_run,
        "second_run_sha": second_run_sha or "",
        "drift": "" if double_run else "outputs_sha_mismatch",
        "claims": [{"claim_id": "C1", "sau_id": s.id,
                    "code_sha": code_sha, "inputs_sha": inputs_sha,
                    "outputs_sha": outputs_sha, "resolved": bool(outputs_sha)}
                   for s in spec.by_kind("numeric")[:5]],
    }
    (p / "CLAIM_ANCHORS.json").write_text(
        json.dumps(anchors, ensure_ascii=False, indent=2), encoding="utf-8")
    return anchors


@dataclass
class FinalEvaluation:
    paper_id: str
    arxiv_id: str
    effort: str
    overall: str = "BLOCKED"
    reasons: List[str] = field(default_factory=list)
    sau_score: float = 0.0
    coverage: float = 0.0
    drift_rate: float = 0.0
    exec_rate: float = 0.0
    perf_gap: float = 1.0
    symbol_recall: float = 0.0
    align_mixed: float = 0.0
    anchor_integrity: bool = False
    by_drift: Dict[str, int] = field(default_factory=dict)
    counts: Dict[str, Dict[str, int]] = field(default_factory=dict)
    ladder_verdict: str = "BLOCKED"
    debug_tries: int = 0
    out_of_scope: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def finalize(spec: Any, sau_report: Any, exec_result: Any,
             ladder: Any, anchors: Dict[str, Any],
             results: Dict[str, Any], *,
             effort: str, out_dir: str | Path) -> FinalEvaluation:
    """按验证设计 §2.3 判定 overall；写 FINAL_EVALUATION.json。"""
    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)
    ex_ok = bool(getattr(exec_result, "ok", False))
    ex_rate = 1.0 if ex_ok else 0.0
    gap = perf_gap(results)
    rubric = align_rubric(spec, sau_report, exec_result)
    code_total = sum(v for k, v in (sau_report.counts.get("code_grounding")
                                    or {}).items() if k != "unverified")
    method_total = sum(v for k, v in (sau_report.counts.get("method")
                                      or {}).items() if k != "unverified")
    symbol_recall = round(min(1.0, code_total / max(1, method_total)), 4)

    fe = FinalEvaluation(
        paper_id=spec.paper_id, arxiv_id=spec.arxiv_id, effort=effort,
        sau_score=sau_report.sau_score, coverage=sau_report.coverage,
        drift_rate=sau_report.drift_rate, exec_rate=ex_rate,
        perf_gap=gap, symbol_recall=symbol_recall,
        align_mixed=rubric["primary"],
        anchor_integrity=bool(anchors.get("double_run_equal") and
                              anchors.get("outputs_sha")),
        by_drift=sau_report.by_drift, counts=sau_report.counts,
        ladder_verdict=getattr(ladder, "verdict", "BLOCKED"),
        debug_tries=getattr(exec_result, "debug_tries", 0),
        out_of_scope=["原论文模型训练精度（本轮未训练；full 可行性见 "
                      "TRAIN_FEASIBILITY.json）",
                      "原论文实验全量表", "跨数据集泛化"],
    )
    if effort == "dry" or not ex_ok:
        fe.overall = "BLOCKED"
        fe.reasons.append("dry 或执行失败：不得给出非 BLOCKED 判定")
    elif getattr(ladder, "verdict", "BLOCKED") == "BLOCKED":
        fe.overall = "BLOCKED"
        fe.reasons.append("S2 ladder BLOCKED")
    elif not fe.anchor_integrity:
        fe.overall = "BLOCKED"
        fe.reasons.append("三哈希/双跑不一致")
    elif (fe.sau_score >= 0.90 and fe.drift_rate <= 0.05 and
          fe.coverage >= 0.90 and fe.perf_gap <= 0.05 and
          fe.align_mixed >= 80.0 and fe.exec_rate == 1.0):
        fe.overall = "PASS"
    else:
        fe.overall = "PARTIAL"
        if fe.sau_score < 0.90:
            fe.reasons.append(f"SAU_score {fe.sau_score} < 0.90")
        if fe.drift_rate > 0.05:
            fe.reasons.append(f"drift_rate {fe.drift_rate} > 0.05")
        if fe.coverage < 0.90:
            fe.reasons.append(f"coverage {fe.coverage} < 0.90")
        if fe.perf_gap > 0.05:
            fe.reasons.append(f"Perf Gap {fe.perf_gap} > 0.05")
        if fe.align_mixed < 80.0:
            fe.reasons.append(f"Align_mixed {fe.align_mixed} < 80")
    (p / "FINAL_EVALUATION.json").write_text(
        json.dumps({"evaluation": fe.to_dict(), "align_rubric": rubric,
                    "anchors": anchors}, ensure_ascii=False, indent=2,
                   default=str), encoding="utf-8")
    (p / "ALIGN_RUBRIC.json").write_text(
        json.dumps(rubric, ensure_ascii=False, indent=2), encoding="utf-8")
    return fe
