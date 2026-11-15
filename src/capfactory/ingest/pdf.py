"""PDF 解析：把论文转换为「章节 → 文本」结构，供能力抽取使用.

优先使用 pymupdf4llm 的 Markdown 转换（保留标题层级），
失败时退化为按页抽取 + 正则切分标题。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..utils import read_text, truncate, write_json, ensure_dir

logger = logging.getLogger(__name__)

HEADING_RE = re.compile(r"^#{1,3}\s+(.+)$", re.MULTILINE)
NUMBERED_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*\.?\s+)([A-Z][A-Za-z0-9 ,\-:]{2,80})$", re.MULTILINE
)
KNOWN_SECTIONS = [
    "abstract", "introduction", "related work", "background", "method", "methods",
    "methodology", "approach", "materials and methods", "experiments", "experimental setup",
    "results", "discussion", "conclusion", "conclusions", "limitations", "appendix",
]


def _read_markdown(pdf_path: Path) -> str:
    """使用 pymupdf4llm 转 Markdown；不可用时退化为纯文本."""
    import contextlib
    import io
    import threading

    try:
        import pymupdf4llm  # type: ignore

        # pymupdf4llm 会拉起布局分析子进程，其非 UTF-8 输出会在 reader 线程里抛错，
        # 这里屏蔽该噪声（不影响正文抽取结果）。
        old_hook = threading.excepthook
        threading.excepthook = lambda args: None  # type: ignore[assignment]
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                md = pymupdf4llm.to_markdown(str(pdf_path))
        finally:
            threading.excepthook = old_hook
        if md and len(md) > 500:
            return md
    except Exception as exc:  # pragma: no cover - 依赖环境
        logger.debug("pymupdf4llm 转 Markdown 失败：%s", exc)
    try:
        import pymupdf  # type: ignore

        doc = pymupdf.open(str(pdf_path))
        return "\n\n".join(page.get_text("text") for page in doc)
    except Exception as exc:
        logger.warning("PDF 文本抽取失败 %s：%s", pdf_path, exc)
        return ""


def split_sections(markdown: str) -> Dict[str, str]:
    """把 Markdown 文本切分为章节字典。"""
    if not markdown:
        return {}
    matches = list(HEADING_RE.finditer(markdown))
    sections: Dict[str, str] = {}
    if matches:
        for i, m in enumerate(matches):
            name = re.sub(r"[*_`#]", "", m.group(1)).strip()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
            body = markdown[start:end].strip()
            if len(body) < 80:
                continue
            key = name or f"Section {i+1}"
            if key in sections:
                key = f"{key} ({i+1})"
            sections[key] = body
    if len(sections) >= 3:
        return sections

    # 退化：按编号标题切分
    sections = {}
    numbered = list(NUMBERED_RE.finditer(markdown))
    for i, m in enumerate(numbered):
        name = m.group(1).strip()
        start = m.end()
        end = numbered[i + 1].start() if i + 1 < len(numbered) else len(markdown)
        body = markdown[start:end].strip()
        if len(body) >= 120:
            sections[name] = body
    if sections:
        return sections

    # 最后兜底：按固定窗口切块
    from ..utils import chunk_text

    chunks = chunk_text(markdown, 4000, 200)[:12]
    return {f"chunk_{i}": c for i, c in enumerate(chunks)}


def extract_abstract(markdown: str, sections: Dict[str, str]) -> str:
    """从章节或正文头部抽取摘要。"""
    for key, body in sections.items():
        if "abstract" in key.lower():
            return re.sub(r"\s+", " ", body)[:3000]
    m = re.search(r"(?i)abstract[\s\.:—-]*(.{200,2500}?)(?:\n#{1,3}\s|\n\d\.\s)", markdown, re.DOTALL)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    return re.sub(r"\s+", " ", markdown[:1500])


def parse_pdf(pdf_path: Path, out_dir: Optional[Path] = None) -> Dict[str, object]:
    """解析 PDF，返回 ``{"abstract", "sections", "markdown_path", "n_sections", "full_chars"}``。"""
    pdf_path = Path(pdf_path)
    markdown = _read_markdown(pdf_path)
    sections = split_sections(markdown)
    abstract = extract_abstract(markdown, sections)
    result: Dict[str, object] = {
        "abstract": abstract,
        "sections": sections,
        "n_sections": len(sections),
        "full_chars": len(markdown),
        "markdown_path": "",
    }
    if out_dir and markdown:
        out_dir = ensure_dir(Path(out_dir))
        md_path = out_dir / f"{pdf_path.stem}.md"
        md_path.write_text(markdown, encoding="utf-8")
        result["markdown_path"] = str(md_path)
    logger.info("PDF 解析完成：%s（%d 章节，%d 字符）", pdf_path.name, len(sections), len(markdown))
    return result


def find_code_urls(text: str) -> List[str]:
    """从论文全文中抽取 GitHub 链接。"""
    urls = re.findall(r"https?://github\.com/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+", text or "")
    seen, out = set(), []
    for u in urls:
        u = u.rstrip(".,;)").replace(".git", "")
        if u.lower() in seen:
            continue
        seen.add(u.lower())
        out.append(u)
    return out
