"""P2/P3：算法库填充 + 两阶段抽取器（先判类别 → 按族 schema 抽）。

判定权在规则：LLM 只能在封闭族词表 / 字段枚举里选，越界值丢弃。
"""
from __future__ import annotations
import json, re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .algorithm_schema import (FAMILIES, COMMON, classify_rule, schema_for,
                               enum_values, FAMILY_IDS)

OUT = Path("storage_cf/sciforge/algorithm_fill_report.json")

# 基于算法认知的已知属性（真实机制，非编造；不确定的留 unknown）
KNOWN: Dict[str, Dict[str, Any]] = {
    "MolMiner": {"family": "fragment", "fields": {
        "fragment_vocab": "RDKit 环与孤立键切分得到的片段词表",
        "decomposition_rule": "环+键切分",
        "attachment_points": "开放连接点 + 对称性规范化映射",
        "symmetry_handling": "规范化映射", "geometry_aware": "是"}},
    "ChemicalVAE": {"family": "vae", "fields": {
        "representation": "SMILES", "encoder": "CNN/MLP",
        "decoder": "SMILES RNN", "prior": "标准正态"}},
    "SchNet": {"family": "geometric_gnn", "fields": {
        "message_passing": "连续滤波卷积", "equivariance_group": "不变但不等变",
        "invariant_features": "原子间距离", "prediction_target": "能量+力"}},
    "SO3LR Tauri": {"family": "geometric_gnn", "fields": {
        "message_passing": "SO3krates 等变消息传递",
        "equivariance_group": "SO(3)", "radial_basis": "Gaussian",
        "prediction_target": "能量+力"}},
    "SO3LR": {"family": "geometric_gnn", "fields": {
        "equivariance_group": "SO(3)", "prediction_target": "能量+力"}},
    "OPLS4": {"family": "classical_forcefield", "fields": {
        "potential_form": "键伸缩/角/二面 + Lennard-Jones + 库仑",
        "parameterization": "量子化学与实验数据拟合", "polarizable": "否"}},
    "GAFF": {"family": "classical_forcefield", "fields": {
        "potential_form": "简谐键/角/二面 + LJ + 库仑",
        "parameterization": "经验/量子化学拟合", "polarizable": "否"}},
    "MACE-POLAR-1-M": {"family": "geometric_gnn", "fields": {
        "message_passing": "高阶等变消息传递 (MACE)",
        "equivariance_group": "E(n)", "prediction_target": "能量+力"}},
    "AIMNet2-2025": {"family": "geometric_gnn", "fields": {
        "message_passing": "神经网络势消息传递",
        "prediction_target": "能量+力"}},
    "UMA-S-1.2.1": {"family": "geometric_gnn", "fields": {
        "prediction_target": "能量+力"}},
    "AntiFold": {"family": "autoregressive", "fields": {
        "representation": "氨基酸序列", "architecture_variant": "encoder-decoder",
        "decoding": "temperature sampling"}},
    "ESM-IF1": {"family": "autoregressive", "fields": {
        "representation": "氨基酸序列", "architecture_variant": "encoder-decoder"}},
    "AbMPNN": {"family": "geometric_gnn", "fields": {
        "message_passing": "图消息传递", "prediction_target": "序列/残基"}},
    "ProteinMPNN": {"family": "geometric_gnn", "fields": {
        "message_passing": "图消息传递", "prediction_target": "序列/残基"}},
    "AMP-Designer": {"family": "autoregressive", "fields": {
        "representation": "氨基酸序列", "architecture_variant": "decoder-only"}},
    "AMP-GPT": {"family": "autoregressive", "fields": {
        "representation": "氨基酸序列", "architecture_variant": "decoder-only",
        "pretrain_objective": "CLM"}},
    "AMP-Prompt": {"family": "instruction_tuning", "fields": {
        "base_model": "AMP-GPT", "tuning_method": "prefix/prompt tuning"}},
    "AMP-Distillation": {"family": "instruction_tuning", "fields": {
        "base_model": "AMP-GPT", "tuning_method": "蒸馏",
        "instruction_source": "AMP-GPT 生成样本"}},
    "AMP-MIC": {"family": "autoregressive", "fields": {
        "representation": "氨基酸序列", "architecture_variant": "decoder-only"}},
    "CLaSS": {"family": "classifier_guidance", "fields": {
        "condition_type": "活性标签", "screening": "分类器筛选"}},
    "CFPS": {"family": "wetlab", "fields": {
        "wet_lab_method": "细胞游离蛋白合成"}},
    "Condition Token (CT)": {"family": "instruction_tuning", "fields": {
        "tuning_method": "condition token", "base_model": "AMP-GPT"}},
    "Fine-Tuning (FT)": {"family": "instruction_tuning", "fields": {
        "tuning_method": "全量微调", "base_model": "AMP-GPT"}},
    "Huang et al. RNN": {"family": "rnn", "fields": {
        "cell_type": "vanilla RNN", "representation": "氨基酸序列"}},
    "Lingo3DMol": {"family": "autoregressive", "fields": {
        "representation": "3D 坐标", "architecture_variant": "encoder-decoder",
        "decoding": "beam search"}},
    "Pocket2Mol": {"family": "geometric_gnn", "fields": {
        "message_passing": "口袋条件图消息传递",
        "prediction_target": "结构/坐标"}},
    "TargetDiff": {"family": "diffusion", "fields": {
        "discrete_or_continuous": "连续坐标扩散",
        "conditioning": "口袋条件", "score_network": "等变 GNN"}},
    "Mol-Instructions": {"family": "autoregressive", "fields": {
        "representation": "文本/指令", "architecture_variant": "decoder-only"}},
    "LLaMA": {"family": "autoregressive", "fields": {
        "representation": "文本/指令", "architecture_variant": "decoder-only",
        "pretrain_objective": "CLM"}},
    "Stanford Alpaca": {"family": "autoregressive", "fields": {
        "representation": "文本/指令", "architecture_variant": "decoder-only"}},
    "GPT4All": {"family": "autoregressive", "fields": {
        "representation": "文本/指令", "architecture_variant": "decoder-only"}},
    "MOLGEN": {"family": "autoregressive", "fields": {
        "representation": "SELFIES",
        "architecture_variant": "bidirectional+autoregressive",
        "pretrain_objective": "掩码重建 + 自回归"}},
    "SMILES-based PLMs": {"family": "autoregressive", "fields": {
        "representation": "SMILES", "architecture_variant": "encoder-decoder"}},
    "Langevin Speculative Dynamics": {"family": "speculative_sampling",
        "fields": {"proposal_kernel": "Langevin 动力学",
                   "verification": "精确校验"}},
}


