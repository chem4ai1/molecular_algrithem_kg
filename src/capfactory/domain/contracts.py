"""蛋白质 / 分子任务的**接口契约**（插件式注册）.

原 ``replicate/contract.py`` 只有 3 类契约，且 ``runner.py`` 硬编码读取
``sequence,label`` 的 int 标签、只算分类指标。本模块新增 4 类领域契约，
并提供 ``register_domain_contracts()`` 显式注入，做到：

- **不改动原流水线默认行为**：只有显式调用注册后 ``get_contract`` 才认识新类型；
- **给 LLM 明确的生成约束**：``prompt_text`` 可直接拼进 ``CODE_GEN``；
- **给 v2 验证器明确的执行约定**：``evaluation`` 字段声明评测器与数据格式。

注意：新契约由 ``capfactory.domain.validation.DomainVerifier``（v2 路径）执行，
而不是原 ``runner.py``（v1 路径）。原因见 ``docs/MODULE_BREAKDOWN.md`` 1.3。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..replicate.contract import CONTRACTS, TaskContract

SMILES_REGRESSION = TaskContract(
    task_type="smiles_property_regression",
    title="小分子性质回归（SMILES → 连续活性 / ADMET 值）",
    required_functions=["featurize", "build_model"],
    required_constants=["TASK_TYPE"],
    primary_metric="spearman",
    secondary_metrics=["rmse", "mae", "r2"],
    metric_threshold=0.3,
    prompt_text="""TASK_TYPE = "smiles_property_regression"

1. `featurize(molecules: Iterable[str]) -> numpy.ndarray`
   - Input: SMILES strings (length 1-200). Must handle empty input, invalid
     characters, duplicate molecules.
   - Output: float32 2-D array (n_samples, n_features), finite, deterministic.
   - Recommended: character/atom-count descriptors, hashed Morgan-like fragments,
     physicochemical proxies. RDKit is NOT available in the verifier sandbox.
2. `build_model(**kwargs) -> estimator`
   - sklearn-compatible `.fit(X, y)` / `.predict(X)` with FIXED random_state.
   - `y` is continuous (float), do not binarise.

Forbidden: network, file I/O, subprocess, eval/exec, GPU-only libraries,
returning constant predictions, reading the test labels.""",
)

PROTEIN_SEQUENCE_REGRESSION = TaskContract(
    task_type="protein_sequence_regression",
    title="蛋白/多肽序列连续值预测（pIC50 / 半衰期 / 溶解度 / 稳定性）",
    required_functions=["featurize", "build_model"],
    required_constants=["TASK_TYPE"],
    primary_metric="spearman",
    secondary_metrics=["rmse", "mae", "r2"],
    metric_threshold=0.3,
    prompt_text="""TASK_TYPE = "protein_sequence_regression"

1. `featurize(sequences: Iterable[str]) -> numpy.ndarray`
   - One-letter amino-acid sequences; handle empty input, unknown residues X/B/Z/U,
     very short (1-2 aa) and duplicate sequences.
   - Deterministic float32 matrix (n_samples, n_features), no NaN/Inf.
   - Recommended: AAC, DPC, k-mer, length/net-charge/hydrophobicity proxies.
2. `build_model(**kwargs) -> estimator` with `.fit(X, y)` / `.predict(X)`,
   fixed seed, y continuous.

Forbidden: network, file I/O, subprocess, eval/exec, constant predictions.""",
)

PAIRWISE_BINDING_REGRESSION = TaskContract(
    task_type="pairwise_binding_regression",
    title="成对输入结合亲和力预测（序列 × SMILES / 序列 × 序列）",
    required_functions=["featurize", "build_model"],
    required_constants=["TASK_TYPE"],
    primary_metric="spearman",
    secondary_metrics=["rmse", "mae", "r2"],
    metric_threshold=0.3,
    prompt_text="""TASK_TYPE = "pairwise_binding_regression"

1. `featurize(pairs: Iterable[tuple[str, str]]) -> numpy.ndarray`
   - Each pair is (protein/peptide sequence, SMILES or second sequence).
   - Encode BOTH sides (e.g. AAC for sequence + atom counts for SMILES) and
     concatenate; output a finite float32 (n_samples, n_features) matrix.
