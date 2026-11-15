"""Golden 双路回归（复制 SciForge ``kernel/sciforge/golden.py`` 的范式）。

不是「看效果不错」，而是固定题 + 好坏双路 + 对抗绕过：
好输入必须 PASS、含糊/篡改/平局升档/超轮/哈希漂移必须 FAIL。
任何后续改造让这里的通过数下降，就是回归。
"""

from __future__ import annotations

from typing import Any, Dict, List

from .contracts import (
    gap_gate, verdict, validate_verdict, decide, validate_ladder,
    relative_gain, is_improvement, method_code_parity,
    record_node, verify_anchors, sha256_text,
)

GOOD_GAP = (
    "GAP-1: paper:07 与 paper:09 都报告 A04 扩散方法，但 D7 合成/逆合成领域 "
    "no benchmark exists，未被任何论文测试（Zhang et al. 2025）。\n"
    "GAP-2: A06 GFlowNet 在 20 篇论文中未被使用，缺少多样性采样实现，"
    "no code implementation 可复现（Li 2024）。")
BAD_GAP = "Interesting future work is needed; this topic deserves more research."

GOLDEN_LADDER = {"critic_state": "GOOD", "engineer_rounds": 1,
                 "baseline_score": 0.80, "candidate_score": 0.86,
                 "direction": "maximize", "full_set_pass": True,
                 "relative_gain_pct": relative_gain(0.80, 0.86)}


def run_golden() -> Dict[str, Any]:
    cases: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, **extra: Any) -> None:
        cases.append({"case": name, "passed": bool(ok), **extra})

    # 1) gap 判别双路
    add("gap_good_pass", gap_gate(GOOD_GAP, min_gaps=2)["ok"])
    add("gap_bad_fail", not gap_gate(BAD_GAP, min_gaps=2)["ok"])

    # 2) 三态 Critic 边界
    add("critic_bad", decide(0.80, 0.75) == "BAD")
    add("critic_engineer_on_tie", decide(0.80, 0.80) == "ENGINEER")
    add("critic_good", decide(0.80, 0.86) == "GOOD")
    add("minimize_direction", decide(1.9, 1.5, direction="minimize") == "GOOD")
    add("tie_not_improvement", not is_improvement(0.8, 0.8))

    # 3) ladder 对抗：算术篡改 / 平局升档 / 超轮
    add("ladder_golden_valid", not validate_ladder(GOLDEN_LADDER))
    tampered = dict(GOLDEN_LADDER, relative_gain_pct=99.9)
    add("ladder_tampered_gain_fail", bool(validate_ladder(tampered)))
    tie = dict(GOLDEN_LADDER, candidate_score=0.80, relative_gain_pct=0.0)
    add("ladder_tie_good_fail", bool(validate_ladder(tie)))
    over = dict(GOLDEN_LADDER, engineer_rounds=5)
    add("ladder_over_rounds_fail", bool(validate_ladder(over)))

    # 4) verdict schema
    add("verdict_valid", not validate_verdict(verdict("PASS", notes="ok")))
    add("verdict_illegal", bool(validate_verdict({"verdict": "MAYBE"})))
    add("verdict_warn_strict", bool(validate_verdict(verdict("WARN"), strict=True)))

    # 5) 方法-代码 parity：命中 vs 缺失
    method = "We use EGNN with EGCL and CoorsNorm for coordinate update."
    code_hit = "class EGNN:\n def forward(self, EGCL, CoorsNorm):\n  return coordinate"
    code_miss = "def unrelated():\n  return 1"
    add("parity_high", method_code_parity(method, code_hit)["status"] == "PASS")
    add("parity_low", method_code_parity(method, code_miss)["status"] == "FAIL")

    # 6) 内容寻址：哈希稳定 + 漂移检出
    node = record_node(kind="repro", phase="toy", code="inline:abc",
                       inputs=[{"seed": 42}], outputs=[{"score": 0.86}])
    add("anchor_stable", not verify_anchors([node]))
    drifted = dict(node, code={"path": __file__, "sha256": "0" * 64})
    add("anchor_drift_detected", bool(verify_anchors([drifted])))

    passed = sum(1 for c in cases if c["passed"])
    return {"ok": passed == len(cases), "n": len(cases), "passed": passed,
            "cases": cases}
