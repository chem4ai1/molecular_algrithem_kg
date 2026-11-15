"""P3/P4：算法库与数据库的语义分类体系。

算法库 6 维（重新设计，不照抄用户随口举的例子）：
  family   算法族：自回归/Transformer、扩散/分数、VAE、GNN/等变、流匹配…
  role     论文角色：本论文方法 / 基线 / 评测工具
  object   作用对象：小分子 / 蛋白口袋 / 抗体 / 多肽 / 材料力场
  task     解决问题：生成设计 / 性质预测 / 结构对接 / 优化校准 / 指令 LLM
  modality 数据模态：3D 结构 / 2D 图 / 1D 序列 / 文本 / 性质向量
  code     代码落地：已对齐 CodeFunction / 仅论文提及

数据库 6 维：
  task     任务族；object 研究对象；modality 数据模态
  io       输入输出形式；scale 规模；source 数据来源（PG 有 result 否）
"""
from __future__ import annotations
import re
from typing import Any, Dict, List, Optional

from .taxonomy import classify, domain_label, family_label

OBJ_LABEL = {"antibody": "抗体", "peptide": "多肽", "protein": "蛋白/口袋",
             "material": "材料/力场", "reaction": "反应/合成",
             "molecule": "小分子", "other": "未分类对象"}
TASK_LABEL = {"instruction": "指令/LLM", "benchmark": "基准/数据集",
              "structure": "结构/对接", "optimization": "优化/校准",
              "prediction": "性质/能量预测", "generation": "生成/设计",
              "other": "未分类问题"}
MOD_LABEL = {"text": "文本/指令", "3d": "3D 结构/坐标", "graph": "2D 图",
             "sequence": "1D 序列/SMILES", "tabular": "性质向量/表格",
             "other": "未分类模态"}

ARCH_FAMILY = [
    (r"autoregress|transformer|llm|gpt|decoder|language", "自回归/Transformer/LLM"),
    (r"diffusion|score.?based|ddpm|denois", "扩散/分数模型"),
    (r"vae|variational|latent", "VAE/隐变量"),
    (r"flow|normalizing|optimal transport", "流匹配/连续流"),
    (r"gnn|graph|message.?pass|mpnn|schnet|equivariant|so3|se\(3\)",
     "GNN/几何等变"),
    (r"gan|adversarial|discriminator", "GAN/对抗"),
    (r"gan|genetic|evolution|tree.?search|mcts", "进化/树搜索"),
    (r"fragment|junction.?tree|motif", "片段/结构化生成"),
]

BENCH_TASK = [
    (r"amp|peptide|antimicrobial|sequence", "多肽/序列设计"),
    (r"dock|pocket|dud.?e|protein|antibod|cdrh", "结构/对接"),
    (r"admet|logp|tox|qsar|pka|property|sapt|energy|quid|jsch|pla15",
     "性质/能量预测"),
    (r"zinc|molgen|generation|generative|torsion|glcmal", "分子生成"),
    (r"instruction|prompt|dataset|corpus", "指令/数据集"),
]
BENCH_OBJECT = [
    (r"antibod|cdrh|nanobod", "抗体"),
    (r"amp|peptide|pentapeptide", "多肽"),
    (r"pocket|protein|dud.?e|crambin", "蛋白/口袋"),
    (r"sapt|quid|pla15|jsch|force field|water|material|crystal", "材料/力场"),
    (r"zinc|molecul|molgen|torsion|glcmal|drug", "小分子"),
]
BENCH_MOD = [
    (r"pocket|dud.?e|3d|coordinate|conformer|sapt|crambin|torsion",
     "3D 结构/坐标"),
    (r"amp|peptide|sequence|smiles|selfies", "1D 序列/SMILES"),
    (r"graph|topolog|junction", "2D 图"),
    (r"instruction|text|corpus", "文本/指令"),
    (r"descriptor|vector|property|admet|logp|pka", "性质向量/表格"),
]


def _first(text: str, rules, default: str) -> str:
    low = (text or "").lower()
    for pat, label in rules:
        if re.search(pat, low):
            return label
    return default


def _paper_of(graph: Any, algo_id: str) -> Optional[Any]:
    for a in graph.incoming(algo_id):
        if a.relation == "PROPOSES_METHOD" and a.source in graph.nodes:
            return graph.nodes[a.source]
    return None


