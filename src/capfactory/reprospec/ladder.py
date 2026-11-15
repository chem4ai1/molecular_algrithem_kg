"""P1-6：S2 实验阶梯 + 三态 Critic（SciForge `s2-protocol.md` / GGR 蓝图 §5 R5）。

三态：
    GOOD      —— 相对增益 > max(min_gain, GAIN_TOLERANCE)，进入 full
    ENGINEER  —— 打平或轻微差异，允许 ≤ 2 轮调参
    BAD       —— 比 baseline 更差，丢弃

硬规则（SciForge 原样保留）：
  * GOOD 但未严格优于 baseline → 报错
  * full 阶段必须严格优于**它自己的** baseline；ties fail
  * engineer_rounds > 2 → 报错
  * `relative_gain_pct` 由本模块**重算**，不信任脚本自报值（防算术作弊）
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

GAIN_TOLERANCE_PCT = 0.0015      # 0.15%
MAX_ENGINEER_ROUNDS = 2


def relative_gain(baseline: float, candidate: float,
                  direction: str = "min") -> float:
    """min: 越小越好 → gain = (baseline - candidate)/denom；max 反之。"""
    denom = max(abs(float(baseline)), abs(float(candidate)), 1e-12)
    raw = (float(baseline) - float(candidate)) / denom
    return raw if direction == "min" else -raw


def decide(baseline: Any, candidate: Any, *, direction: str = "min",
           min_gain: float = 0.0, tol: float = GAIN_TOLERANCE_PCT * 100
           ) -> str:
    """三态 Critic。``tol`` 以「相对增益」为单位（默认 0.15%）。"""
    try:
        gain = relative_gain(baseline, candidate, direction)
    except (TypeError, ValueError):
        return "BAD"
    if gain > max(min_gain, GAIN_TOLERANCE_PCT):
        return "GOOD"
    if gain >= -GAIN_TOLERANCE_PCT:
        return "ENGINEER"
    return "BAD"


@dataclass
class LadderResult:
    verdict: str = "BLOCKED"            # PASS / PARTIAL / BLOCKED
    critic_state: str = "BAD"
    rows: List[Dict[str, Any]] = field(default_factory=list)
    strict_full_improvement: bool = False
    ties_fail: bool = False
    engineer_rounds: int = 0
    problems: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save(self, out_dir: str | Path) -> str:
        p = Path(out_dir)
        p.mkdir(parents=True, exist_ok=True)
        f = p / "S2_LADDER.json"
        f.write_text(json.dumps(self.to_dict(), ensure_ascii=False,
                                indent=2, default=str), encoding="utf-8")
        return str(f)


def validate_ladder(rows: List[Dict[str, Any]], *,
                    engineer_rounds: int = 0) -> List[str]:
    """重算每个 stage 的 gain 并与声明值比对；返回问题列表。"""
    problems: List[str] = []
    for r in rows:
        b, c = r.get("baseline"), r.get("candidate")
        if b is None or c is None:
            problems.append(f"{r.get('stage')}:缺 baseline 或 candidate")
            continue
        gain = relative_gain(b, c, r.get("direction", "min"))
        declared = r.get("relative_gain_pct")
        if declared is not None and abs(float(declared) - gain) > 0.0015:
            problems.append(
                f"{r.get('stage')}:自报 gain {declared} 与重算 {gain:.6f} 不符")
        if r.get("critic_state") == "GOOD" and not (
                (float(c) < float(b)) if r.get("direction", "min") == "min"
                else (float(c) > float(b))):
            problems.append(f"{r.get('stage')}:GOOD 但未严格优于 baseline")
        if r.get("critic_state") == "GOOD" and abs(float(c) - float(b)) < 1e-12:
            problems.append(f"{r.get('stage')}:ties fail")
    if engineer_rounds > MAX_ENGINEER_ROUNDS:
        problems.append(f"engineer_rounds {engineer_rounds} > {MAX_ENGINEER_ROUNDS}")
    return problems


def run_ladder(exec_result: Any, *, out_dir: Optional[str | Path] = None,
               engineer_rounds: int = 0) -> LadderResult:
    """从 ``ExecutionResult.raw.stages`` 构造 S2 阶梯判定。

    subset 判 GOOD 才"放行" full；full 必须严格优于自己的 baseline。
    脚本实际上两个阶段都跑了，但未被放行的 full 在语义上不算通过。
    """
    out = LadderResult(engineer_rounds=engineer_rounds)
    if not getattr(exec_result, "ok", False):
        out.problems.append("execution_failed")
        out.warnings.append("无执行结果，阶梯不可用")
        if out_dir:
            out.save(out_dir)
        return out
    stages = ((getattr(exec_result, "raw", {}) or {}).get("stages") or {})
    sub, full = stages.get("subset") or {}, stages.get("full") or {}
    if not sub or not full:
        out.problems.append("missing_stage")
        if out_dir:
            out.save(out_dir)
        return out

    for name, st in (("subset", sub), ("full", full)):
        b, c = st.get("baseline"), st.get("candidate")
        state = decide(b, c)
        row = {"stage": name, "baseline": b, "candidate": c,
               "direction": "min",
               "relative_gain_pct": round(relative_gain(b, c), 6)
               if b is not None and c is not None else None,
               "critic_state": state,
               "n_rows": st.get("n_rows"),
               "steps_executed": st.get("steps_executed"),
               "admitted": name == "subset" or state == "GOOD"}
        out.rows.append(row)
    out.critic_state = out.rows[0]["critic_state"]
    if out.critic_state == "BAD":
        out.verdict = "BLOCKED"
        out.problems.append("subset_critic_BAD")
    elif out.critic_state == "ENGINEER":
        out.verdict = "PARTIAL"
        out.warnings.append("subset 打平，需 ENGINEER 调参（≤2 轮）")
    else:
        fr = out.rows[1]
        strict = (fr["candidate"] < fr["baseline"]) and \
                 abs(fr["candidate"] - fr["baseline"]) > 1e-12
        out.strict_full_improvement = bool(strict)
        out.ties_fail = not strict
        if not strict:
            out.verdict = "PARTIAL"
            out.problems.append("full_no_strict_improvement")
        else:
            out.verdict = "PASS"
    out.problems.extend(validate_ladder(out.rows,
                                        engineer_rounds=engineer_rounds))
    if out.verdict == "PASS" and out.problems:
        out.verdict = "PARTIAL"
    if out_dir:
        out.save(out_dir)
    return out