def _uniform(family: str, values: Dict[str, Any]) -> Dict[str, Any]:
    """统一同族属性集合：schema 里每个字段都出现，缺失填 unknown。"""
    sch = schema_for(family)
    out: Dict[str, Any] = {"schema_family": family,
                           "schema_label": sch.get("label", ""),
                           "schema_version": "v1"}
    for k in sch.get("all_fields", {}):
        v = values.get(k)
        if v in (None, "", []):
            v = "unknown"
        out[k] = v
    return out


def fill_library(graph: Any, *, persist: bool = True) -> Dict[str, Any]:
    """为全部 Algorithm 节点判族 + 按族 schema 统一属性。"""
    from .facets_v7 import classify_algorithm
    rep: Dict[str, Any] = {"n_algorithms": 0, "by_family": {},
                           "n_fields_written": 0,
                           "unclassified": [], "sources": {}}
    for n in graph.by_type("Algorithm"):
        fam = (KNOWN.get(n.label, {}).get("family") or
               classify_rule(n.label,
                             str(n.attrs.get("architecture") or "")))
        if not fam:
            rep["unclassified"].append(n.id)
            continue
        f = classify_algorithm(graph, n.id)
        base = {"name": n.label, "role": f.get("role", "unknown"),
                "object_kind": f.get("object", "unknown"),
                "task_kind": f.get("task", "unknown"),
                "modality": f.get("modality", "unknown"),
                "paper_ids": n.attrs.get("paper_ids") or [],
                "evidence": n.attrs.get("description") or "unknown"}
        base.update(KNOWN.get(n.label, {}).get("fields") or {})
        for k, src in (("object_kind", "llm_object"),
                       ("task_kind", "llm_task"),
                       ("modality", "llm_modality")):
            if n.attrs.get(src):
                base[k] = n.attrs[src]
        uniform = _uniform(fam, base)
        n.attrs.update(uniform)
        rep["n_algorithms"] += 1
        rep["n_fields_written"] += len(uniform)
        rep["by_family"][fam] = rep["by_family"].get(fam, 0) + 1
        rep["sources"][n.id] = ("knowledge" if n.label in KNOWN
                                else "rule_classify")
    if persist:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        graph.save("storage_cf/sciforge/batch10_final_graph.json")
    return rep


