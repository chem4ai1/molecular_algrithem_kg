"""蛋白质 / 分子算法能力的**结构化知识抽取**（优化版）.

原流水线的问题（见 ``llm/prompts.py::PAPER_EXTRACTION`` 与 ``pipeline._make_capabilities``）：

1. LLM 直出一个扁平 JSON，``task`` / ``category`` / ``dtype`` 全是**自由文本**，
   同一任务会被写成 ``toxicity_prediction`` / ``peptide toxicity`` / ``tox pred``；
2. ``evidence.quote`` 只靠 prompt 约束"must be verbatim"，**没有任何程序化核验**，
   模型改写/编造的证据会直接进入图谱并抬高 confidence；
3. ``confidence`` 是模型给的一个**整体标量**，一条编造的证据可以给整条能力 0.9；
4. 只从论文抽，仓库里现成的函数签名、依赖、常量**完全没被利用**；
5. 指标没有 ``split`` / ``protocol``，不同划分下的 AUC 被直接比大小。

本模块提供三层能力，全部离线、纯 stdlib：

- :func:`DomainExtractor.extract`          纯规则/词典抽取（无 LLM 时的兜底，且质量可解释）
- :func:`DomainExtractor.refine_llm_output` 对 **LLM 原输出做后处理**（证据锚定、数值溯源、
  词表归一、IO/指标/依赖补全、字段级置信度重算、冲突检测）——这是与现有 6 Agent 的接入点
- :func:`DomainExtractor.extract_from_code` 从 ``.py`` 源码 AST 反推函数签名与 IO 契约

输出统一为 ``ExtractionResult``，其中每条能力都是可直接写入图谱的
:class:`~capfactory.domain.bio_schema.ProteinCapability`。
"""

from __future__ import annotations

import ast
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..utils import now_iso, short_hash
from .bio_schema import (
    ALGORITHM_FAMILIES, BIO_ENTITIES, MODALITIES, TASK_FAMILIES,
    ApplicabilityDomain, BioSpec, ComputeBudget, DomainEvidence, DomainIOField,
    MetricProfile, ProteinCapability, default_direction,
)

# ---------------------------------------------------------------------------
# 领域词典（受控词表的落地：正则命中 → 规范值）
# 顺序敏感：先具体后一般
# ---------------------------------------------------------------------------
ENTITY_PATTERNS: List[Tuple[str, str]] = [
    ("antibody", r"\bantibod(?:y|ies)\b|抗体"),
    ("peptide", r"\bpeptides?\b|\bAMPs?\b|抗菌肽|多肽|毒素肽"),
    ("small_molecule", r"\bsmall[- ]molecules?\b|\bmolecules?\b|\bligands?\b|"
                       r"\bcompounds?\b|小分子|化合物"),
    ("complex", r"\bprotein[- ]protein interaction\b|\bPPI\b|\bcomplex(?:es)?\b|复合物"),
    ("enzyme", r"\benzymes?\b|\bsubstrates?\b|酶"),
    ("nucleic_acid", r"\bDNA\b|\bRNA\b|核酸"),
    ("protein", r"\bproteins?\b|蛋白质|蛋白"),
]

MODALITY_PATTERNS: List[Tuple[str, str]] = [
    ("smiles", r"\bSMILES\b|\bcanonical smiles\b"),
    ("molecular_graph", r"\bmolecular graph\b|\bgraph neural\b|\bGNN\b|\bGAT\b|"
                        r"\batom[- ]bond\b|\bmessage passing\b|分子图"),
    ("structure_3d", r"\bPDB\b|\b3D structure\b|\bAlphaFold\b|\bESMFold\b|\bRMSD\b|"
                     r"\bTM[- ]?score\b|\bcoordinates?\b|\bdocking\b|三维结构"),
    ("msa", r"\bMSA\b|multiple sequence alignment|多序列比对"),
    ("fingerprint", r"\bECFP\d*\b|\bMorgan fingerprint\b|\bmolecular fingerprint\b|分子指纹"),
    ("embedding", r"\bESM[- ]?2?\b|\bProtBERT\b|\bprotein language model\b|"
                  r"\bembeddings?\b|\bpre-?trained\b|预训练"),
    ("sequence", r"\bamino[- ]acid sequence\b|\bpeptide sequence\b|\bprotein sequence\b|"
                 r"\bsequences?\b|\bFASTA\b|序列"),
    ("tabular", r"\bdescriptor table\b|\btabular\b|\bfeature matrix\b|特征矩阵"),
]

