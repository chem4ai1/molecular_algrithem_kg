"""多智能体协作层.

智能体分工（对应「能力抽取」阶段的多角色协作）：

================  ==================================================
智能体            职责
================  ==================================================
ReaderAgent       通读论文：研究对象、背景、进展、数据集、指标、候选能力
CriticAgent       证据核验：逐条判断能力是否有文本支撑、是否可独立实现
PlannerAgent      方案规划：为一条能力生成多个候选实现方案并打分
CoderAgent        代码生成：按接口契约产出可运行模块
RepairAgent       代码修复：依据报错与历史经验修复
AdvisorAgent      研究方向：结合企业需求与能力全景给出方向建议
================  ==================================================

每个智能体都具备**规则回退**：当 LLM 不可用（离线 / 限流 / 无 Key）时，
使用确定性的启发式实现，保证整条流水线仍然可跑通——这既是鲁棒性要求，
也是「mock LLM 亦可完成核心流程演示」的工程要求。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from ..schema import Capability, Evidence, IOField, MetricSpec, Plan
from ..utils import parse_json_block, truncate
from .client import LLMClient, LLMError, OfflineError, get_client
from .prompts import (
    CODE_GEN,
    CODE_REPAIR,
    CRITIQUE,
    PAPER_EXTRACTION,
    PLANNING,
    RESEARCH_ADVICE,
    SYSTEM_ADVISOR,
    SYSTEM_ANALYST,
    SYSTEM_CODER,
    SYSTEM_CRITIC,
    SYSTEM_PLANNER,
)

logger = logging.getLogger(__name__)


def extract_python_block(text: str) -> str:
    """从 LLM 输出中抽取 Python 代码块。"""
    if not text:
        return ""
    fence = re.search(r"```(?:python|py)?\s*(.*?)```", text, re.DOTALL)
    code = fence.group(1) if fence else text
    code = code.strip()
    if code.startswith("```"):
        code = re.sub(r"^```\w*\n?", "", code)
    code = re.sub(r"\n?```$", "", code)
    return code.strip()


class BaseAgent:
    """智能体基类：统一处理 LLM 不可用时的回退。"""

    name = "base"

    def __init__(self, client: Optional[LLMClient] = None, model: Optional[str] = None):
        self.client = client or get_client()
        self.model = model

    def _ask(self, system: str, user: str, tag: str, max_tokens: Optional[int] = None) -> Optional[Any]:
        try:
            return self.client.complete_json(system, user, model=self.model, tag=tag, max_tokens=max_tokens)
        except (OfflineError, LLMError) as exc:
            logger.warning("[%s] LLM 不可用（%s），使用规则回退", self.name, exc)
            return None


# ---------------------------------------------------------------------------
# Reader
# ---------------------------------------------------------------------------
_KEYWORD_CAPS = [
    ("toxicity", "toxicity prediction"),
    ("hemolytic", "hemolysis prediction"),
    ("antimicrobial", "antimicrobial activity prediction"),
    ("membrane", "membrane interaction modelling"),
    ("structure", "structure prediction"),
    ("docking", "molecular docking"),
    ("generat", "generative design"),
    ("language model", "protein language model representation"),
    ("transformer", "transformer-based sequence encoder"),
    ("random forest", "ensemble tree model"),
    ("support vector", "kernel SVM classifier"),
    ("graph neural", "graph neural network"),
    ("feature", "feature engineering"),
    ("ensemble", "ensemble learning"),
]


class ReaderAgent(BaseAgent):
    """论文理解与能力抽取智能体。"""

    name = "reader"

    def extract(self, *, title: str, abstract: str, year: Optional[int],
                sections: Dict[str, str], code_hint: str = "") -> Dict[str, Any]:
        data = self._try_extract(title, abstract, year, sections, code_hint, max_chars=20000)
        if data is None:
            # 上下文过长导致模型截断/空回复时，退化为「摘要 + 前 3 个章节」的小提示
            logger.info("[reader] 长上下文抽取失败，退化为精简上下文重试")
            small = dict(list(sections.items())[:3])
            data = self._try_extract(title, abstract, year, small, code_hint, max_chars=6000)
        if not isinstance(data, dict):
            return self._fallback(title, abstract, sections)
        # 容错：模型可能把能力放在 techniques / methods / items 等键下
        if not data.get("capabilities"):
            for alt in ("techniques", "methods", "items", "components", "algorithms"):
                if isinstance(data.get(alt), list) and data[alt]:
                    data["capabilities"] = data[alt]
                    logger.info("能力字段名兼容处理：%s → capabilities", alt)
                    break
        if not data.get("capabilities"):
            logger.warning("LLM 抽取结果缺少可用能力，使用规则回退")
            return self._fallback(title, abstract, sections)
        data["_extractor"] = "llm"
        return data

    def _try_extract(self, title: str, abstract: str, year: Optional[int],
                     sections: Dict[str, str], code_hint: str, max_chars: int) -> Optional[Any]:
        section_text = "\n\n".join(
            f"## {name}\n{truncate(text, 4000)}" for name, text in list(sections.items())[:12]
        )
        prompt = PAPER_EXTRACTION.format(
            title=title,
            year=year or "unknown",
            abstract=truncate(abstract, 2500),
            sections=truncate(section_text, max_chars),
            code_hint=code_hint,
        )
        return self._ask(SYSTEM_ANALYST, prompt, tag="paper_extraction")

    # -- 规则回退 ------------------------------------------------------
    def _fallback(self, title: str, abstract: str, sections: Dict[str, str]) -> Dict[str, Any]:
        """基于关键词与章节结构的启发式抽取。"""
        text = f"{title}\n{abstract}\n" + "\n".join(sections.values())
        low = text.lower()
        caps: List[Dict[str, Any]] = []
        for kw, label in _KEYWORD_CAPS:
            if kw in low:
                caps.append({
                    "name": f"Sequence-based {label}",
                    "category": "model",
                    "task": label.replace(" ", "_"),
                    "summary": f"Heuristic capability inferred from keyword '{kw}' in the paper.",
                    "method": (
                        "Represent peptides by amino-acid composition and k-mer frequencies, "
                        "train a supervised classifier, and threshold the predicted probability."
                    ),
                    "inputs": [{"name": "sequences", "dtype": "list[str]", "shape": "[N]",
                                "description": "peptide sequences (one-letter codes)"}],
                    "outputs": [{"name": "probability", "dtype": "float", "shape": "[N]",
                                 "description": "predicted probability of the positive class"}],
                    "metrics": [{"name": "accuracy", "reported": None, "dataset": "paper"}],
                    "conditions": ["labelled peptide dataset available"],
                    "constraints": ["heuristic extraction: not verified against paper details"],
                    "dependencies": ["numpy", "scikit-learn"],
                    "evidence": [{"quote": truncate(abstract, 220), "locator": "Abstract"}],
                    "confidence": 0.35,
                    "tags": [kw],
                })
            if len(caps) >= 3:
                break
        if not caps:
            caps.append({
                "name": "Peptide property classifier",
                "category": "model",
                "task": "peptide_property_prediction",
                "summary": "Generic composition-based peptide property predictor.",
                "method": "Amino-acid composition features + supervised classifier.",
                "inputs": [{"name": "sequences", "dtype": "list[str]", "shape": "[N]"}],
                "outputs": [{"name": "probability", "dtype": "float", "shape": "[N]"}],
                "metrics": [], "conditions": [], "constraints": ["heuristic"],
                "dependencies": ["numpy", "scikit-learn"],
                "evidence": [{"quote": truncate(abstract, 200), "locator": "Abstract"}],
                "confidence": 0.3, "tags": ["heuristic"],
            })
        return {
            "research_object": "peptides" if "peptide" in low else title,
            "background": truncate(abstract, 400),
            "progress": "Not extracted (LLM unavailable).",
            "contributions": [],
            "limitations": [],
            "datasets": [],
            "metrics": [],
            "capabilities": caps,
            "_extractor": "heuristic",
        }


# ---------------------------------------------------------------------------
# Critic
# ---------------------------------------------------------------------------
class CriticAgent(BaseAgent):
    """证据核验与可实现性审查。"""

    name = "critic"

    def review(self, text: str, capabilities: List[Capability]) -> Dict[str, Any]:
        if not capabilities:
            return {"reviews": [], "verdict": "accept"}
        candidates = [
            {"name": c.name, "method": truncate(c.method, 800), "confidence": c.confidence}
            for c in capabilities
        ]
        prompt = CRITIQUE.format(
            text=truncate(text, 9000),
            candidates=json.dumps(candidates, ensure_ascii=False, indent=1),
        )
        data = self._ask(SYSTEM_CRITIC, prompt, tag="critique")
        if not isinstance(data, dict) or "reviews" not in data:
            return self._fallback(capabilities)
        return data

    @staticmethod
    def _fallback(capabilities: List[Capability]) -> Dict[str, Any]:
        """无 LLM 时：依据证据数量与置信度做保守判断。"""
        reviews = []
        for c in capabilities:
            supported = bool(c.evidence) and c.confidence >= 0.4
            reviews.append({
                "name": c.name,
                "supported": supported,
                "implementable": bool(c.method) and len(c.method) > 40,
                "confidence": round(min(c.confidence + 0.05, 0.95), 2),
                "issues": [] if supported else ["insufficient verbatim evidence"],
                "fix": "" if supported else "add evidence from paper text",
            })
        return {"reviews": reviews, "verdict": "revise"}

    @staticmethod
    def apply(capabilities: List[Capability], review: Dict[str, Any]) -> List[Capability]:
        """按审查结果调整置信度，丢弃被判定不可实现的条目。"""
        by_name = {r.get("name", "").strip().lower(): r for r in review.get("reviews", [])}
        kept: List[Capability] = []
        for cap in capabilities:
            r = by_name.get(cap.name.strip().lower())
            if not r:
                cap.confidence = round(min(cap.confidence, 0.6), 2)
                kept.append(cap)
                continue
            if not r.get("implementable", True):
                logger.info("Critic 判定「%s」不可独立实现，移出候选", cap.name)
                continue
            delta = 0.1 if r.get("supported") else -0.2
            cap.confidence = round(max(0.05, min(0.98, cap.confidence * 0.6 + (r.get("confidence") or cap.confidence) * 0.4 + delta)), 2)
            issues = r.get("issues") or []
            if issues:
                cap.constraints = list(dict.fromkeys(cap.constraints + [str(i) for i in issues]))
            kept.append(cap)
        return kept


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------
class PlannerAgent(BaseAgent):
    """多候选方案规划。"""

    name = "planner"

    def plan(self, capability: Capability, references: List[Dict[str, Any]],
             contract: str, max_candidates: int = 3) -> List[Plan]:
        payload = {
            "name": capability.name,
            "task": capability.task,
            "summary": capability.summary,
            "method": truncate(capability.method, 3000),
            "inputs": [asdict(i) for i in capability.inputs],
            "outputs": [asdict(o) for o in capability.outputs],
            "conditions": capability.conditions,
            "constraints": capability.constraints,
        }
        prompt = PLANNING.format(
            capability=json.dumps(payload, ensure_ascii=False, indent=1),
            references=json.dumps(references, ensure_ascii=False, indent=1)[:6000],
            contract=contract,
        )
        data = self._ask(SYSTEM_PLANNER, prompt, tag="planning")
        plans: List[Plan] = []
        if isinstance(data, dict) and isinstance(data.get("plans"), list):
            for i, raw in enumerate(data["plans"][:max_candidates]):
                scores = raw.get("scores") or {}
                detail = {k: self._clamp(scores.get(k, 0.5))
                          for k in ("fidelity", "feasibility", "robustness", "cost")}
                plans.append(Plan(
                    id=f"plan_{capability.id[-6:]}_{i}",
                    capability_id=capability.id,
                    name=str(raw.get("name") or f"plan-{i}"),
                    approach=str(raw.get("approach") or ""),
                    steps=[str(s) for s in raw.get("steps") or []],
                    libraries=[str(s) for s in raw.get("libraries") or []],
                    rationale=str(raw.get("rationale") or ""),
                    risks=[str(s) for s in raw.get("risks") or []],
                    expected_metrics={k: float(v) for k, v in (raw.get("expected_metrics") or {}).items()
                                      if isinstance(v, (int, float))},
                    score_detail=detail,
                ))
        if not plans:
            plans = self._fallback(capability, max_candidates)
        for p in plans:
            p.score = self.score(p.score_detail)
        plans.sort(key=lambda p: p.score, reverse=True)
        return plans

    @staticmethod
    def _clamp(value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.5

    @staticmethod
    def score(detail: Dict[str, Any]) -> float:
        """加权评分：保真度 0.45、可行性 0.35、鲁棒性 0.15、成本 0.05（成本越低越好）。"""
        def g(k: str, default: float) -> float:
            try:
                return max(0.0, min(1.0, float(detail.get(k, default))))
            except (TypeError, ValueError):
                return default
        fidelity = g("fidelity", 0.6)
        feasibility = g("feasibility", 0.7)
        robustness = g("robustness", 0.5)
        cost = 1.0 - g("cost", 0.3)
        return round(0.45 * fidelity + 0.35 * feasibility + 0.15 * robustness + 0.05 * cost, 4)

    def _fallback(self, capability: Capability, n: int) -> List[Plan]:
        """无 LLM 时的三个标准方案（也是 CoderAgent 模板的输入）。"""
        base = [
            {
                "name": "Amino-acid composition + linear model",
                "approach": "20-dim AAC features + class-balanced logistic regression",
                "steps": ["compute AAC", "standardize", "logistic regression", "threshold 0.5"],
                "libraries": ["numpy", "scikit-learn"],
                "rationale": "Classic peptide property baseline; fast and interpretable.",
                "risks": ["ignores sequence order"],
                "scores": {"fidelity": 0.55, "feasibility": 0.95, "robustness": 0.7, "cost": 0.1},
                "expected_metrics": {"accuracy": 0.7},
                "feature_mode": "aac",
            },
            {
                "name": "Dipeptide composition + ensemble",
                "approach": "400-dim DPC features + gradient boosting / random forest",
                "steps": ["compute DPC", "random forest", "probability calibration"],
                "libraries": ["numpy", "scikit-learn"],
                "rationale": "Dipeptide composition is the de-facto standard in peptide toxicity prediction.",
                "risks": ["high dimensionality on small data"],
                "scores": {"fidelity": 0.8, "feasibility": 0.9, "robustness": 0.65, "cost": 0.25},
                "expected_metrics": {"accuracy": 0.8},
                "feature_mode": "dpc",
            },
            {
                "name": "Hybrid k-mer + physicochemical descriptors",
                "approach": "AAC + DPC + length/charge/hydrophobicity + regularized linear SVM",
                "steps": ["compute hybrid features", "standardize", "linear SVM", "Platt scaling"],
                "libraries": ["numpy", "scikit-learn"],
                "rationale": "Adds physicochemical priors known to govern peptide toxicity/activity.",
                "risks": ["feature scaling sensitive"],
                "scores": {"fidelity": 0.85, "feasibility": 0.85, "robustness": 0.75, "cost": 0.3},
                "expected_metrics": {"accuracy": 0.82},
                "feature_mode": "hybrid",
            },
        ]
        plans = []
        for i, b in enumerate(base[:n]):
            plans.append(Plan(
                id=f"plan_{capability.id[-6:]}_{i}",
                capability_id=capability.id,
                name=b["name"], approach=b["approach"], steps=b["steps"],
                libraries=b["libraries"], rationale=b["rationale"], risks=b["risks"],
                expected_metrics=b["expected_metrics"], score_detail=b["scores"],
            ))
        return plans


# ---------------------------------------------------------------------------
# Coder
# ---------------------------------------------------------------------------
class CoderAgent(BaseAgent):
    """代码生成智能体。"""

    name = "coder"

    def generate(self, capability: Capability, plan: Plan, contract: str,
                 code_refs: str = "") -> str:
        payload = {
            "name": capability.name, "task": capability.task, "summary": capability.summary,
            "method": truncate(capability.method, 3500),
            "inputs": [asdict(i) for i in capability.inputs],
            "outputs": [asdict(o) for o in capability.outputs],
            "dependencies": capability.dependencies,
        }
        prompt = CODE_GEN.format(
            capability=json.dumps(payload, ensure_ascii=False, indent=1),
            plan=json.dumps(plan.to_dict(), ensure_ascii=False, indent=1),
            contract=contract,
            code_refs=truncate(code_refs, 6000) or "(none)",
        )
        try:
            resp = self.client.chat(
                [{"role": "system", "content": SYSTEM_CODER}, {"role": "user", "content": prompt}],
                model=self.model, tag="code_gen",
            )
            code = extract_python_block(resp.text)
            if code and "def featurize" in code and "def build_model" in code:
                return code
            logger.warning("LLM 生成代码不满足契约，使用模板回退")
        except (OfflineError, LLMError) as exc:
            logger.warning("[coder] LLM 不可用（%s），使用模板回退", exc)
        return template_solution(capability, plan)


class RepairAgent(BaseAgent):
    """代码修复智能体。"""

    name = "repair"

    def repair(self, capability: Capability, contract: str, code: str,
               stage: str, error: str, lessons: List[str]) -> Optional[str]:
        prompt = CODE_REPAIR.format(
            capability=json.dumps({"name": capability.name, "method": truncate(capability.method, 2000)},
                                  ensure_ascii=False),
            contract=contract,
            code=truncate(code, 12000),
            stage=stage,
            error=truncate(error, 4000),
            lessons="\n".join(f"- {l}" for l in lessons) or "(none)",
        )
        try:
            resp = self.client.chat(
                [{"role": "system", "content": SYSTEM_CODER}, {"role": "user", "content": prompt}],
                model=self.model, tag="code_repair",
            )
            fixed = extract_python_block(resp.text)
            if fixed and "def featurize" in fixed and "def build_model" in fixed:
                return fixed
        except (OfflineError, LLMError) as exc:
            logger.warning("[repair] LLM 不可用：%s", exc)
        return None


# ---------------------------------------------------------------------------
# Advisor
# ---------------------------------------------------------------------------
class AdvisorAgent(BaseAgent):
    """研究方向建议智能体。"""

    name = "advisor"

    def advise(self, needs: List[str], landscape: List[Dict[str, Any]],
               papers: List[Dict[str, Any]],
               coverage: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        prompt = RESEARCH_ADVICE.format(
            needs="\n".join(f"- {n}" for n in needs),
            landscape=json.dumps(landscape[:14], ensure_ascii=False, indent=1)[:5000],
            papers=json.dumps(papers[:6], ensure_ascii=False, indent=1)[:5000],
        )
        data = self._ask(SYSTEM_ADVISOR, prompt, tag="research_advice", max_tokens=9000)
        if isinstance(data, dict):
            for key in ("directions", "recommendations", "items", "research_directions"):
                if isinstance(data.get(key), list) and data[key]:
                    return data[key]
            logger.warning("[advisor] LLM 输出缺少 directions 字段，keys=%s", list(data)[:6])
        elif isinstance(data, list) and data:
            return data
        return self._fallback(needs, landscape, coverage)

    def _fallback(self, needs: List[str], landscape: List[Dict[str, Any]],
                  coverage: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """规则兜底：仅对「覆盖不足」的需求生成方向，已被验证的需求不再列为空白。"""
        status_map: Dict[str, Dict[str, Any]] = {}
        if coverage:
            for item in coverage.get("needs", []):
                status_map[item.get("need", "")] = item
        targets = []
        for need in needs:
            info = status_map.get(need)
            status = (info or {}).get("status", "gap")
            if status == "covered":
                continue
            targets.append((need, status, info or {}))
        if not targets:  # 全部已覆盖 → 给出「深化/拓展」类方向
            targets = [(n, "covered", status_map.get(n, {})) for n in needs[:2]]

        out: List[Dict[str, Any]] = []
        for i, (need, status, info) in enumerate(targets):
            matched = info.get("matched") or []
            base_cap = matched[0]["name"] if matched else "（暂无对应能力）"
            if status == "partial":
                title = f"{need}：从「部分覆盖」走向可验证的专用能力"
                gap = (f"最相近的能力是「{base_cap}」，但相关度 {info.get('relevance', 0):.2f} / "
                       f"成熟度 {info.get('maturity', 0):.2f}，尚未针对性验证")
                exps = [
                    f"以「{base_cap}」为基线，在 {need} 的公开标注数据上做零样本迁移评测",
                    f"补充 {need} 相关的特征/标签体系，复刻 2 条公开方法并统一评测协议",
                    "在自有多肽库上做外部验证，报告分布偏移下的性能",
                ]
                diff = "low" if info.get("maturity", 0) > 0.5 else "medium"
            else:
                title = f"{need}：构建从数据到模型的完整能力"
                gap = f"能力图谱中缺少与「{need}」直接对应的可执行能力"
                exps = [
                    f"收集 {need} 的公开标注数据并做去泄漏划分",
                    f"复刻 2-3 条公开算法并统一评测",
                    "在自有多肽库上做外部验证",
                ]
                diff = "high"
            out.append({
                "title": title,
                "gap": gap,
                "rationale": f"企业管线需要「{need}」，当前覆盖状态为 {status}，属于可优先补齐的能力缺口。",
                "supporting_capabilities": [base_cap] if base_cap else [],
                "required_capabilities": [need],
                "experiments": exps,
                "expected_impact": "形成可复用的预测/筛选模块，支撑管线早期决策",
                "difficulty": diff,
                "priority": round(max(0.45, 0.9 - 0.06 * i - (0.2 if status == "partial" else 0)), 2),
                "references": [],
            })
        return out[:6]


# ---------------------------------------------------------------------------
# 模板代码（离线 / 兜底 / 基线）
# ---------------------------------------------------------------------------
_TEMPLATE = '''"""Auto-generated peptide property predictor.

