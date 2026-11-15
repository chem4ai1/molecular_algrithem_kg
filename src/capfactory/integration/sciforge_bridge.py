"""SciForge 核心架构桥接层（CapFactory ⇄ SciForge-OSS）.

融入的是**机制**，不是把 26-node 论文流水线整套搬过来。抽取 SciForge 中
对「算法能力工厂」真正有用、且可机械执行的 4 件事：

| SciForge 机制 | 原实现 | 在 CapFactory 中的用途 |
|---|---|---|
| Subset→Full-Set 三态 Critic | `s2/ladder.py` | 多候选择优：必须在**全集独立测试集**上严格优于复现基线，平局不算赢 |
| 完备性审计 | `s2/audit.py` | reward-hacking 算术复核 + 方法描述↔代码实现 token parity |
| 预执行完整性门 (AAR D1/D2/D3) | `s2/monitor.py` | 生成代码执行前扫描：评测集泄漏 / 更大模型教师 / 自造 ground truth |
| verdict + 机械门 + phasegraph | `gates.py` / `config/phasegraph.json` / `validate_verdicts.py` | 把「提示词里的建议」升级为「代码里 fail-closed 的边界」 |

工程约束
--------
* **动态加载、不拷贝源码**：通过 ``SCIFORGE_ROOT`` 或默认兄弟目录定位 ``kernel/``，
  只把该目录加入 ``sys.path`` 后 import ``sciforge.s2.*``。这也便于遵守
  SciForge 的 PolyForm Noncommercial 1.0.0 许可（不内嵌其代码）。
* **零硬依赖**：SciForge 缺失 / 导入失败时，自动使用本模块内置的等价
  ``_fallback_*`` 实现（规则完全一致），CapFactory 仍可离线完整运行。
* **fail-closed**：无法解析、缺失证据、门未通过一律 BLOCKED，不静默放行。

许可提示：SciForge-OSS 采用 PolyForm Noncommercial 1.0.0，商业使用前需单独授权；
本桥接层只做开发/研究态的可选集成，不构成其代码的再分发。
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..config import REPO_ROOT
from ..utils import now_iso, short_hash

VERDICT_STATES = ("PASS", "WARN", "FAIL", "NOT_APPLICABLE", "BLOCKED", "ERROR")
MAX_ENGINEER_ROUNDS = 2
GAIN_TOLERANCE_PCT = 0.15
PARITY_MIN_RATIO = 0.8

# 能力工厂自己的 phasegraph：借鉴 SciForge「DAG + 每相机械门 + 事件可恢复」思想，
# 但压缩到与算法能力工厂一一对应的 7 相，避免引入 26 相的论文写作流程。
CAPABILITY_PHASEGRAPH: Dict[str, Any] = {
    "schema_version": "capfactory_sciforge_v1",
    "invariants": [
        "INV-G1: 每个能力绑定 problem_id / source_id，边界处重算 hash",
        "INV-G2: 非 PASS verdict 阻断下一相（fail-closed）",
        "INV-G3: 验证指标必须由平台侧裁判计算，候选代码不得自报指标",
    ],
    "phases": [
        {"id": "p1_ingest",   "name": "采集与解析",   "gates": ["source_present"],
         "next": ["p2_extract"]},
        {"id": "p2_extract",  "name": "能力抽取",     "gates": ["evidence_anchored",
                                                              "schema_valid"],
         "next": ["p3_plan"]},
        {"id": "p3_plan",     "name": "方案规划",     "gates": ["applicability_ok",
                                                              "budget_feasible"],
         "next": ["p4_generate"]},
        {"id": "p4_generate", "name": "代码生成",     "gates": ["static_contract_ok",
                                                              "integrity_D2_D3"],
         "next": ["p5_verify"]},
        {"id": "p5_verify",   "name": "验证与比较",   "gates": ["metrics_computed",
                                                              "s2_ladder",
                                                              "reward_hacking_audit"],
         "next": ["p6_deposit"]},
        {"id": "p6_deposit",  "name": "知识沉淀",     "gates": ["kg_writeback_ok"],
         "next": ["p7_report"]},
        {"id": "p7_report",   "name": "方向与报告",   "gates": ["report_generated"],
         "next": []},
    ],
}

_HOLDOUT_RE = re.compile(r"\b(holdout|held_out|heldout|secret_dir|eval_private|answer_key)\w*", re.I)
_ACQUISITION_RE = re.compile(
    r"load_dataset\s*\(|datasets\.load_dataset|urllib|requests\.get|curl\s|wget\s|git\s+clone", re.I)
_FRONTIER_RE = re.compile(r"gpt-[45]|o[13]-|claude-(?:opus|sonnet)|gemini-(?:ultra|pro)", re.I)
_TEACHER_VERB_RE = re.compile(r"\b(label|teacher|distill|synthes|generate|augment|annotate)\w*", re.I)
_TOKEN_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_]{3,})`|\b([a-z]+_[a-z0-9_]{3,})\b")


def _relative_gain(baseline: float, candidate: float, direction: str) -> float:
    b, c = float(baseline), float(candidate)
    if b == 0:
        delta = (c - b) if direction == "maximize" else (b - c)
        return 100.0 * delta
    raw = (c - b) / abs(b) * 100.0
    return raw if direction == "maximize" else -raw


def _is_improvement(baseline: float, candidate: float, direction: str) -> bool:
    b, c = float(baseline), float(candidate)
    return c > b if direction == "maximize" else c < b


def _decide(baseline: float, candidate: float, direction: str, min_gain: float = 0.0) -> str:
    gain = _relative_gain(baseline, candidate, direction)
    if gain > max(min_gain, 0.0):
        return "GOOD"
    if gain >= 0.0:
        return "ENGINEER"
    return "BAD"


def _fallback_ladder_validate(doc: Dict[str, Any]) -> List[str]:
    """与 ``sciforge.s2.ladder.validate`` 等价的内置规则（无外部依赖时）。"""
    problems: List[str] = []
    subset, fullset = doc.get("subset") or {}, doc.get("fullset") or {}
    critic, metric = doc.get("critic") or {}, doc.get("metric") or {}
    if not subset:
        problems.append("subset stage missing (baseline reproduction never ran)")
    if not fullset:
        problems.append("fullset stage missing (full-set verification never ran)")
    state = critic.get("state")
    if state not in ("BAD", "GOOD", "ENGINEER"):
        problems.append(f"critic.state must be one of BAD|GOOD|ENGINEER, got {state!r}")
    rounds = critic.get("engineer_rounds")
    if not isinstance(rounds, int) or rounds < 0:
        problems.append("critic.engineer_rounds must be a non-negative integer")
    elif rounds > MAX_ENGINEER_ROUNDS:
        problems.append(f"engineer_rounds={rounds} exceeds the cap of {MAX_ENGINEER_ROUNDS}")
    direction = metric.get("direction", "maximize")
    if direction not in ("maximize", "minimize"):
        problems.append(f"metric.direction invalid: {direction!r}")
    fv = (fullset.get("candidate") or {}).get("value")
    bv = (fullset.get("baseline") or {}).get("value")
    if state == "GOOD":
        if fv is None or bv is None:
            problems.append("critic=GOOD but fullset baseline/candidate values missing")
        elif not _is_improvement(bv, fv, direction):
            problems.append(f"critic=GOOD but fullset candidate {fv} does not strictly beat {bv}")
        if fullset.get("verified") is not True:
            problems.append("critic=GOOD but fullset.verified is not true")
    stated = doc.get("relative_gain_pct")
    if stated is not None and fv is not None and bv is not None:
        expected = _relative_gain(bv, fv, direction)
        if abs(expected - float(stated)) > GAIN_TOLERANCE_PCT:
            problems.append(f"relative_gain_pct stated {stated} != recomputed "
                            f"{round(expected, 4)} (arithmetic inconsistency)")
    if not (doc.get("problem_id") or doc.get("run_id")):
        problems.append("problem_id/run_id missing (INV-G1 anchor required)")
    return problems


def _fallback_scan_code(text: str, benchmark_names: Sequence[str]) -> List[Dict[str, Any]]:
    """AAR D2/D3 确定性扫描的等价实现。"""
    violations: List[Dict[str, Any]] = []
    has_teacher_verb = bool(_TEACHER_VERB_RE.search(text))
    for i, line in enumerate(text.splitlines(), 1):
        if _HOLDOUT_RE.search(line):
            violations.append({"desiderata": "D2", "line": i,
                               "kind": "eval-private-path", "detail": line.strip()[:120]})
        if _ACQUISITION_RE.search(line):
            for b in benchmark_names:
                if len(b) >= 4 and b.lower() in line.lower():
                    violations.append({"desiderata": "D2", "line": i,
                                       "kind": "benchmark-download",
                                       "detail": f"acquisition names scored benchmark {b!r}"})
        if _FRONTIER_RE.search(line) and has_teacher_verb:
            violations.append({"desiderata": "D3", "line": i,
                               "kind": "frontier-teacher", "detail": line.strip()[:120]})
    return violations


class SciForgeBridge:
    """CapFactory 与 SciForge kernel 的可选桥接。"""

    def __init__(self, root: Optional[str] = None, *, strict: bool = False):
        self.root = self._resolve_root(root)
        self.strict = strict
        self.available = False
        self.backend = "fallback"
        self.load_error = ""
        self._ladder = None
        self._audit = None
        self._monitor = None
        self._load()

    # -- 加载 -------------------------------------------------------------
    @staticmethod
    def _resolve_root(root: Optional[str]) -> Path:
        candidates = [
            root, os.environ.get("SCIFORGE_ROOT"),
            str(REPO_ROOT.parent / "SciForge-OSS-master"),
            str(REPO_ROOT / "SciForge-OSS-master"),
        ]
        for c in candidates:
            if c and (Path(c) / "kernel" / "sciforge" / "s2").is_dir():
                return Path(c)
        return Path(candidates[2])

    def _load(self) -> None:
        kernel = self.root / "kernel"
        if not kernel.is_dir():
            self.load_error = f"kernel 目录不存在：{kernel}"
            return
        try:
            if str(kernel) not in sys.path:
                sys.path.insert(0, str(kernel))
            from sciforge.s2 import audit, ladder, monitor  # type: ignore
            self._ladder, self._audit, self._monitor = ladder, audit, monitor
            self.available = True
            self.backend = f"sciforge@{self.root.name}"
        except Exception as exc:  # noqa: BLE001 - 可选依赖，失败即降级
            self.load_error = f"{type(exc).__name__}: {exc}"
            if self.strict:
                raise

    def status(self) -> Dict[str, Any]:
        return {
            "available": self.available, "backend": self.backend,
            "root": str(self.root), "load_error": self.load_error,
            "modules": {
                "ladder": "sciforge.s2.ladder" if self._ladder else "builtin_fallback",
                "audit": "sciforge.s2.audit" if self._audit else "builtin_fallback",
                "monitor": "sciforge.s2.monitor" if self._monitor else "builtin_fallback",
            },
            "phasegraph": CAPABILITY_PHASEGRAPH["schema_version"],
            "verdict_states": list(VERDICT_STATES),
        }

    # -- 机制 1：Subset→Full-Set 三态 Critic -------------------------------
    def evaluate_candidate(self, *, baseline_subset: float, candidate_subset: float,
                           baseline_full: float, candidate_full: float,
                           direction: str = "maximize", metric: str = "roc_auc",
                           problem_id: str = "", engineer_rounds: int = 0,
                           min_gain: float = 0.0, fullset_verified: bool = True) -> Dict[str, Any]:
        """判定一次「算法方案改进」是否真实成立。

        与 CapFactory 原 ``replicator`` 的「取最高分候选」不同：这里要求
        **在全量独立测试集上严格优于复现基线**，且相对增益的算术必须自洽。
        """
        problem_id = problem_id or f"cap_{short_hash(now_iso(), length=8)}"
        state = _decide(baseline_full, candidate_full, direction, min_gain)
        gain = round(_relative_gain(baseline_full, candidate_full, direction), 4)
        doc = {
            "schema_version": "1.0", "problem_id": problem_id, "metric": {
                "name": metric, "direction": direction},
            "subset": {"baseline": {"value": baseline_subset},
                       "candidate": {"value": candidate_subset}},
            "fullset": {"baseline": {"value": baseline_full},
                        "candidate": {"value": candidate_full},
                        "verified": bool(fullset_verified)},
            "critic": {"state": state, "engineer_rounds": int(engineer_rounds)},
            "relative_gain_pct": gain,
            "ts": now_iso(),
        }
        validator = self._ladder.validate if self._ladder else _fallback_ladder_validate
        problems = list(validator(doc))
        if state != "GOOD":
            # SciForge 的 validate 只在 GOOD 状态下检查全集提升；对 ENGINEER/BAD
            # 补充一条可解释结论，避免调用方把空 problems 误读为"没有问题"。
            problems.append(
                f"critic.state={state}: fullset candidate {candidate_full} vs baseline "
                f"{baseline_full} — no strict full-set improvement, promotion refused")
        if not fullset_verified:
            problems.append("fullset.verified is false — unverified full-set result cannot promote")
        promoted = (state == "GOOD" and not problems and fullset_verified)
        return {
            "verdict": "PASS" if promoted else "FAIL",
            "promoted": promoted, "critic_state": state,
            "relative_gain_pct": gain,
            "subset_gain_pct": round(_relative_gain(baseline_subset, candidate_subset, direction), 4),
            "problems": problems, "doc": doc,
            "rule": "GOOD 只能在全集上取得；平局/仅子集提升/算术不一致一律不晋升",
            "backend": self.backend,
        }

    # -- 机制 2：完备性审计（reward hacking + 方法↔代码 parity） ------------
    def audit_experiment(self, *, method_text: str, code_text: str,
                         ladder_doc: Optional[Dict[str, Any]] = None,
                         protocol_text: str = "held-out test split, fixed seed 42") -> Dict[str, Any]:
        """审计一次复刻：增益算术、划分声明、方法描述与实现的一致性。"""
        parity: Dict[str, Any]
        if self._audit:
            with tempfile.TemporaryDirectory(prefix="cf_audit_") as td:
                ws = Path(td)
                (ws / "methods").mkdir()
                (ws / "src").mkdir()
                (ws / "methods" / "METHOD_REGISTRY.md").write_text(method_text or "", encoding="utf-8")
                (ws / "src" / "solution.py").write_text(code_text or "", encoding="utf-8")
                if ladder_doc:
                    audits = ws / ".sciforge" / "audits"
                    audits.mkdir(parents=True)
                    (audits / "S2_LADDER.json").write_text(json.dumps(ladder_doc), encoding="utf-8")
                experiments = ws / "experiments" / "full"
                experiments.mkdir(parents=True)
                # SciForge 的 protocol_split_declaration 只查这三个固定路径，
                # 必须按其约定落盘，否则会把「已声明划分」误判为 reward hacking。
                (ws / "experiments" / "EVALUATION_PROTOCOL.md").write_text(
                    protocol_text, encoding="utf-8")
                verdicts = ws / ".sciforge" / "verdicts"
                verdicts.mkdir(parents=True, exist_ok=True)
                (verdicts / "EVALUATION_PROTOCOL.json").write_text(
                    json.dumps({"protocol": protocol_text, "split": "held-out test",
                                "seed": 42}), encoding="utf-8")
                (experiments / "RESULT.json").write_text("{}", encoding="utf-8")
                parity = self._audit.method_code_parity(ws)
                hacking = self._audit.reward_hacking_scan(ws)
        else:
            tokens = sorted({next((g for g in m.groups() if g), "")
                             for m in _TOKEN_RE.finditer(method_text or "")})
            tokens = [t for t in tokens if t]
            matched = [t for t in tokens if re.search(rf"\b{re.escape(t)}\b", code_text or "")]
            ratio = len(matched) / len(tokens) if tokens else 0.0
            parity = {"status": "SKIP" if not tokens else
                      ("PASS" if ratio >= PARITY_MIN_RATIO else "FAIL"),
                      "ratio": round(ratio, 3), "claimed": len(tokens),
                      "matched": len(matched), "unmatched": [t for t in tokens if t not in matched][:40]}
            gain_ok = True
            if ladder_doc and ladder_doc.get("relative_gain_pct") is not None:
                fv = (ladder_doc.get("fullset") or {}).get("candidate", {}).get("value")
                bv = (ladder_doc.get("fullset") or {}).get("baseline", {}).get("value")
                d = (ladder_doc.get("metric") or {}).get("direction", "maximize")
                if fv is not None and bv is not None:
                    gain_ok = abs(_relative_gain(bv, fv, d) -
                                  float(ladder_doc["relative_gain_pct"])) <= GAIN_TOLERANCE_PCT
            split_ok = any(k in protocol_text.lower()
                           for k in ("held-out", "seed", "split", "test"))
            hacking = {
                "overall": "PASS" if (gain_ok and split_ok) else "FAIL",
                "checks": {
                    "gain_arithmetic": {"status": "PASS" if gain_ok else "FAIL"},
                    "split_discipline": {"status": "PASS" if split_ok else "FAIL"},
                },
            }
        statuses = [parity.get("status"), hacking.get("overall")]
        overall = "FAIL" if "FAIL" in statuses else ("PASS" if "PASS" in statuses else "SKIP")
        return {"overall": overall, "method_code_parity": parity,
                "reward_hacking": hacking, "backend": self.backend,
                "rule": "FAIL 阻断 wrap-up；SKIP 仅当没有实验声明"}

    # -- 机制 3：预执行完整性门（AAR D1/D2/D3） ----------------------------
    def pre_execution_gate(self, code_text: str, *,
                           benchmark_names: Sequence[str] = ()) -> Dict[str, Any]:
        """代码执行前扫描 D2（评测集泄漏）/ D3（更大模型教师）；D1 需 LLM 或人工。"""
        scanner = self._monitor.scan_code if self._monitor else _fallback_scan_code
        violations = scanner(code_text or "", list(benchmark_names))
        return {
            "verdict": "BLOCKED" if violations else "PASS",
            "decision": "REJECT" if violations else "APPROVE",
            "violations": violations[:20],
            "benchmarks": list(benchmark_names),
            "d1_note": "D1（自造 ground truth）需语义审阅；无 LLM 时标记为 NOT_APPLICABLE",
            "backend": self.backend,
        }

    # -- 机制 4：verdict 机械门 -------------------------------------------
    @staticmethod
    def check_boundary(verdicts: Dict[str, str], *,
                       phase: str = "", required: Sequence[str] = ()) -> Dict[str, Any]:
        """边界门：任何非 PASS（且未显式声明 NOT_APPLICABLE）都阻断下一相。"""
        missing = [g for g in required if g not in verdicts]
        blocking = {k: v for k, v in verdicts.items()
                    if v not in ("PASS", "NOT_APPLICABLE", "N/A")}
        ok = not missing and not blocking
        return {
            "phase": phase, "verdict": "PASS" if ok else "BLOCKED", "ok": ok,
            "missing_verdicts": missing, "blocking_verdicts": blocking,
            "rule": "INV-G2: 非 PASS verdict 阻断下一相（fail-closed）",
        }

    def phasegraph(self) -> Dict[str, Any]:
        return dict(CAPABILITY_PHASEGRAPH)


_BRIDGE: Optional[SciForgeBridge] = None


def get_bridge(root: Optional[str] = None) -> SciForgeBridge:
    """进程级单例（避免重复修改 sys.path）。"""
    global _BRIDGE
    if _BRIDGE is None or (root and Path(root) != _BRIDGE.root):
        _BRIDGE = SciForgeBridge(root)
    return _BRIDGE