CLASSIFY_PROMPT = """你是算法族判定器。只根据算法名称与上下文，从封闭词表里选**一个**类别，
输出严格 JSON（纯 JSON，不要代码块）：
{"family_id":"","confidence":0.9,"evidence":"逐字引文"}
词表：{families}
规则：只能选词表里的 id；判断不了输出 {"family_id":"unknown"}；
evidence 必须从【上下文】逐字复制 ≤100 字。
【算法名】{name}
【上下文】{context}
"""

EXTRACT_PROMPT = """你是「{label}」算法属性抽取器。
该类算法特征：{description}
只基于【论文片段】抽取下面字段，输出严格 JSON（纯 JSON，不要代码块）：
{fields}
规则：
1. 枚举字段只能从给定候选里选；没有依据就填 "unknown"，禁止编造。
2. 文本字段 ≤60 字；evidence 必须是【论文片段】里的逐字短句（≤100 字）。
3. 不要输出词表外的字段。
【算法名】{name}
【论文片段】{text}
"""


def _norm_ev(s: str) -> str:
    s = re.sub(r"-\s*\n\s*", "", str(s or ""))
    s = re.sub(r"-\s+(?=[a-z])", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower().replace("’", "'").replace("–", "-")


def _validate(family: str, data: Dict[str, Any], text: str = ""
              ) -> List[str]:
    issues: List[str] = []
    enums = enum_values(family)
    specs = schema_for(family).get("all_fields", {})
    for k, v in (data or {}).items():
        if k not in specs:
            issues.append(f"unknown_field:{k}")
            continue
        spec = specs[k]
        if spec.get("type") == "list":
            if not isinstance(v, list):
                issues.append(f"needs_list:{k}")
            continue
        if k in enums and v not in enums[k] and v != "unknown":
            issues.append(f"bad_enum:{k}={v}")
        if isinstance(v, (dict, list)):
            issues.append(f"bad_type:{k}")
        elif isinstance(v, str) and len(v) > 120 and k != "evidence":
            issues.append(f"too_long:{k}")
    ev = str((data or {}).get("evidence") or "")
    if ev and text and ev != "unknown" and \
            _norm_ev(ev) not in _norm_ev(text) and \
            _norm_ev(ev)[:60] not in _norm_ev(text):
        issues.append("evidence_not_verbatim")
    return issues


def classify_family(name: str, context: str = "", *, chat_fn: Any = None,
                    use_llm: bool = True) -> Dict[str, Any]:
    """阶段 1：规则优先，规则不中才让 LLM 从封闭 14 类里选。"""
    fam = classify_rule(name)      # 只用名称+架构，避免全文 context 污染
    if fam:
        return {"family_id": fam, "source": "rule",
                "label": FAMILIES[fam]["label"], "confidence": 1.0}
    if not use_llm:
        return {"family_id": "unknown", "source": "none",
                "label": "未分类", "confidence": 0.0}
    from ..llm.backends import chat as _chat
    from ..utils import parse_llm_json
    fn = chat_fn or (lambda p, **kw: _chat(p, backend="vllm", **kw))
    prompt = (CLASSIFY_PROMPT.replace("{families}", ", ".join(FAMILY_IDS))
              .replace("{name}", name)
              .replace("{context}", (context or "")[:1600]))
    try:
        d = parse_llm_json(fn(prompt, max_tokens=600, timeout=180)) or {}
        fid = str(d.get("family_id") or "unknown")
        if fid not in FAMILIES:
            fid = "unknown"
        return {"family_id": fid, "source": "llm",
                "label": FAMILIES.get(fid, {}).get("label", "未分类"),
                "confidence": d.get("confidence"),
                "evidence": d.get("evidence")}
    except Exception as exc:  # noqa: BLE001
        return {"family_id": "unknown", "source": "error",
                "label": "未分类",
                "error": f"{type(exc).__name__}:{exc}"[:120]}


def extract_by_family(name: str, family: str, text: str, *,
                      chat_fn: Any = None) -> Dict[str, Any]:
    """阶段 2：按族 schema 生成专属 prompt，LLM 理解填充，规则校验。"""
    sch = schema_for(family)
    if not sch:
        return {"ok": False, "issues": [f"unknown_family:{family}"]}
    lines = []
    for k, spec in sch["all_fields"].items():
        if spec.get("type") == "enum":
            lines.append(f'  "{k}": 只能从 {spec["enum"]} 选')
        elif spec.get("type") == "list":
            lines.append(f'  "{k}": 数组')
        else:
            lines.append(f'  "{k}": {spec.get("hint") or "短文本"}')
    prompt = (EXTRACT_PROMPT.replace("{label}", sch["label"])
              .replace("{description}", sch["description"])
              .replace("{fields}", "字段说明：\n" + "\n".join(lines))
              .replace("{name}", name)
              .replace("{text}", (text or "")[:6000]))
    from ..llm.backends import chat as _chat
    from ..utils import parse_llm_json
    fn = chat_fn or (lambda p, **kw: _chat(p, backend="vllm", **kw))
    attempts, issues = [], []
    for i in range(3):
        try:
            raw = fn(prompt, max_tokens=1400, timeout=240)
            data = parse_llm_json(raw) or {}
            issues = _validate(family, data, text)
            attempts.append({"i": i, "issues": issues[:6],
                             "out_chars": len(raw or "")})
            if not issues:
                return {"ok": True, "family": family, "data": data,
                        "uniform": _uniform(family, data),
                        "attempts": attempts}
            if i == 1:
                prompt += ("\n【收窄契约】只输出下面 5 个字段：role, object_kind, "
                           "task_kind, modality, evidence；"
                           "evidence 若无法逐字复制原文就填空字符串 \"\"。")
            else:
                prompt += "\n【修正】" + "; ".join(issues[:4])
        except Exception as exc:  # noqa: BLE001
            attempts.append({"i": i, "error": str(exc)[:120]})
    return {"ok": False, "family": family, "data": {},
            "issues": issues, "attempts": attempts}


def extract_algorithm(name: str, text: str, *, chat_fn: Any = None,
                      use_llm: bool = True) -> Dict[str, Any]:
    """两阶段入口：判类别 → 按族 schema 抽取。"""
    cls = classify_family(name, text, chat_fn=chat_fn, use_llm=use_llm)
    if cls["family_id"] == "unknown":
        return {"ok": False, "stage": "classify", "classify": cls}
    ex = extract_by_family(name, cls["family_id"], text, chat_fn=chat_fn)
    return {"ok": ex["ok"], "stage": "extract", "classify": cls,
            "extract": ex}
