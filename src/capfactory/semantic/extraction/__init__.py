"""语义层 v4.1 抽取方案（新）：契约/prompt/校验/编排。

旧链路 `sciforge/stage_extract.py` + `deepdive.py` 仍保留为 legacy，
其输出结构面向旧 TBox，与语义层大面积错配；新方案从这里进入。
"""
from .contracts import E_CONTRACTS, NON_LLM, contract_text, llm_fields_of
from .prompts import PROMPTS, render, stages
from .validator import validate, fatal, retry_contract, cross_check

__all__ = ["E_CONTRACTS", "NON_LLM", "contract_text", "llm_fields_of",
           "PROMPTS", "render", "stages", "validate", "fatal",
           "retry_contract", "cross_check"]