2. `build_model(**kwargs) -> estimator` with `.fit(X, y)` / `.predict(X)`,
   y = pIC50 / Kd / binding score (continuous), fixed seed.

Forbidden: network, file I/O, subprocess, eval/exec, leaking test targets.""",
)

MOLECULAR_GENERATION = TaskContract(
    task_type="molecular_generation",
    title="分子/多肽生成（de novo design）",
    required_functions=["generate", "featurize"],
    required_constants=["TASK_TYPE"],
    primary_metric="validity",
    secondary_metrics=["uniqueness", "novelty", "diversity"],
    metric_threshold=0.5,
    prompt_text="""TASK_TYPE = "molecular_generation"

1. `generate(n: int, seed: int = 42) -> list[str]`
   - Deterministic given (n, seed); returns exactly n SMILES or peptide strings.
2. `featurize(molecules: Iterable[str]) -> numpy.ndarray`
   - Used by the scorer to compute diversity; finite float32 (n, d).

Quality gates: validity (parseable characters, length 1-200), uniqueness,
novelty vs training set, internal diversity. No network, no file I/O,
no returning the training set verbatim.""",
)

DOMAIN_CONTRACTS: Dict[str, TaskContract] = {
    c.task_type: c for c in (
        SMILES_REGRESSION, PROTEIN_SEQUENCE_REGRESSION,
        PAIRWISE_BINDING_REGRESSION, MOLECULAR_GENERATION,
    )
}

# 契约 → v2 评测器与数据格式（供 DomainVerifier 分派）
DOMAIN_EVALUATION: Dict[str, Dict[str, Any]] = {
    "smiles_property_regression": {
        "evaluator": "regression", "columns": ["smiles", "value"],
        "primary": "spearman", "direction": "higher",
    },
    "protein_sequence_regression": {
        "evaluator": "regression", "columns": ["sequence", "value"],
        "primary": "spearman", "direction": "higher",
    },
    "pairwise_binding_regression": {
        "evaluator": "regression", "columns": ["item_a", "item_b", "value"],
        "primary": "spearman", "direction": "higher",
    },
    "molecular_generation": {
        "evaluator": "generation", "columns": ["smiles"],
        "primary": "validity", "direction": "higher",
    },
}


def register_domain_contracts() -> List[str]:
    """把领域契约注入全局 ``CONTRACTS``（显式调用才生效）。返回新增类型。"""
    added = []
    for key, contract in DOMAIN_CONTRACTS.items():
        if key not in CONTRACTS:
            added.append(key)
        CONTRACTS[key] = contract
    return added


def get_domain_contract(task_type: str) -> TaskContract:
    """取领域契约；未知类型抛出明确错误（不静默回退到肽二分类）。"""
    if task_type not in DOMAIN_CONTRACTS:
        raise KeyError(f"未知领域任务类型 {task_type!r}，可选：{sorted(DOMAIN_CONTRACTS)}")
    return DOMAIN_CONTRACTS[task_type]


def infer_domain_task_type(text: str) -> str:
    """从能力描述推断领域任务类型（比原 ``infer_task_type`` 更细）。"""
    low = (text or "").lower()
    if any(k in low for k in ("generation", "de novo", "diffusion", "design molecules",
                              "生成模型", "denovo")):
        return "molecular_generation"
    if any(k in low for k in ("pairwise", "protein-ligand", "complex", "binding affinity",
                              "interaction", "pic50", "kd", "结合")):
        return "pairwise_binding_regression"
    if any(k in low for k in ("smiles", "small molecule", "molecular graph", "compound",
                              "rdkit", "molecule", "小分子")):
        return "smiles_property_regression"
    if any(k in low for k in ("regression", "continuous", "half-life", "solubility",
                              "ic50", "affinity", "stability", "回归", "连续值")):
        return "protein_sequence_regression"
    return "protein_sequence_regression"


def contract_for_domain_prompt(task_type: str) -> str:
    c = get_domain_contract(task_type)
    return f"## Domain Contract: {c.title}\n\n{c.prompt_text}\n\n" \
           f"Primary metric: {c.primary_metric} (threshold {c.metric_threshold})"
