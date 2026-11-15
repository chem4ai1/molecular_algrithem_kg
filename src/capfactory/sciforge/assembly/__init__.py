"""Stage3 Assembly：把 Stage0–2 抽取内容确定性导入图谱。"""
from .contract import (Stage3Input, NormalizedInput, LinkPlan,
                       Stage3Manifest)
from .assemble import assemble_stage3

__all__ = ["assemble_stage3", "Stage3Manifest", "Stage3Input",
           "NormalizedInput", "LinkPlan"]