Capability : {cap_name}
Plan       : {plan_name}
Strategy   : {plan_approach}
Generated by CapFactory (template fallback).
"""
from __future__ import annotations

import numpy as np

TASK_TYPE = "sequence_binary_classification"
CAPABILITY_ID = "{cap_id}"

AA = "ACDEFGHIKLMNPQRSTVWY"
AA_INDEX = {{a: i for i, a in enumerate(AA)}}
FEATURE_MODE = "{feature_mode}"  # aac | dpc | hybrid

# Kyte-Doolittle hydropathy (normalised below), used by the hybrid descriptor.
HYDROPATHY = {{
    "A": 1.8, "R": -4.5, "N": -3.5, "D": -3.5, "C": 2.5, "Q": -3.5, "E": -3.5,
    "G": -0.4, "H": -3.2, "I": 4.5, "L": 3.8, "K": -3.9, "M": 1.9, "F": 2.8,
    "P": -1.6, "S": -0.8, "T": -0.7, "W": -0.9, "Y": -1.3, "V": 4.2,
}}


def clean_sequence(seq: str) -> str:
    """Normalise a peptide sequence: uppercase, keep canonical amino acids only."""
    if not isinstance(seq, str):
        return ""
    return "".join(ch for ch in seq.upper() if ch in AA_INDEX)


def aac_features(seq: str) -> np.ndarray:
    """Amino-acid composition (20 dims). Unknown characters are dropped."""
    seq = clean_sequence(seq)
    vec = np.zeros(len(AA), dtype=np.float32)
    if not seq:
        return vec
    for ch in seq:
        vec[AA_INDEX[ch]] += 1.0
    return vec / len(seq)


def dpc_features(seq: str) -> np.ndarray:
    """Dipeptide composition (400 dims)."""
    seq = clean_sequence(seq)
    vec = np.zeros(len(AA) * len(AA), dtype=np.float32)
    if len(seq) < 2:
        return vec
    for i in range(len(seq) - 1):
        idx = AA_INDEX[seq[i]] * len(AA) + AA_INDEX[seq[i + 1]]
        vec[idx] += 1.0
    return vec / (len(seq) - 1)


def physchem_features(seq: str) -> np.ndarray:
    """Length, net charge, mean hydropathy, hydrophobic ratio, aromatic ratio."""
    seq = clean_sequence(seq)
    if not seq:
        return np.zeros(5, dtype=np.float32)
    h = np.array([HYDROPATHY.get(ch, 0.0) for ch in seq], dtype=np.float32)
    charge = sum(1 for ch in seq if ch in "KR") - sum(1 for ch in seq if ch in "DE")
    return np.array([
        len(seq) / 50.0,
        charge / max(len(seq), 1),
        float(h.mean()) / 4.5,
        float((h > 0).mean()),
        sum(1 for ch in seq if ch in "FWY") / len(seq),
    ], dtype=np.float32)


def featurize(sequences):
    """Convert a list of peptide sequences into a 2-D feature matrix."""
    if sequences is None:
        return np.zeros((0, len(AA)), dtype=np.float32)
    if isinstance(sequences, str):
        sequences = [sequences]
    rows = []
    for seq in sequences:
        if FEATURE_MODE == "aac":
            rows.append(aac_features(seq))
        elif FEATURE_MODE == "dpc":
            rows.append(dpc_features(seq))
        else:
            rows.append(np.concatenate([aac_features(seq), dpc_features(seq), physchem_features(seq)]))
    return np.vstack(rows).astype(np.float32) if rows else np.zeros((0, 0), dtype=np.float32)


def build_model(**kwargs):
    """Return a scikit-learn compatible estimator (fit / predict_proba)."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    if FEATURE_MODE == "aac":
        clf = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42)
        return Pipeline([("scaler", StandardScaler()), ("clf", clf)])
    if FEATURE_MODE == "hybrid":
        clf = LogisticRegression(max_iter=3000, class_weight="balanced", C=1.0, random_state=42)
        return Pipeline([("scaler", StandardScaler()), ("clf", clf)])
    return RandomForestClassifier(
        n_estimators=int(kwargs.get("n_estimators", 300)),
        min_samples_leaf=int(kwargs.get("min_samples_leaf", 1)),
        class_weight="balanced_subsample",
        random_state=42,
        n_jobs=1,
    )


if __name__ == "__main__":
    demo = ["FLGALFKALSKLL", "GIGKFLHSAKKFGKAFVGEIMNS"]
    model = build_model()
    model.fit(featurize(demo), np.array([0, 1]))
    print("smoke:", model.predict_proba(featurize(demo))[:, 1])
'''


def template_solution(capability: Capability, plan: Plan) -> str:
    """按方案生成模板代码（离线可用，同时作为 LLM 生成的对照组基线）。"""
    mode = "dpc"
    name = (plan.name + " " + plan.approach).lower()
    if "composition + linear" in name or "aac" in name:
        mode = "aac"
    elif "hybrid" in name or "physicochemical" in name:
        mode = "hybrid"
    return _TEMPLATE.format(
        cap_name=capability.name,
        plan_name=plan.name,
        plan_approach=plan.approach,
        cap_id=capability.id,
        feature_mode=mode,
    )
