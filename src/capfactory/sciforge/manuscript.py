"""论文生成侧的确定性门（SciForge Phase 10–16 的最小可移植子集）。

四件事，全部是**脚本门**，不把判定交给 LLM：

1. ``claim_anchor`` / ``verify_claim_anchors`` —— claim 锚到实验节点的字节；
2. ``fidelity_gate`` —— 三档保真度 + 极性 + 允许措辞；
3. ``figure_spec`` / ``figure_audit`` —— LLM 只写数据，布局由渲染器锁死；
4. ``blind_review`` / ``e2e_smoke`` —— 冻结 rubric、角色隔离、产物集合双向相等。

LLM 在这套设计里只负责写 ``prompt / spec 内容 / 章节文字``，
**判「能不能写、写了算不算」的一律是这里的代码**。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from ..ontology.generation import (FIDELITY, POLARITY, ALLOWED_WORDING,
                                    RUBRIC_AXES)
from .contracts import verdict, sha256_text

# ---------------------------------------------------------------------------
# ① Claim 三角形
# ---------------------------------------------------------------------------
def claim_anchor(*, claim_id: str, node_id: str, experiment_node: Dict[str, Any],
                 tex_file: str = "", line: int = 0,
                 observation_ids: Sequence[str] = ()) -> Dict[str, Any]:
    """把一条主张锚到 ``ExperimentNode`` 的 code/inputs/outputs 哈希。"""
    code = (experiment_node.get("code") or {})
    return {
        "claim_id": claim_id, "node_id": node_id,
        "tex_file": tex_file, "line": line,
        "code_sha": code.get("sha256", ""),
        "inputs_sha": experiment_node.get("inputs_sha", ""),
        "outputs_sha": experiment_node.get("outputs_sha", ""),
        "evidence_refs": [f"sha256:{code.get('sha256','')}"] + list(observation_ids),
        "resolved": bool(code.get("sha256")),
        "drift": "",
    }


def verify_claim_anchors(anchors: Sequence[Dict[str, Any]],
                         nodes: Dict[str, Dict[str, Any]]) -> List[str]:
    """重算哈希：结果事后被改动 → 锚失效（SciForge verify_anchors 语义）。"""
    problems: List[str] = []
    for a in anchors:
        n = nodes.get(a.get("node_id", ""))
        if n is None:
            problems.append(f"{a.get('claim_id')}: 实验节点不存在")
            continue
        live = (n.get("code") or {}).get("sha256", "")
        if live != a.get("code_sha"):
            problems.append(f"{a.get('claim_id')}: code drift（结果改动后锚失效）")
        if n.get("outputs_sha") != a.get("outputs_sha"):
            problems.append(f"{a.get('claim_id')}: outputs drift")
        if not a.get("resolved"):
            problems.append(f"{a.get('claim_id')}: unresolved")
    return problems


# ---------------------------------------------------------------------------
# ② 主张保真度
# ---------------------------------------------------------------------------
_WORDING_STRONG = re.compile(r"\b(proven|established|demonstrated|prove)\b", re.I)
_WORDING_MED = re.compile(r"\b(supported|validated|confirmed)\b", re.I)
_LEAK = re.compile(
    r"\b(phase\s*\d+|verdict|render_figure|pipeline|GAP-\d+|skill|kernel|"
    r"smoke_gate|s2_ladder|run_id|prompt|bundle)\b", re.I)


def fidelity_gate(*, claim_text: str, fidelity: str, polarity: str,
                  in_abstract: bool = False) -> Dict[str, Any]:
    """三档保真度 + 极性 + 越级措辞检测。

    SciForge: "Never label proven without symbolic, never supported without
    numerical fidelity"；只有 positive 能进 Abstract/contributions。
    """
    problems: List[str] = []
    if fidelity not in FIDELITY:
        problems.append(f"fidelity 非法 {fidelity!r}")
    if polarity not in POLARITY:
        problems.append(f"polarity 非法 {polarity!r}")
    low = claim_text or ""
    if _WORDING_STRONG.search(low) and fidelity != "symbolic":
        problems.append("措辞越级：'proven/established' 需要 symbolic 推导")
    if _WORDING_MED.search(low) and fidelity == "qualitative":
        problems.append("措辞越级：'supported' 至少需要 numerical")
    if in_abstract and polarity != "positive":
        problems.append(f"极性 {polarity} 不得进 Abstract / contributions")
    allowed = ALLOWED_WORDING.get(fidelity, ())
    return verdict("PASS" if not problems else "FAIL",
                   notes="; ".join(problems) or f"fidelity={fidelity} ok",
                   artifacts=["CLAIMS_FROM_RESULTS"]) | {
                       "fidelity": fidelity, "polarity": polarity,
                       "allowed_wording": list(allowed), "problems": problems}


def leakage_scrub(text: str) -> Dict[str, Any]:
    """把流水线内部术语从正文里检出（不自动改，交回 LLM 重写）。"""
    hits = sorted({m.group(0) for m in _LEAK.finditer(text or "")})
    return {"verdict": verdict("PASS" if not hits else "FAIL",
                               notes=f"检出 {len(hits)} 个内部术语"),
            "hits": hits}


# ---------------------------------------------------------------------------
# ③ 图：LLM 写 spec，渲染器锁布局
# ---------------------------------------------------------------------------
FIGURE_ARCHETYPES = ("comparison", "ablation", "trajectory", "architecture",
                     "distribution", "correlation")


def figure_spec(*, claim: str, archetype: str,
                observation_ids: Sequence[str], data: Dict[str, Any],
                caption: str = "") -> Dict[str, Any]:
    """生成机器可渲染的图 spec。

    **刻意不含** 字体/色板/坐标/布局字段——这些由渲染器决定，LLM 无布局自由度。
    """
    problems: List[str] = []
    if not claim:
        problems.append("缺 claim")
    if archetype not in FIGURE_ARCHETYPES:
        problems.append(f"未知 archetype {archetype!r}")
    if not observation_ids:
        problems.append("图必须嵌入至少一个 Observation")
    if not data:
        problems.append("缺数据")
    spec = {"claim": claim, "archetype": archetype,
            "observation_ids": list(observation_ids), "data": data,
            "caption": caption, "layout_locked": True}
    return {"spec": spec, "spec_sha": sha256_text(json.dumps(spec, sort_keys=True)),
            "verdict": verdict("PASS" if not problems else "FAIL",
                               notes="; ".join(problems))}


def figure_audit(spec: Dict[str, Any], *, caption: str = "") -> Dict[str, Any]:
    """最小图审计：无布局自由度、caption 在图之后写、误差语义必须定义。"""
    problems: List[str] = []
    if not spec.get("layout_locked"):
        problems.append("布局未锁定")
    if not spec.get("observation_ids"):
        problems.append("无观测数据引用")
    if caption and not re.search(r"(±|SD|CI|seed|error bar|n\s*=)", caption, re.I):
        problems.append("caption 未定义误差语义 / 样本数")
    return {"verdict": verdict("PASS" if not problems else "WARN",
                               notes="; ".join(problems)),
            "checks": ["A1 outputs", "A2 data", "A3 caption"]}


# ---------------------------------------------------------------------------
# ④ 独立盲审 + 端到端验收
# ---------------------------------------------------------------------------
def blind_review(*, scores: Dict[str, float], role: str = "reviewer",
                 reread_from_files: bool = True,
                 cap: float = 84.0) -> Dict[str, Any]:
    """冻结 6 轴权重；reviewer 必须重读文件、看不到 researcher 推理。"""
    problems: List[str] = []
    missing = set(RUBRIC_AXES) - set(scores)
    if missing:
        problems.append(f"缺轴 {sorted(missing)}")
    if not reread_from_files:
        problems.append("违反 re-read don't recall")
    raw = sum(RUBRIC_AXES[k] * float(scores.get(k, 0)) * 10
              for k in RUBRIC_AXES)  # 各轴 1–10 分 → 加权到 100
    overall = min(raw, cap)
    if overall > 85 and len(scores) < len(RUBRIC_AXES):
        problems.append(">85 分需逐轴证据")
    state = "PASS" if overall >= 60 and not problems else "FAIL"
    return {"verdict": verdict(state, notes="; ".join(problems)),
            "overall": round(overall, 2), "raw": round(raw, 2),
            "cap": cap, "rubric": dict(RUBRIC_AXES), "role": role}


def pin_hash(text: str, *, name: str = "PIN") -> Dict[str, Any]:
    return {"name": name, "sha256": hashlib.sha256(text.encode()).hexdigest()}


def e2e_smoke(*, expected: Iterable[str], actual: Iterable[str],
              pins: Sequence[Tuple[str, str, str]] = (),
              double_run_equal: bool = True) -> Dict[str, Any]:
    """SciForge test_e2e_smoke 的最小复刻：产物集合双向相等 + hash 重算 + 双跑确定。"""
    e, a = set(expected), set(actual)
    missing, extra = sorted(e - a), sorted(a - e)
    drift = [n for n, expected_hash, live in pins if expected_hash != live]
    if not double_run_equal:
        drift.append("double_run")
    problems = ([f"缺产物 {missing}"] if missing else []) + \
               ([f"多产物 {extra}"] if extra else []) + \
               ([f"hash/双跑漂移 {drift}"] if drift else [])
    return {"verdict": verdict("PASS" if not problems else "FAIL",
                               notes="; ".join(problems) or "产物集合与哈希一致"),
            "expected": len(e), "actual": len(a),
            "missing": missing, "extra": extra, "drift": drift}