def classify_algorithm(graph: Any, algo_id: str) -> Dict[str, str]:
    n = graph.nodes.get(algo_id)
    if not n:
        return {}
    at = n.attrs
    arch = str(at.get("architecture") or "")
    fam = _first(f"{arch} {n.label}", ARCH_FAMILY, "未分类算法族")
    codes = at.get("algo_codes") or []
    if fam == "未分类算法族" and codes:
        fam = family_label(str(codes[0]))
    kind = str(at.get("kind") or "")
    role = ("本论文方法" if kind == "method" else
            "基线" if kind == "baseline" or at.get("is_baseline") else
            "评测工具" if "eval" in kind.lower() else "未标注角色")
    p = _paper_of(graph, algo_id)
    tx = classify((p.label if p else ""), "",
                  paper_type=str(p.attrs.get("paper_type") if p else ""))
    has_code = any(a.relation in ("REALIZED_BY", "HAS_MODULE_IMPL",
                                  "IMPLEMENTS_MODULE")
                   for a in graph.outgoing(algo_id))
    out = {"family": fam, "role": role,
           "object": OBJ_LABEL.get(tx["object_kind"], "未分类对象"),
           "task": TASK_LABEL.get(tx["task_kind"], "未分类问题"),
           "modality": MOD_LABEL.get(tx["modality"], "未分类模态"),
           "code": "已对齐代码" if has_code else "仅论文提及"}
    # v2 问题中心框架覆盖了展示维度；「论文角色」改由「任务类型」承担
    core = str(at.get("schema_version") or "")
    if core.startswith("v2"):
        from .algorithm_problem import TASK_TYPES
        from .algorithm_schema import FAMILIES as ALGO_FAMILIES
        fam_label = ALGO_FAMILIES.get(
            at.get("schema_family") or {}, {}).get("label")
        out["family"] = fam_label or at.get("schema_family") or fam
        out["role"] = at.get("task_type_label") or \
            TASK_TYPES.get(at.get("task_type"), "未分类任务")
        out["task"] = out["role"]
        out["object"] = at.get("object_kind") or out["object"]
        out["modality"] = at.get("modality") or out["modality"]
    # 分类补值优先（封闭词表，历史一次性脚本已归档到 backup/）
    for k in ("family", "object", "task", "modality"):
        v = str(at.get("llm_" + k) or "")
        if v:
            out[k] = v
    return out


FAMILY_TO_FACET = {
    "molecule_generation": ("分子生成", "小分子", "1D 序列/SMILES"),
    "property_prediction": ("性质/能量预测", "小分子", "性质向量/表格"),
    "quantum_energy": ("性质/能量预测", "材料/力场", "3D 结构/坐标"),
    "structure_docking": ("结构/对接", "蛋白/口袋", "3D 结构/坐标"),
    "peptide_sequence": ("多肽/序列设计", "多肽", "1D 序列/SMILES"),
    "instruction_dataset": ("指令/数据集", "小分子", "文本/指令"),
    "reaction_synthesis": ("反应/合成", "反应/合成", "1D 序列/SMILES"),
}


def classify_benchmark(graph: Any, bid: str,
                       has_result: bool = False) -> Dict[str, str]:
    n = graph.nodes.get(bid)
    if not n:
        return {}
    at = n.attrs
    blob = f"{n.label} {at.get('task_family','')} {at.get('research_object','')}"
    CN_TASKS = {"分子生成", "性质/能量预测", "结构/对接", "多肽/序列设计",
                "指令/数据集"}
    CN_OBJS = {"小分子", "蛋白/口袋", "抗体", "多肽", "材料/力场"}
    CN_MODS = {"3D 结构/坐标", "1D 序列/SMILES", "2D 图", "文本/指令",
               "性质向量/表格"}
    _t = str(at.get("task_family") or "")
    task = (_t if _t in CN_TASKS else
            _first(blob, BENCH_TASK, "未分类任务族"))
    _o = str(at.get("research_object") or "")
    obj = (_o if _o in CN_OBJS else
           _first(blob, BENCH_OBJECT, "未分类研究对象"))
    _m = str(at.get("modality") or "")
    mod = (_m if _m in CN_MODS else
           _first(blob + " " + str(at.get("input_schema") or ""), BENCH_MOD,
                  "未分类模态"))
    i = str(at.get("input_schema") or at.get("input_form") or "?")
    o = str(at.get("output_schema") or at.get("output_form") or "?")
    io = f"{i[:18]} → {o[:18]}"
    raw = str(at.get("n_samples") or "")
    m = re.search(r"(\d[\d,]*)", raw.replace(".", ""))
    if m:
        v = int(m.group(1).replace(",", ""))
        scale = "小规模 (<1k)" if v < 1000 else (
            "中规模 (1k–100k)" if v < 100000 else "大规模 (>100k)")
    else:
        scale = "规模未标注"
    fam = str(at.get("schema_family") or "")
    if fam in FAMILY_TO_FACET:
        t, o, m = FAMILY_TO_FACET[fam]
        task, obj, mod = t, o, m
    out = {"task": task[:40], "object": obj[:40], "modality": mod[:40],
           "io": io, "scale": scale,
           "source": "论文表格已抽" if has_result else "仅图关系"}
    for k in ("object", "modality", "io", "scale"):
        v = str(at.get("llm_" + k) or "")
        if v:
            out[k] = v
    return out


ALGO_FACET_LABELS = {
    "family": "算法族", "role": "任务类型", "object": "作用对象",
    "task": "解决问题", "modality": "数据模态"}
DATA_FACET_LABELS = {
    "task": "任务族", "object": "研究对象", "modality": "数据模态",
    "io": "输入输出形式", "scale": "规模"}
