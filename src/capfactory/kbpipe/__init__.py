"""知识底座流水线（kbpipe）：文本块 / 图片 / 向量 / PO 图。

注意：包名用 ``kbpipe`` 而不是 ``pipeline``，避免遮蔽 ``capfactory/pipeline.py``
（后者是 CapFactory 主流水线，Web 与 CLI 都依赖它）。
"""

from .chunker import Chunk, chunk_sections, chunk_text, to_items
from .extractor import ExtractionResult, OllamaChat, POExtractor
from .runner import PipelineRunner

__all__ = [
    "Chunk", "chunk_text", "chunk_sections", "to_items",
    "POExtractor", "OllamaChat", "ExtractionResult", "PipelineRunner",
]
