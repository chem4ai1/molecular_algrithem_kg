"""任务接口契约：定义「可被验证的算法模块」必须满足的形状.

不同任务类型有不同契约（对应需求中的「支持不同任务类型的验证配置」）。
契约既是给 LLM 的生成约束，也是静态校验与动态验证的依据。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TaskContract:
    """一个任务类型的契约定义。"""

    task_type: str
    title: str
    required_functions: List[str]
    required_constants: List[str]
    prompt_text: str
    primary_metric: str = "roc_auc"
    secondary_metrics: List[str] = field(default_factory=lambda: ["accuracy", "f1", "mcc"])
    metric_threshold: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_type": self.task_type,
            "title": self.title,
            "required_functions": self.required_functions,
            "required_constants": self.required_constants,
            "primary_metric": self.primary_metric,
            "metric_threshold": self.metric_threshold,
        }


SEQ_BINARY = TaskContract(
    task_type="sequence_binary_classification",
    title="肽序列二分类（毒性 / 抗菌 / 溶血等性质预测）",
    required_functions=["featurize", "build_model"],
    required_constants=["TASK_TYPE"],
    primary_metric="roc_auc",
    secondary_metrics=["accuracy", "f1", "mcc", "average_precision"],
    metric_threshold=0.6,
    prompt_text="""TASK_TYPE = "sequence_binary_classification"

# Required public API
1. `TASK_TYPE: str` — must equal "sequence_binary_classification".
2. `featurize(sequences: Iterable[str]) -> numpy.ndarray`
   - Input: peptide sequences using one-letter amino-acid codes (may be a str or a list).
   - Output: 2-D float32 array of shape (n_samples, n_features); row i corresponds to
     sequences[i]; the same input must always produce the same output; no NaN/Inf.
   - Must handle: empty input (return shape (0, n_features)), unknown characters,
     very short sequences (length 1-2), and duplicate sequences.
3. `build_model(**kwargs) -> estimator`
   - Returns a scikit-learn compatible estimator exposing `.fit(X, y)` and either
     `.predict_proba(X)` (preferred, returns shape (n, 2)) or `.predict(X)`.
   - Must be deterministic (fixed random_state) and trainable on <= 5000 samples
     within ~60 seconds on CPU with n_jobs=1.

# Forbidden
- Network access, file I/O outside the working directory, `os.system`, `subprocess`,
  `eval`, `exec`, `importlib`, downloading models, GPU-only libraries.
- Returning constant predictions or random outputs.

# Recommended
- Amino-acid composition (AAC), dipeptide composition (DPC), k-mer composition,
  physicochemical descriptors (length, net charge, hydrophobicity, aromaticity, pI proxy).
- Class-imbalance handling via `class_weight="balanced"`.""",
)

TABULAR_BINARY = TaskContract(
    task_type="tabular_binary_classification",
    title="表格数据二分类",
    required_functions=["featurize", "build_model"],
    required_constants=["TASK_TYPE"],
    primary_metric="roc_auc",
    metric_threshold=0.6,
    prompt_text="""TASK_TYPE = "tabular_binary_classification"
`featurize(rows: Iterable[dict]) -> numpy.ndarray` builds a numeric feature matrix from
records (missing values must be handled); `build_model(**kwargs)` returns a scikit-learn
compatible estimator with `.fit` / `.predict_proba`.""",
)

TABULAR_REGRESSION = TaskContract(
    task_type="tabular_regression",
    title="表格数据回归（活性 / 浓度 / 半衰期预测）",
    required_functions=["featurize", "build_model"],
    required_constants=["TASK_TYPE"],
    primary_metric="spearman",
    secondary_metrics=["rmse", "mae"],
    metric_threshold=0.3,
    prompt_text="""TASK_TYPE = "tabular_regression"
`featurize(rows: Iterable[dict]) -> numpy.ndarray`; `build_model(**kwargs)` returns an
estimator with `.fit(X, y)` and `.predict(X)` returning continuous values.""",
)

CONTRACTS: Dict[str, TaskContract] = {
    c.task_type: c for c in (SEQ_BINARY, TABULAR_BINARY, TABULAR_REGRESSION)
}


def get_contract(task_type: str) -> TaskContract:
    """按任务类型取契约，未知类型回退到序列二分类。"""
    return CONTRACTS.get(task_type, SEQ_BINARY)


def infer_task_type(text: str) -> str:
    """从能力文本推断任务类型。"""
    low = (text or "").lower()
    if any(k in low for k in ("regression", "ic50", "hemolytic concentration", "half-life",
                              "predict concentration", "回归", "活性值")):
        return "tabular_regression"
    if any(k in low for k in ("tabular", "表格", "descriptor table")):
        return "tabular_binary_classification"
    return "sequence_binary_classification"


def contract_for_prompt(task_type: str) -> str:
    """渲染给 LLM 的契约说明。"""
    c = get_contract(task_type)
    return f"## Contract: {c.title}\n\n{c.prompt_text}"


def static_check(source: str, task_type: str) -> Dict[str, Any]:
    """静态检查：语法、必需符号、禁用 API、危险导入。"""
    contract = get_contract(task_type)
    result: Dict[str, Any] = {
        "syntax_ok": False,
        "missing_functions": [],
        "missing_constants": [],
        "forbidden_calls": [],
        "imports": [],
        "n_lines": len(source.splitlines()) if source else 0,
        "has_docstring": False,
    }
    if not source or not source.strip():
        result["error"] = "empty source"
        return result
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        result["error"] = f"SyntaxError: {exc}"
        return result
    result["syntax_ok"] = True
    result["has_docstring"] = bool(ast.get_docstring(tree))

    functions = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assignments = {t.id for n in ast.walk(tree) if isinstance(n, ast.Assign)
                   for t in n.targets if isinstance(t, ast.Name)}
    # 兼容带类型注解的常量声明： TASK_TYPE: str = "..."
    assignments |= {n.target.id for n in ast.walk(tree)
                    if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}
    result["missing_functions"] = [f for f in contract.required_functions if f not in functions]
    result["missing_constants"] = [c for c in contract.required_constants if c not in assignments]

    forbidden_modules = {"subprocess", "socket", "shutil", "ctypes", "multiprocessing", "importlib"}
    forbidden_calls = {"eval", "exec", "compile", "__import__"}
    imports: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in forbidden_calls:
            result["forbidden_calls"].append(node.func.id)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"system", "popen", "run", "Popen", "urlopen"}:
                result["forbidden_calls"].append(node.func.attr)
    result["imports"] = sorted(set(imports))
    result["forbidden_imports"] = sorted(set(imports) & forbidden_modules)
    result["forbidden_calls"] = sorted(set(result["forbidden_calls"]))
    result["ok"] = (
        result["syntax_ok"]
        and not result["missing_functions"]
        and not result["missing_constants"]
        and not result["forbidden_calls"]
        and not result["forbidden_imports"]
    )
    return result