TASK_FAMILY_PATTERNS: List[Tuple[str, str]] = [
    ("structure_prediction", r"structure prediction|protein folding|contact map|"
                             r"\bRMSD\b|\bTM[- ]?score\b|\bpLDDT\b|结构预测"),
    ("binding_affinity", r"binding affinity|protein[- ]ligand|\bpIC50\b|\bIC50\b|"
                         r"\bKd\b|\bK_i\b|\bΔG\b|结合亲和"),
    ("interaction_prediction", r"protein[- ]protein interaction|\bPPI\b|interaction prediction"),
    ("molecular_generation", r"de novo (?:design|generation)|generative model|"
                             r"diffusion model|\bVAE\b|\bGAN\b|molecule generation|生成模型"),
    ("sequence_design", r"sequence design|peptide design|序列设计"),
    ("docking", r"molecular docking|docking (?:score|simulation)|分子对接"),
    ("admet", r"\bADMET\b|half[- ]life|immunogenicity|\btoxicity\b|hemolytic|"
              r"solubility|permeability|stability prediction|成药性|毒性"),
    ("virtual_screening", r"virtual screening|hit identification|enrichment factor|虚拟筛选"),
    ("representation_learning", r"representation learning|contrastive learning|"
                                r"self[- ]supervised|masked language model|表示学习"),
    ("evaluation_protocol", r"evaluation protocol|benchmark(?:ing)?|cross[- ]validation|"
                            r"imbalanced evaluation|\bMCC\b"),
    ("optimization", r"bayesian optimization|reinforcement learning|multi[- ]objective|"
                     r"directed evolution|优化"),
    ("property_prediction", r"predict(?:ion|ing|s)?|classif(?:ier|ication)|"
                            r"regression|\btoxic\b|\bactivity\b|性质预测"),
]

ALGORITHM_FAMILY_PATTERNS: List[Tuple[str, str]] = [
    ("geometric_dl", r"graph (?:neural|convolution)|equivariant|\bGNN\b|\bGAT\b|"
                     r"geometric deep learning|\bSE\(3\)\b"),
    ("generative", r"diffusion|\bGAN\b|\bVAE\b|autoregressive|generative|flow matching"),
    # 模型族优先于特征族：能力通常按「用什么模型」归类，
    # "AAC 特征 + Extra Trees" 应判为 ensemble，而不是只看到 AAC 就判 descriptor。
    ("ensemble", r"stacking|ensemble|random forest|extra trees|gradient boosting|\bXGBoost\b"),
    ("descriptor", r"amino[- ]acid composition|\bAAC\b|dipeptide composition|\bDPC\b|"
                   r"\bk[- ]mer\b|physicochemical descriptor|fingerprint|descriptor"),
    ("deep_learning", r"\bCNN\b|\bRNN\b|transformer|neural network|deep learning|\bLSTM\b"),
    ("classical_ml", r"\bSVM\b|support vector|logistic regression|\bKNN\b|"
                     r"naive bayes|\bRF\b|decision tree|classifier"),
    ("simulation", r"molecular dynamics|\bMD simulation\b|Monte Carlo|docking simulation"),
    ("statistical", r"\bANOVA\b|hypothesis test|bootstrap|confidence interval"),
    ("optimization", r"bayesian optimization|reinforcement learning|evolutionary"),
    ("retrieval", r"\bBM25\b|retrieval|nearest neighbour|homology search|\bBLAST\b"),
]

REPRESENTATION_PATTERNS: List[Tuple[str, str]] = [
    ("AAC", r"amino[- ]acid composition|\bAAC\b"),
    ("DPC", r"dipeptide composition|\bDPC\b"),
    ("k-mer", r"\bk[- ]mer\b|\bkmer\b"),
    ("physicochemical", r"hydrophobicity|net charge|isoelectric|aromaticity|物化描述符"),
    ("ESM-2", r"\bESM[- ]?2\b|\bESM\b"),
    ("ECFP", r"\bECFP\d*\b|Morgan fingerprint"),
    ("one-hot", r"one[- ]hot|\bordinal encoding\b"),
    ("3D-coordinates", r"\bCα\b|backbone coordinates|torsion angles"),
]

DATASET_PATTERNS = [
    r"\bDBAASP\b", r"\bDRAMP\b", r"\bHemolytik(?:-2)?\b", r"\bTox21\b", r"\bMUV\b",
    r"\bPDBbind\b", r"\bCASF\b", r"\bUniProt\b", r"\bPDB\b", r"\bAPD3?\b", r"\bCAMP(?:R3)?\b",
    r"\bBindingDB\b", r"\bChEMBL\b", r"\bMoleculeNet\b", r"\bZINC\b", r"\bQM9\b",
    r"\bToxinPred\d?\b", r"\bAntiBP\d?\b", r"\bSATPdb\b", r"\bPDBsum\b",
]

DEPENDENCY_PATTERNS: List[Tuple[str, str]] = [
    ("rdkit", r"\bRDKit\b|\brdkit\b"), ("biopython", r"\bBiopython\b|\bBio\.PDB\b"),
    ("torch", r"\bPyTorch\b|\btorch\b"), ("tensorflow", r"\bTensorFlow\b"),
    ("transformers", r"\bHuggingFace\b|\btransformers\b"), ("esm", r"\bfair-esm\b|\besm\b"),
    ("scikit-learn", r"\bscikit[- ]learn\b|\bsklearn\b"), ("xgboost", r"\bXGBoost\b"),
    ("numpy", r"\bnumpy\b"), ("pandas", r"\bpandas\b"), ("scipy", r"\bscipy\b"),
    ("torch-geometric", r"\bPyG\b|torch[- ]geometric"), ("dgl", r"\bDGL\b"),
    ("openmm", r"\bOpenMM\b"), ("mdtraj", r"\bMDTraj\b"),
]

