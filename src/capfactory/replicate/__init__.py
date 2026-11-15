"""能力复刻与验证层。"""

from .contract import CONTRACTS, TaskContract, contract_for_prompt, get_contract, infer_task_type, static_check  # noqa: F401
from .dataset import clean_rows, load_csv, load_fasta, materialise, stratified_split  # noqa: F401
from .replicator import Replicator  # noqa: F401
from .sandbox import ExecResult, run_module  # noqa: F401
from .verifier import Verifier, verify_and_attach  # noqa: F401

__all__ = [
    "Replicator",
    "Verifier",
    "verify_and_attach",
    "TaskContract",
    "CONTRACTS",
    "get_contract",
    "contract_for_prompt",
    "infer_task_type",
    "static_check",
    "materialise",
    "load_csv",
    "load_fasta",
    "clean_rows",
    "stratified_split",
    "run_module",
    "ExecResult",
]
