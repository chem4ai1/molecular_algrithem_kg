"""从 SciForge-OSS 复制并适配的**确定性判定层**（纯标准库，零外部依赖）。

来源与理念：

* ``kernel/sciforge/s2/ladder.py`` —— subset→full 阶梯 + 三态 Critic；
* ``scripts/gap_gate.py`` —— 缺口报告的判别门（好缺口 PASS / 含糊 FAIL）；
* ``kernel/sciforge/s2/audit.py`` —— 方法段 token 与代码的方法-代码对齐；
* ``kernel/sciforge/nodes.py`` —— 内容寻址证据节点（code/inputs/outputs 哈希）；
* ``skills/shared-references/assurance-contract.md`` —— 6 态 verdict。

核心原则（SciForge README L13）：
**「what to do stays in Markdown; how it is enforced moves into code」**——
LLM 只负责生成与推理，判定权交给这里的确定性函数，不能写在 prompt 里靠自觉。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# ① 6 态 verdict（assurance-contract.md）
# ---------------------------------------------------------------------------
VERDICT_STATES = ("PASS", "WARN", "FAIL", "NOT_APPLICABLE", "BLOCKED", "ERROR")
TERMINAL_OK = ("PASS", "NOT_APPLICABLE")


def verdict(state: str, *, artifacts: Iterable[str] = (),
            notes: str = "", strict: bool = False) -> Dict[str, Any]:
    """构造机器 verdict。``strict`` 下 WARN 视为不通过。"""
    state = str(state or "ERROR").upper()
    if state not in VERDICT_STATES:
        state = "ERROR"
        notes = f"非法状态 {state}; {notes}"
    ok = state in TERMINAL_OK or (state == "WARN" and not strict)
    return {"verdict": state, "ok": ok,
            "artifacts": [str(x) for x in artifacts], "notes": notes}


def validate_verdict(d: Dict[str, Any], *, strict: bool = False) -> List[str]:
    """校验 verdict 结构（等价于 validate_verdicts.py 的最小子集）。"""
    problems: List[str] = []
    if not isinstance(d, dict):
        return ["verdict 必须是对象"]
    if d.get("verdict") not in VERDICT_STATES:
        problems.append(f"verdict 非法: {d.get('verdict')!r}")
    if not isinstance(d.get("artifacts", []), list):
        problems.append("artifacts 必须是数组")
    if not isinstance(d.get("notes", ""), str):
        problems.append("notes 必须是字符串")
    if strict and d.get("verdict") == "WARN":
        problems.append("strict 模式下 WARN 不通过")
    return problems


# ---------------------------------------------------------------------------
# ② Subset→Full 阶梯 + 三态 Critic（s2/ladder.py 逐字等价）
# ---------------------------------------------------------------------------
LADDER_STATES = ("BAD", "GOOD", "ENGINEER")
MAX_ENGINEER_ROUNDS = 2
GAIN_TOLERANCE_PCT = 0.15


def relative_gain(baseline: float, candidate: float,
                  direction: str = "maximize") -> float:
    b, c = float(baseline), float(candidate)
    if b == 0:
        delta = (c - b) if direction == "maximize" else (b - c)
        return 100.0 * delta
    raw = (c - b) / abs(b) * 100.0
    return raw if direction == "maximize" else -raw


def is_improvement(baseline: float, candidate: float,
                   direction: str = "maximize") -> bool:
    """严格优于；平局不算改进（SciForge 的硬规则）。"""
    b, c = float(baseline), float(candidate)
    return c > b if direction == "maximize" else c < b


def decide(baseline: float, candidate: float, direction: str = "maximize",
           min_gain: float = 0.0) -> str:
    """三态 Critic：GOOD(升 full) / ENGINEER(≤2 轮调参) / BAD(丢弃)。"""
    gain = relative_gain(baseline, candidate, direction)
    if gain > max(min_gain, 0.0):
        return "GOOD"
    if gain >= -GAIN_TOLERANCE_PCT:
        return "ENGINEER"
    return "BAD"


def validate_ladder(doc: Dict[str, Any]) -> List[str]:
    """S2_LADDER.json 的机械校验：防算术篡改、平局升档、超轮数。"""
    p: List[str] = []
    if doc.get("critic_state") not in LADDER_STATES:
        p.append("critic_state 非法")
    eng = int(doc.get("engineer_rounds", 0) or 0)
    if eng > MAX_ENGINEER_ROUNDS:
        p.append(f"engineer_rounds {eng} > {MAX_ENGINEER_ROUNDS}")
    b, c = doc.get("baseline_score"), doc.get("candidate_score")
    direction = doc.get("direction", "maximize")
    if isinstance(b, (int, float)) and isinstance(c, (int, float)):
        stated = doc.get("relative_gain_pct")
        if stated is not None and abs(float(stated) - relative_gain(b, c, direction)) > GAIN_TOLERANCE_PCT:
            p.append("relative_gain_pct 与重算值不符")
        if doc.get("critic_state") == "GOOD" and not is_improvement(b, c, direction):
            p.append("GOOD 但全集未严格优于基线")
        if doc.get("full_set_pass") and not is_improvement(b, c, direction):
            p.append("full_set_pass 但全集未严格优于基线")
    return p


# ---------------------------------------------------------------------------
# ③ 缺口判别门（scripts/gap_gate.py 适配到图谱 gap dict）
# ---------------------------------------------------------------------------
GAP_ID = re.compile(r"(GAP-\d+|#gap-[\w-]+|\[GAP:?\s*\d+\]|gap:[A-Za-z0-9_-]+)", re.I)
CITATION = re.compile(
    r"(\[@[\w:-]+\]|\[[A-Z][\w-]*,\s*\d{4}\]|\b[A-Z][a-z]+(?: et al\.?)? \d{4}\b|"
    r"\(\d{4}\)|paper:\d+|arxiv:\d{4}\.\d{4,5})")
DISCRIMINATOR = re.compile(
    r"contradict|inconsistent|unsolved|not (?:been )?(?:studied|tested|measured|validated)|"
    r"absence of|no (?:study|evidence|benchmark|dataset|code|implementation)|"
    r"remains (?:open|unknown|unverified)|fail(?:s|ed)? to (?:explain|account|reproduce)|"
    r"discrepan(?:cy|cies)|cannot (?:explain|distinguish)|untested|not reported|"
    r"未被|没有|缺少|空白|未使用|未覆盖|不可比|未实现", re.I)


def gap_gate(report_text: str, *, min_gaps: int = 1,
             require_citation: bool = True) -> Dict[str, Any]:
    """判别门：返回 ``{ok, problems, n_gaps, n_discriminators, n_citations}``。

    与 SciForge 原版一致——「interesting future work」这类含糊表述必须 FAIL。
    """
    text = str(report_text or "")
    ids = GAP_ID.findall(text)
    cites = CITATION.findall(text)
    discs = DISCRIMINATOR.findall(text)
    problems: List[str] = []
    if len(set(ids)) < min_gaps:
        problems.append(f"期望 >= {min_gaps} 个 gap-id，实际 {len(set(ids))}")
    if require_citation and not cites:
        problems.append("缺口未锚定任何引用/论文节点")
    if len(discs) < max(1, min_gaps):
        problems.append(f"缺少判别性语言（找到 {len(discs)} 个标记）")
    blocks = re.split(r"\n(?=(?:GAP-\d+|## GAP|#gap-|gap:))", text)
    gap_blocks = [b for b in blocks if GAP_ID.search(b)]
    if require_citation:
        uncited = [b[:60] for b in gap_blocks if not CITATION.search(b)]
        if uncited:
            problems.append(f"{len(uncited)} 个缺口块无引用")
    return {"ok": not problems, "problems": problems,
            "n_gaps": len(set(ids)), "n_discriminators": len(discs),
            "n_citations": len(cites)}


# ---------------------------------------------------------------------------
# ④ 方法-代码对齐（s2/audit.py，token-level parity）
# ---------------------------------------------------------------------------
PARITY_MIN_RATIO = 0.80
# 对齐 SciForge s2/audit.py L39-42，并补一条「全大写缩写 / CamelCase 方法名」，
# 因为 AI4Science 论文里方法多写成 EGNN / EGCL / CoorsNorm 而非 snake_case。
_TOKEN_RE = re.compile(
    r"`([A-Za-z_][A-Za-z0-9_]{3,})`|"
    r"\b([a-z]+_[a-z0-9_]{3,})\b|"
    r"\b([a-z]+[A-Z][A-Za-z0-9]+)\b|"
    r"\b([A-Z][A-Z0-9]{2,}|[A-Z][a-z]+[A-Z][A-Za-z0-9]*)\b")
_STOP = {"for_example", "in_order", "and_or", "if_and_only_if", "as_well_as",
         "note_that", "see_also", "for_instance", "such_as", "load_balancing"}


def claimed_tokens(method_text: str) -> List[str]:
    seen: List[str] = []
    for m in _TOKEN_RE.finditer(method_text or ""):
        tok = next((g for g in m.groups() if g), "")
        if tok and tok not in _STOP and tok not in seen:
            seen.append(tok)
    return seen


def method_code_parity(method_text: str, code_text: str) -> Dict[str, Any]:
    """方法段声明的机器 token 有多少真的出现在代码里。

    ``SKIP``：方法段无 token 或没有代码可比；``PASS``：ratio ≥ 0.80。
    """
    tokens = claimed_tokens(method_text)
    if not tokens:
        return {"status": "SKIP", "note": "方法段没有可比对 token"}
    if not (code_text or "").strip():
        return {"status": "SKIP", "note": "无可比对代码"}
    matched = [t for t in tokens if re.search(rf"\b{re.escape(t)}\b", code_text)]
    unmatched = [t for t in tokens if t not in matched]
    code_funcs = sorted(set(re.findall(r"^def ([A-Za-z_][A-Za-z0-9_]+)",
                                       code_text, re.MULTILINE)))
    unmentioned = [f for f in code_funcs
                   if not re.search(rf"\b{re.escape(f)}\b", method_text or "")][:40]
    ratio = len(matched) / len(tokens)
    return {"status": "PASS" if ratio >= PARITY_MIN_RATIO else "FAIL",
            "ratio": round(ratio, 3), "claimed": len(tokens),
            "matched": len(matched), "unmatched": unmatched[:40],
            "unmentioned_functions": unmentioned}


# ---------------------------------------------------------------------------
# ⑤ 内容寻址证据节点（nodes.py 核心）
# ---------------------------------------------------------------------------
def sha256_file(p: str | Path) -> str:
    """文件哈希；传目录时按 *.py 文件名+内容聚合（代码仓库场景）。"""
    h = hashlib.sha256()
    path = Path(p)
    if path.is_dir():
        for f in sorted(path.rglob("*.py")):
            h.update(str(f.relative_to(path)).encode())
            h.update(f.read_bytes())
    elif path.exists():
        h.update(path.read_bytes())
    else:
        h.update(str(path).encode())
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def record_node(*, kind: str, phase: str, code: str | Path,
                inputs: Sequence[Any] = (), outputs: Sequence[Any] = (),
                reexec_cmd: str = "") -> Dict[str, Any]:
    """把一次计算登记成可复验节点（code/inputs/outputs 全哈希）。"""
    code_path = Path(code)
    code_hash = sha256_file(code_path) if code_path.exists() else sha256_text(str(code))
    return {"kind": kind, "phase": phase,
            "code": {"path": str(code), "sha256": code_hash},
            "inputs": [{"sha256": sha256_text(json.dumps(x, ensure_ascii=False,
                                                          sort_keys=True, default=str))}
                       for x in inputs],
            "outputs": [{"sha256": sha256_text(json.dumps(x, ensure_ascii=False,
                                                           sort_keys=True, default=str))}
                        for x in outputs],
            "reexec_cmd": reexec_cmd}


def verify_anchors(nodes: Sequence[Dict[str, Any]]) -> List[str]:
    """重算 code 哈希，漂移即失效（等价 nodes.verify_anchors）。"""
    drift = []
    for i, n in enumerate(nodes):
        info = (n.get("code") or {})
        p = info.get("path")
        if not p or not Path(p).exists():
            continue
        if sha256_file(p) != info.get("sha256"):
            drift.append(f"node[{i}] code drift: {p}")
    return drift