METRIC_CANON: Dict[str, str] = {
    "auroc": "roc_auc", "roc-auc": "roc_auc", "auc": "roc_auc", "area under the curve": "roc_auc",
    "acc": "accuracy", "acc.": "accuracy", "mcc": "mcc", "f1": "f1", "f1-score": "f1",
    "aupr": "aupr", "average precision": "average_precision", "ap": "average_precision",
    "rmse": "rmse", "mae": "mae", "mse": "mse", "r2": "r2", "r²": "r2",
    "spearman": "spearman", "spearman's rho": "spearman", "pearson": "pearson",
    "rmsd": "rmsd", "tm-score": "tm_score", "tm score": "tm_score", "lddt": "lddt",
    "plddt": "plddt", "gdtts": "gdtts", "validity": "validity",
    "uniqueness": "uniqueness", "novelty": "novelty", "diversity": "diversity",
    "enrichment factor": "enrichment_factor", "ef": "enrichment_factor",
    "hit rate": "hit_rate", "brier": "brier", "recall": "recall", "precision": "precision",
}

_METRIC_ALT = "|".join(re.escape(k) for k in sorted(METRIC_CANON, key=len, reverse=True))
METRIC_VALUE_RE = re.compile(
    rf"(?P<name>{_METRIC_ALT})\s*(?:score|value|of|was|is|=|:|,)?\s*"
    r"(?:of\s+|reached\s+|achieved\s+)?(?P<value>0?\.\d{2,}|\d{1,3}\.\d+)",
    re.I,
)
NUMBER_RE = re.compile(r"(?<![\w.])(0?\.\d{2,}|\d{1,3}\.\d{2,})(?![\w.])")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;!?])\s+|\n{2,}")

# 字段置信度权重：证据与方法最重，避免"一条漂亮的名字"撑起整条能力
FIELD_WEIGHTS: Dict[str, float] = {
    "name": 0.05, "task": 0.08, "bio_spec": 0.07, "method": 0.20,
    "inputs": 0.10, "outputs": 0.10, "metrics": 0.10, "evidence": 0.20,
    "applicability": 0.05, "dependencies": 0.05,
}

FORBIDDEN_CODE_CALLS = {"eval", "exec", "compile", "__import__", "system", "popen", "Popen"}
FORBIDDEN_CODE_MODULES = {"subprocess", "socket", "ctypes", "shutil", "importlib"}


_NEGATION_RE = re.compile(
    r"\b(?:not|no|never|without|didn'?t|did not|do not|does not|nor|exclude[sd]?)\b", re.I)


def _sentence_at(text: str, start: int, end: int) -> str:
    """取命中位置所在的句子（用于否定语境判定）。"""
    left = max(text.rfind(".", 0, start), text.rfind("\n", 0, start),
               text.rfind(";", 0, start), 0)
    rights = [p for p in (text.find(".", end), text.find("\n", end),
                          text.find(";", end)) if p >= 0]
    right = min(rights) if rights else len(text)
    return text[left:right]


def _first_match(patterns: Sequence[Tuple[str, str]], text: str, default: str,
                 *, negation_aware: bool = False) -> str:
    """按词典顺序取首个命中值。

    ``negation_aware=True`` 时跳过出现在否定句中的命中（例如
    "We did not use 3D structure information" 不应把模态判成 structure_3d）。
    """
    for value, pattern in patterns:
        for m in re.finditer(pattern, text, re.I):
            if negation_aware and _NEGATION_RE.search(_sentence_at(text, m.start(), m.end())):
                continue
            return value
    return default


def _all_matches(patterns: Sequence[Tuple[str, str]], text: str) -> List[str]:
    return [value for value, pattern in patterns if re.search(pattern, text, re.I)]


def _norm_task(text: str) -> str:
    """把自由文本任务名归一为 snake_case 标识。"""
    s = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff]+", "_", (text or "").lower()).strip("_")
    return re.sub(r"_+", "_", s)[:60] or "unknown_task"


# ---------------------------------------------------------------------------
# 结果与代码信号
# ---------------------------------------------------------------------------
@dataclass
class ExtractionResult:
    """一次抽取的完整结果（含质量诊断，便于回写图谱与人工审核）。"""

    source_id: str = ""
    capabilities: List[ProteinCapability] = field(default_factory=list)
    diagnostics: List[Dict[str, Any]] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "capabilities": [c.to_dict() for c in self.capabilities],
            "diagnostics": self.diagnostics,
            "stats": self.stats, "created_at": self.created_at,
        }

    def summary(self) -> Dict[str, Any]:
        grades = [c.evidence_grade for c in self.capabilities]
        return {
            "n_capabilities": len(self.capabilities),
            "n_diagnostics": len(self.diagnostics),
            "grades": {g: grades.count(g) for g in sorted(set(grades))},
            "mean_confidence": round(
                sum(c.confidence for c in self.capabilities) / len(self.capabilities), 3
            ) if self.capabilities else 0.0,
            "stats": self.stats,
        }


