"""声明式抽取：抽取对象/字段/prompt 写在 data/extract_target，代码只读配置执行。"""
from . import loader
from .refine import (apply_to_graph, build_prompt, locate_paragraphs,
                     parse_payload, run_refine)
from . import render as render_mod
from .render import contract_text, render as render_prompt, stages
from .schema import FieldSpec, RefineSpec, StageSpec

__all__ = ["loader", "render_mod", "render_prompt", "stages", "contract_text", "run_refine",
           "locate_paragraphs", "build_prompt", "parse_payload",
           "apply_to_graph", "StageSpec", "RefineSpec", "FieldSpec"]
