"""视觉层：PDF 页面渲染 + OpenRouter VL 图注 + 图片库."""

from .extract import page_count, pick_figure_pages, render_page, render_pdf_pages
from .prompts import CAPTION_PROMPT, caption_prompt
from .store import ImageLibrary
from .vl_client import DEFAULT_MODEL, OpenRouterVL, key_from_file

__all__ = [
    "OpenRouterVL", "DEFAULT_MODEL", "key_from_file",
    "ImageLibrary", "CAPTION_PROMPT", "caption_prompt",
    "render_page", "render_pdf_pages", "pick_figure_pages", "page_count",
]