@dataclass
class CodeSignals:
    """从源码 AST 抽取的结构化信号。"""

    source_id: str = ""
    functions: List[Dict[str, Any]] = field(default_factory=list)
    constants: Dict[str, Any] = field(default_factory=dict)
    imports: List[str] = field(default_factory=list)
    forbidden_calls: List[str] = field(default_factory=list)
    forbidden_imports: List[str] = field(default_factory=list)
    loc: int = 0
    parse_ok: bool = True
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# 抽取器
# ---------------------------------------------------------------------------
class DomainExtractor:
    """离线、确定性、可解释的领域抽取器。"""

    def __init__(self, *, max_text_chars: int = 120000):
        self.max_text_chars = max_text_chars

    # -- 基础识别 ---------------------------------------------------------
    def detect_bio_spec(self, text: str) -> BioSpec:
        entity = _first_match(ENTITY_PATTERNS, text, "unknown")
        modality = _first_match(MODALITY_PATTERNS, text, "unknown", negation_aware=True)
        # 实体优先兜底：蛋白/多肽默认一级序列，小分子默认 SMILES，避免 unknown 阻塞能力链推理
        if modality == "unknown":
            modality = ({"peptide": "sequence", "protein": "sequence",
                         "antibody": "sequence", "enzyme": "sequence",
                         "small_molecule": "smiles"}.get(entity, "unknown"))
        alphabet = {
            "smiles": "smiles", "molecular_graph": "atom_graph",
            "structure_3d": "pdb", "msa": "amino_acid_1letter",
            "fingerprint": "bit_vector", "tabular": "numeric",
        }.get(modality, "amino_acid_1letter" if entity in ("peptide", "protein", "antibody") else "")
        length_min, length_max = 1, 2000
        m = re.search(r"(?:length|lengths)\s*(?:of|between|from)?\s*(\d{1,4})\s*(?:-|to|–|~)\s*(\d{1,4})",
                      text, re.I)
        if m:
            length_min, length_max = int(m.group(1)), int(m.group(2))
        organism = sorted(set(re.findall(
            r"\b(?:E\.\s?coli|Escherichia coli|Homo sapiens|human|mouse|rat|bacteria|"
            r"bacterial|viral|fungi|yeast)\b", text, re.I)))[:6]
        return BioSpec(
            entity=entity, modality=modality, alphabet=alphabet,
            length_min=length_min, length_max=length_max,
            organism=organism, structure_required=modality == "structure_3d",
            structure_source=("pdb" if modality == "structure_3d" else ""),
        )

    def detect_task_family(self, text: str) -> str:
        return _first_match(TASK_FAMILY_PATTERNS, text, "property_prediction")

    def detect_algorithm_family(self, text: str) -> str:
        return _first_match(ALGORITHM_FAMILY_PATTERNS, text, "classical_ml")

    def detect_representations(self, text: str) -> List[str]:
        return _all_matches(REPRESENTATION_PATTERNS, text)

    def detect_dependencies(self, text: str) -> List[str]:
        return _all_matches(DEPENDENCY_PATTERNS, text)

    def detect_datasets(self, text: str) -> List[str]:
        return sorted({m.group(0) for p in DATASET_PATTERNS for m in re.finditer(p, text, re.I)})

    def detect_metrics(self, text: str) -> List[MetricProfile]:
        """指标名 + 报告值，且**数值必须真的出现在原文**（反幻觉）。"""
        out: List[MetricProfile] = []
        seen: set = set()
        for m in METRIC_VALUE_RE.finditer(text):
            raw = m.group("name").lower().strip()
            name = METRIC_CANON.get(raw, _norm_task(raw))
            try:
                value = float(m.group("value"))
            except ValueError:
                continue
            key = (name, value)
            if key in seen or not (0.0 <= value <= 100.0):
                continue
            seen.add(key)
            out.append(MetricProfile(name=name, direction=default_direction(name),
                                     reported=round(value, 4)))
            if len(out) >= 12:
                break
        return out

    def detect_applicability(self, text: str, bio: BioSpec) -> ApplicabilityDomain:
        exclusions: List[str] = []
        if re.search(r"not (?:applicable|suitable)|only (?:for|applies to)|excluding", text, re.I):
            exclusions.append("文中显式声明的排除条件需人工复核")
        regime = ""
        for token, pat in (("imbalanced", r"imbalanced|class imbalance"),
                           ("low_data", r"small (?:dataset|sample)|few[- ]shot|limited data"),
                           ("large_scale", r"large[- ]scale|millions? of"),
                           ("balanced", r"balanced dataset")):
            if re.search(pat, text, re.I):
                regime = token
                break
        min_samples = 0
        m = re.search(r"(?:at least|minimum of|≥|>=)\s*(\d{2,6})\b", text, re.I)
        if m:
            min_samples = int(m.group(1))
        return ApplicabilityDomain(
            entities=[bio.entity] if bio.entity != "unknown" else [],
            modalities=[bio.modality] if bio.modality != "unknown" else [],
            length_min=bio.length_min, length_max=bio.length_max,
            min_samples=min_samples, data_regime=regime,
            exclusions=exclusions,
        )

    def infer_io(self, bio: BioSpec, representations: Sequence[str]) -> Tuple[List[DomainIOField], List[DomainIOField]]:
        """按模态推断默认数据契约（LLM 未给 IO 时补全）。"""
        if bio.modality == "smiles":
            inp = DomainIOField(name="molecules", modality="smiles", dtype="list[str]",
                                shape="[N]", canonical_form="canonical SMILES",
                                validator="validate_smiles", description="小分子结构")
        elif bio.modality in ("molecular_graph", "fingerprint"):
            inp = DomainIOField(name="molecular_representations", modality=bio.modality,
                                dtype="list[object]", shape="[N]",
                                canonical_form=(representations[0] if representations else "graph"),
                                description="分子图或指纹")
        elif bio.modality == "structure_3d":
            inp = DomainIOField(name="structures", modality="structure_3d", dtype="list[object]",
                                shape="[N, L, 3]", unit="Å", canonical_form="PDB coordinates",
                                validator="validate_coordinates", description="原子坐标")
        else:
            inp = DomainIOField(name="sequences", modality="sequence", dtype="list[str]",
                                shape="[N]", canonical_form="uppercase one-letter AA",
                                validator="validate_amino_acid_sequence",
                                description="蛋白/多肽一级序列")
        out = DomainIOField(name="prediction", modality="tabular", dtype="ndarray",
                            shape="[N]", canonical_form="float32 probability or score",
                            description="模型输出：概率 / 连续活性值 / 类别")
        return [inp], [out]

    # -- 纯规则抽取 -------------------------------------------------------
    def extract(self, text: str, *, source_id: str = "", locator: str = "",
                kind: str = "paper", title: str = "") -> ExtractionResult:
        """无 LLM 时的规则抽取：产出 1 条带可解释诊断的领域能力。"""
        text = (text or "")[: self.max_text_chars]
        result = ExtractionResult(source_id=source_id or f"src_{short_hash(text, length=8)}")
        if not text.strip():
            result.diagnostics.append({"level": "error", "code": "empty_text", "message": "输入文本为空"})
            result.stats = {"ok": False}
            return result

        bio = self.detect_bio_spec(text)
        task_family = self.detect_task_family(text)
        algo_family = self.detect_algorithm_family(text)
        reps = self.detect_representations(text)
        deps = self.detect_dependencies(text)
        datasets = self.detect_datasets(text)
        metrics = self.detect_metrics(text)
        inputs, outputs = self.infer_io(bio, reps)
        applicability = self.detect_applicability(text, bio)

        sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if len(s.strip()) > 40]
        method_sentences = [s for s in sentences
                            if re.search(r"we (?:use|propose|train|compute|apply|employ)|"
                                         r"(?:model|feature|algorithm|classifier) (?:is|was|uses)|"
                                         r"consists of|is computed as", s, re.I)][:6]
        method = " ".join(method_sentences) if method_sentences else text[:600]

        # 证据：优先取方法句，逐字锚定
        evidence: List[DomainEvidence] = []
        for i, s in enumerate(method_sentences[:3]):
            e = DomainEvidence(source_id=result.source_id, quote=s[:300],
                               locator=f"{locator or 'text'}#sentence{i+1}", kind=kind)
            evidence.append(e.anchor_in(text))

        name = (title.strip()[:70] if title else
                f"{task_family.replace('_', ' ')} via {algo_family.replace('_', ' ')} "
                f"for {bio.entity}").strip()
        # 先构造骨架，再统一计算字段置信度 / 证据等级 / 整体置信度
        cap = ProteinCapability(
            name=name,
            summary=(sentences[0][:180] if sentences else text[:180]),
            task=_norm_task(f"{bio.entity}_{task_family}"),
            task_family=task_family, algorithm_family=algo_family,
            category="representation" if algo_family in ("descriptor", "geometric_dl") else "model",
            bio_spec=bio, inputs=inputs, outputs=outputs, method=method,
            metrics=metrics, applicability=applicability,
            compute=ComputeBudget(dependencies=deps, device="cpu"),
            evidence=evidence, dependencies=deps,
            conditions=([f"数据集: {d}" for d in datasets[:3]] +
                        ([f"表示法: {', '.join(reps[:3])}"] if reps else [])),
            tags=sorted(set([task_family, algo_family, bio.entity, bio.modality] + reps[:3])),
            provenance={"source_id": result.source_id, "locator": locator,
                        "extraction_method": "rule_v1", "datasets": datasets},
        )
        self._finalise(cap, text, result, extraction_method="rule_v1")
        result.capabilities.append(cap)
        result.stats = {
            "ok": True, "n_chars": len(text), "n_sentences": len(sentences),
            "n_method_sentences": len(method_sentences), "n_metrics": len(metrics),
            "n_dependencies": len(deps), "n_datasets": len(datasets),
            "entity": bio.entity, "modality": bio.modality, "task_family": task_family,
        }
        return result

    # -- LLM 输出后处理（核心优化） ---------------------------------------
    def refine_llm_output(self, raw: Any, source_text: str, *,
                          source_id: str = "", locator: str = "",
                          code_signals: Optional[CodeSignals] = None) -> ExtractionResult:
        """把 LLM 的自由 JSON 提升为受控、可锚定、带字段置信度的领域能力。

        这是与现有 ``ReaderAgent`` / ``CriticAgent`` 的接入点：
        ``refine_llm_output(reader.output, full_text, code_signals=...)``。
        """
        result = ExtractionResult(source_id=source_id or f"llm_{short_hash(source_text, length=8)}")
        text = (source_text or "")[: self.max_text_chars]
        items: List[Dict[str, Any]] = []
        if isinstance(raw, dict):
            for key in ("capabilities", "techniques", "methods"):
                if isinstance(raw.get(key), list):
                    items = [x for x in raw[key] if isinstance(x, dict)]
                    if items:
                        break
            if not items and "name" in raw:
                items = [raw]
        elif isinstance(raw, list):
            items = [x for x in raw if isinstance(x, dict)]

        if not items:
            result.diagnostics.append({"level": "error", "code": "no_capabilities",
                                       "message": "LLM 输出中未找到能力数组，回退规则抽取"})
            fallback = self.extract(text, source_id=source_id, locator=locator)
            fallback.diagnostics = result.diagnostics + fallback.diagnostics
            return fallback

        for idx, item in enumerate(items[:8]):
            evidence_raw = item.get("evidence") or []
            evidence: List[DomainEvidence] = []
            for er in (evidence_raw if isinstance(evidence_raw, list) else [])[:6]:
                er = er if isinstance(er, dict) else {"quote": str(er)}
                e = DomainEvidence(
                    source_id=source_id or result.source_id,
                    quote=str(er.get("quote") or "")[:400],
                    locator=str(er.get("locator") or locator),
                    kind=str(er.get("kind") or "paper"),
                ).anchor_in(text)
                if not e.anchored and not e.quote:
                    continue
                evidence.append(e)
                if not e.anchored:
                    result.diagnostics.append({
                        "level": "warning", "code": "unanchored_evidence",
                        "capability_index": idx, "quote_preview": e.quote[:80],
                        "message": "证据引文无法在原文逐字匹配，已降级并计入幻觉风险"})

            method = str(item.get("method") or "")
            name = str(item.get("name") or item.get("title") or f"capability_{idx}")
            combined = " ".join(filter(None, [name, method, str(item.get("summary") or "")]))
            bio = self.detect_bio_spec(" ".join(filter(None, [combined, text[:3000]])))
            task_family = str(item.get("task_family") or "")
            if task_family not in TASK_FAMILIES:
                task_family = self.detect_task_family(combined or text[:3000])
            algo_family = str(item.get("algorithm_family") or "")
            if algo_family not in ALGORITHM_FAMILIES:
                algo_family = self.detect_algorithm_family(combined or text[:3000])
            task = _norm_task(str(item.get("task") or f"{bio.entity}_{task_family}"))

            reps = self.detect_representations(combined) or self.detect_representations(text[:3000])
            default_inputs, default_outputs = self.infer_io(bio, reps)
            inputs = [DomainIOField.from_any(x) for x in (item.get("inputs") or [])] or default_inputs
            outputs = [DomainIOField.from_any(x) for x in (item.get("outputs") or [])] or default_outputs
            for io in inputs + outputs:
                if io.modality not in MODALITIES:
                    io.modality = bio.modality if bio.modality != "unknown" else "unknown"
                    result.diagnostics.append({
                        "level": "info", "code": "modality_normalised",
                        "capability_index": idx, "field": io.name,
                        "message": f"IO 模态归一为 {io.modality}"})

            # 指标：LLM 声明 + 文本抽取补全，并做数值溯源
            metrics = [MetricProfile.from_any(m) for m in (item.get("metrics") or [])
                       if isinstance(m, dict)]
            seen_keys = {(m.name, m.reported) for m in metrics}
            for m in self.detect_metrics(text):
                if (m.name, m.reported) not in seen_keys:
                    metrics.append(m)
                    seen_keys.add((m.name, m.reported))
            numbers = set(NUMBER_RE.findall(text))
            for m in metrics:
                if m.reported is None:
                    continue
                candidates = {f"{m.reported:.4f}", f"{m.reported:g}", str(m.reported)}
                if not any(c in numbers or any(c in n for n in numbers) for c in candidates):
                    result.diagnostics.append({
                        "level": "warning", "code": "untraceable_metric_value",
                        "capability_index": idx, "metric": m.name, "value": m.reported,
                        "message": "报告值未出现在原文，标记为待核验"})
                    m.note = "untraceable_value"
                if not m.direction:
                    m.direction = default_direction(m.name)

            deps = sorted(set(
                [str(d) for d in (item.get("dependencies") or [])] +
                self.detect_dependencies(text) +
                (code_signals.imports if code_signals else [])
            ))
            datasets = self.detect_datasets(text)
            applicability = self.detect_applicability(text, bio)
            for c in (item.get("conditions") or []):
                if isinstance(c, str) and c.strip():
                    applicability.constraints.append(c[:200])

            cap = ProteinCapability(
                name=name, summary=str(item.get("summary") or "")[:400],
                task=task, task_family=task_family, algorithm_family=algo_family,
                category=str(item.get("category") or "model"),
                bio_spec=bio, inputs=inputs, outputs=outputs, method=method,
                metrics=metrics[:12], applicability=applicability,
                compute=ComputeBudget(dependencies=deps),
                evidence=evidence,
                conditions=[str(x)[:200] for x in (item.get("conditions") or [])][:8],
                constraints=[str(x)[:200] for x in (item.get("constraints") or [])][:8],
                dependencies=deps,
                tags=sorted(set([str(x) for x in (item.get("tags") or [])] +
                                [task_family, algo_family, bio.entity, bio.modality] + reps[:3])),
                maturity=0.0,
                provenance={"source_id": source_id, "locator": locator,
                            "extraction_method": "llm_refined_v1",
                            "llm_confidence": item.get("confidence"),
                            "datasets": datasets,
                            "representations": reps,
                            "code_signals": bool(code_signals)},
            )
            self._finalise(cap, text, result, extraction_method="llm_refined_v1",
                           code_signals=code_signals)
            result.capabilities.append(cap)

        self._detect_conflicts(result)
        result.stats = {
            "ok": True, "n_input_capabilities": len(items),
            "n_output_capabilities": len(result.capabilities),
            "n_diagnostics": len(result.diagnostics), "n_chars": len(text),
            "extraction_method": "llm_refined_v1",
            "code_signals_used": bool(code_signals),
        }
        return result

    # -- 代码反推 ---------------------------------------------------------
    def extract_from_code(self, source: str, *, source_id: str = "") -> CodeSignals:
        signals = CodeSignals(source_id=source_id or f"code_{short_hash(source, length=8)}")
        signals.loc = len((source or "").splitlines())
        try:
            tree = ast.parse(source or "")
        except SyntaxError as exc:
            signals.parse_ok = False
            signals.error = f"SyntaxError: {exc}"
            return signals

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                args = [a.arg for a in node.args.args if a.arg not in ("self", "cls")]
                returns = ast.unparse(node.returns) if node.returns else ""
                signals.functions.append({
                    "name": node.name, "args": args, "returns": returns,
                    "doc": (ast.get_docstring(node) or "")[:300],
                    "lineno": node.lineno,
                })
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id.isupper():
                        try:
                            signals.constants[t.id] = ast.literal_eval(node.value)
                        except Exception:
                            signals.constants[t.id] = ast.unparse(node.value)[:100]

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                signals.imports += [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                signals.imports.append(node.module.split(".")[0])
            elif isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else (
                    node.func.attr if isinstance(node.func, ast.Attribute) else "")
                if name in FORBIDDEN_CODE_CALLS:
                    signals.forbidden_calls.append(name)
        signals.imports = sorted(set(signals.imports))
        signals.forbidden_calls = sorted(set(signals.forbidden_calls))
        signals.forbidden_imports = sorted(set(signals.imports) & FORBIDDEN_CODE_MODULES)
        return signals

    def capability_from_code(self, source: str, *, source_id: str = "",
                             name: str = "") -> Tuple[CodeSignals, ProteinCapability]:
        """从源码反推一条 C 级（代码证据）能力，供图谱与 Planner 使用。"""
        signals = self.extract_from_code(source, source_id=source_id)
        bio = self.detect_bio_spec(source)
        task_family = self.detect_task_family(source)
        algo_family = self.detect_algorithm_family(source)
        reps = self.detect_representations(source)
        inputs, outputs = self.infer_io(bio, reps)
        func_names = [f["name"] for f in signals.functions]
        # 用真实签名修正 IO 名称
        if "featurize" in func_names:
            fe = next(f for f in signals.functions if f["name"] == "featurize")
            if fe["args"]:
                inputs[0].name = fe["args"][0]
        declared = str(signals.constants.get("TASK_TYPE") or "")
        cap = ProteinCapability(
            name=name or f"code-derived {task_family} ({', '.join(func_names[:3]) or 'module'})",
            summary=f"从代码反推：{', '.join(func_names[:6])}",
            task=_norm_task(declared or f"{bio.entity}_{task_family}"),
            task_family=task_family, algorithm_family=algo_family,
            bio_spec=bio, inputs=inputs, outputs=outputs,
            method="; ".join(f"{f['name']}({', '.join(f['args'])}) -> {f['returns'] or 'any'}"
                             for f in signals.functions[:8]) or source[:400],
            applicability=self.detect_applicability(source, bio),
            compute=ComputeBudget(dependencies=signals.imports),
            evidence=[DomainEvidence(source_id=signals.source_id,
                                     quote=f"def {f['name']}(", locator=f"L{f['lineno']}",
                                     kind="code").anchor_in(source)
                      for f in signals.functions[:3]],
            dependencies=signals.imports,
            constraints=(["检测到禁用调用: " + ",".join(signals.forbidden_calls)]
                         if signals.forbidden_calls else []) +
                        (["检测到禁用导入: " + ",".join(signals.forbidden_imports)]
                         if signals.forbidden_imports else []),
            tags=sorted(set(func_names[:5] + [task_family, algo_family, "code_derived"])),
            provenance={"source_id": signals.source_id,
                        "extraction_method": "code_ast_v1",
                        "declared_task_type": declared,
                        "n_functions": len(signals.functions)},
        )
        dummy = ExtractionResult(source_id=signals.source_id)
        self._finalise(cap, source, dummy, extraction_method="code_ast_v1",
                       code_signals=signals)
        return signals, cap

    # -- 融合 -------------------------------------------------------------
    def merge(self, results: Iterable[ExtractionResult], *,
              similarity_threshold: float = 0.90) -> ExtractionResult:
        """多来源融合：同名/同任务能力合并证据与指标，并保留 provenance。"""
        results = list(results)
        merged = ExtractionResult(source_id="merged", created_at=now_iso())
        index: Dict[str, ProteinCapability] = {}
        for r in results:
            merged.diagnostics.extend(r.diagnostics)
            for cap in r.capabilities:
                key = cap.task or _norm_task(cap.name)
                if key not in index:
                    index[key] = cap
                    continue
                cur = index[key]
                seen_q = {e.quote[:80] for e in cur.evidence}
                for e in cap.evidence:
                    if e.quote[:80] not in seen_q:
                        cur.evidence.append(e)
                        seen_q.add(e.quote[:80])
                seen_m = {(m.name, m.reported) for m in cur.metrics}
                cur.metrics += [m for m in cap.metrics if (m.name, m.reported) not in seen_m]
                cur.dependencies = sorted(set(cur.dependencies + cap.dependencies))
                cur.tags = sorted(set(cur.tags + cap.tags))
                cur.constraints = list(dict.fromkeys(cur.constraints + cap.constraints))[:10]
                cur.version += 1
                cur.confidence = round(max(cur.confidence, cap.confidence), 3)
                cur.maturity = round(max(cur.maturity, cap.maturity), 3)
                cur.provenance.setdefault("merged_sources", []).append(cap.provenance.get("source_id", ""))
                merged.diagnostics.append({
                    "level": "info", "code": "capability_merged", "task": key,
                    "message": f"合并来自 {cap.provenance.get('source_id', '?')} 的同任务能力"})
        merged.capabilities = list(index.values())
        merged.stats = {"n_sources": len(results), "n_merged": len(merged.capabilities),
                        "similarity_threshold": similarity_threshold}
        return merged

    # -- 内部：置信度与诊断 -----------------------------------------------
    def _finalise(self, cap: ProteinCapability, source_text: str,
                  result: ExtractionResult, *, extraction_method: str,
                  code_signals: Optional[CodeSignals] = None) -> None:
        """统一计算字段级置信度、证据等级、整体置信度与校验诊断。"""
        anchored = [e for e in cap.evidence if e.anchored]
        field_conf: Dict[str, float] = {
            "name": 0.95 if cap.name and "capability_" not in cap.name else 0.4,
            "task": 0.9 if cap.task and cap.task != "unknown_task" else 0.3,
            "bio_spec": 0.9 if cap.bio_spec.entity != "unknown" else 0.35,
            "method": min(1.0, 0.35 + len(cap.method) / 900.0),
            "inputs": 0.9 if cap.inputs and all(i.modality != "unknown" for i in cap.inputs) else 0.5,
            "outputs": 0.9 if cap.outputs else 0.4,
            "metrics": min(1.0, 0.35 + 0.2 * len(cap.metrics)),
            "evidence": min(1.0, 0.15 + 0.35 * len(anchored)),
            "applicability": 0.7 if cap.applicability.entities else 0.35,
            "dependencies": min(1.0, 0.4 + 0.15 * len(cap.dependencies)),
        }
        # 未锚定证据直接惩罚 evidence 字段
        if cap.evidence and len(anchored) < len(cap.evidence):
            field_conf["evidence"] *= 0.45
        # 代码信号提升 IO / 依赖可信度
        if code_signals and code_signals.parse_ok and code_signals.functions:
            field_conf["inputs"] = min(1.0, field_conf["inputs"] + 0.08)
            field_conf["outputs"] = min(1.0, field_conf["outputs"] + 0.08)
            field_conf["dependencies"] = min(1.0, field_conf["dependencies"] + 0.15)

        cap.field_confidence = {k: round(v, 3) for k, v in field_conf.items()}
        cap.confidence = round(min(1.0, sum(FIELD_WEIGHTS[k] * v
                                            for k, v in field_conf.items()) /
                                   sum(FIELD_WEIGHTS.values()) * 1.35), 3)

        if extraction_method == "code_ast_v1":
            cap.evidence_grade = "C"
        elif anchored and code_signals and code_signals.functions:
            cap.evidence_grade = "A"
        elif anchored:
            cap.evidence_grade = "B"
        elif cap.evidence:
            cap.evidence_grade = "D"
        else:
            cap.evidence_grade = "D"
            result.diagnostics.append({
                "level": "warning", "code": "no_evidence",
                "capability": cap.name, "message": "能力没有任何证据，置信度已封顶"})
            cap.confidence = min(cap.confidence, 0.35)

        cap.constraints = [c for c in cap.constraints if not c.startswith("证据等级 ")]
        cap.constraints.append(f"证据等级 {cap.evidence_grade}（A=论文+代码 / B=论文 / C=代码 / D=启发式）")
        cap.tags = sorted(set(cap.tags + [f"grade_{cap.evidence_grade}"]))

        for problem in cap.validate():
            if "未能在原文锚定" in problem:
                continue  # 已在 diagnostics 中单独报告
            result.diagnostics.append({"level": "warning", "code": "schema_validation",
                                       "capability": cap.name, "message": problem})

    @staticmethod
    def _detect_conflicts(result: ExtractionResult) -> None:
        """检测同 comparable_key 下指标值冲突（不可比却被写在一起）。"""
        seen: Dict[str, float] = {}
        for cap in result.capabilities:
            for m in cap.metrics:
                if m.reported is None:
                    continue
                key = m.comparable_key()
                if key in seen and abs(seen[key] - m.reported) > 0.05:
                    result.diagnostics.append({
                        "level": "warning", "code": "metric_conflict",
                        "comparable_key": key, "values": [seen[key], m.reported],
                        "message": "相同协议下报告值不一致，需人工核验"})
                seen.setdefault(key, m.reported)
