"""语义分类：研究对象 / 研究问题 / 数据模态（替代 D1/A01 这类裸码）。

用户要求：论文树不能只显示 D1，要按「研究对象、研究的问题、数据模态」分。
规则确定性可复算；未命中落 `other/未分类`，不编造。
"""
from __future__ import annotations
import re
from typing import Any, Dict, List, Tuple

OBJECT: Tuple[Tuple[str, str, str], ...] = (
    (r"antibod|nanobod|immunoglob|cdr", "antibody", "抗体"),
    (r"peptide|antimicrobial|\bamp\b|amp-", "peptide", "多肽"),
    (r"protein|pocket|ligand bind|fold|conformational", "protein", "蛋白/口袋"),
    (r"force field|potential energy|material|mlip|dft|so3lr|tauri", "material",
     "材料/力场"),
    (r"reaction|retrosynth|synthes", "reaction", "反应/合成"),
    (r"molecul|smiles|drug|compound|chemical|fragment", "molecule", "小分子"),
)
TASK: Tuple[Tuple[str, str, str], ...] = (
    (r"instruction|prompt|fine-tun|llm|language model", "instruction",
     "指令/LLM"),
    (r"benchmark|dataset|corpus|evaluat", "benchmark", "基准/数据集"),
    (r"dock|fold|structur|conformer|geometr", "structure", "结构/对接"),
    (r"optimi|multi-objective|calibrat|conditional generat", "optimization",
     "优化/校准"),
    (r"predict|regress|estimat|property|admet|logp|toxicit|affinity|"
     r"force field|potential energy|energ(y|ies)|forces", "prediction",
     "性质/能量预测"),
    (r"generat|design|sampl|de novo|diffusion|autoregress", "generation",
     "生成/设计"),
)
MODALITY: Tuple[Tuple[str, str, str], ...] = (
    (r"3d|coordinate|conformer|equivarian|geometr|force field|structure",
     "3d", "3D 结构/坐标"),
    (r"smiles|sequence|amino acid|residue|token|string|fragment", "sequence",
     "1D 序列/SMILES"),
    (r"graph|node|edge|message passing|\bgnn\b|junction tree", "graph", "2D 图"),
    (r"propert|descriptor|vector|feature|scalar", "tabular", "性质向量/表格"),
    (r"instruction|natural language|text corpus|\bqa\b|question answer",
     "text", "文本/指令"),
)


def _first(text: str, rules: Tuple[Tuple[str, str, str], ...],
           default: Tuple[str, str]) -> Tuple[str, str]:
    low = (text or "").lower()
    for pat, code, label in rules:
        if re.search(pat, low):
            return code, label
    return default


def classify(title: str = "", abstract: str = "", *,
             domain_code: str = "", paper_type: str = "") -> Dict[str, str]:
    """返回 object_kind/object_label/task_kind/task_label/modality/..."""
    blob = f"{title} {abstract} {domain_code} {paper_type}"
    o_code, o_label = _first(blob, OBJECT, ("other", "未分类对象"))
    t_code, t_label = _first(blob, TASK, ("other", "未分类问题"))
    m_code, m_label = _first(blob, MODALITY, ("other", "未分类模态"))
    return {"object_kind": o_code, "object_label": o_label,
            "task_kind": t_code, "task_label": t_label,
            "modality": m_code, "modality_label": m_label}


def domain_label(code: str) -> str:
    from ..po.vocab import DOMAIN_NAMES
    return DOMAIN_NAMES.get((code or "").strip().upper(), code or "未分类领域")


def family_label(code: str) -> str:
    from ..po.vocab import ALGO_NAMES
    return ALGO_NAMES.get((code or "").strip().upper(), code or "未分类算法")


def paper_facets(papers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """按 5 个 facet 汇总，供数据树切换。"""
    facets: Dict[str, Dict[str, Any]] = {
        "domain": {}, "object": {}, "task": {}, "modality": {}, "algorithm": {}}
    for p in papers:
        d = (p.get("domain_codes") or ["未分类"])[0]
        facets["domain"].setdefault(d, {"label": domain_label(d)})
        o = p.get("object_kind") or "other"
        facets["object"].setdefault(o, {"label": p.get("object_label") or "未分类对象"})
        t = p.get("task_kind") or "other"
        facets["task"].setdefault(t, {"label": p.get("task_label") or "未分类问题"})
        m = p.get("modality") or "other"
        facets["modality"].setdefault(m, {"label": p.get("modality_label") or "未分类模态"})
        for a in (p.get("algo_codes") or ["未分类"]):
            facets["algorithm"].setdefault(a, {"label": family_label(a)})
    return {k: [{"id": i, **v} for i, v in sorted(v.items())]
            for k, v in facets.items()}
