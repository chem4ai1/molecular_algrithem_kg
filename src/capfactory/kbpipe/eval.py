"""兼容 shim（已归档）：实现见 ``capfactory.legacy.eval_extraction``。

新代码请用 ``capfactory.ontology.prompts`` / ``capfactory.kbpipe.extractor``。
"""
from ..legacy.eval_extraction import *  # noqa: F401,F403
from ..legacy.eval_extraction import (  # noqa: F401
    FREE_PROMPT, RECORD_FIELDS, _json_of, _types_of, _rels_of,
    metrics_raw, metrics_concepts, pick_chunks, run_group, compare,
    build_record_chunks, roundtrip, to_markdown,
)

__all__ = ["FREE_PROMPT", "RECORD_FIELDS", "metrics_raw", "metrics_concepts",
           "pick_chunks", "run_group", "compare", "build_record_chunks",
           "roundtrip", "to_markdown"]
