"""从 PDF 抽取页面/图表图像（PyMuPDF 渲染，无需外部服务）.

策略：

* 默认渲染**整页**（1280px 宽，约 150–400KB PNG）——VL 模型对整页版式
  （标题、图注、坐标轴、表格）理解优于裁切碎片；
* ``pick_figure_pages`` 用启发式挑页：出现 ``Figure N``/``Table N`` 且该页
  内嵌图片较多，避免把纯文字页送去 VL（省额度）；
* 同一页重复渲染按内容 sha 去重（见 ``store.ImageLibrary``）。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

FIG_RE = re.compile(r"\b(Figure|Fig\.|Table)\s*(\d+)", re.I)


def _fitz():
    import fitz  # PyMuPDF
    return fitz


def page_count(pdf_path: str | Path) -> int:
    try:
        with _fitz().open(str(pdf_path)) as doc:
            return doc.page_count
    except Exception:  # noqa: BLE001
        return 0


def render_page(pdf_path: str | Path, page: int = 0, *,
                width: int = 1280, dpi: int = 144) -> bytes:
    """渲染单页为 PNG 字节。``page`` 从 0 开始。"""
    fitz = _fitz()
    with fitz.open(str(pdf_path)) as doc:
        if page < 0 or page >= doc.page_count:
            raise IndexError(f"page {page} 超出范围 0..{doc.page_count-1}")
        p = doc[page]
        zoom = max(1.0, width / max(p.rect.width, 1.0))
        if dpi and dpi > 0:
            zoom = max(zoom, dpi / 72.0)
        pix = p.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return pix.tobytes("png")


def pick_figure_pages(pdf_path: str | Path, *, max_pages: int = 3,
                      start: int = 0, scan: int = 14) -> List[Dict[str, Any]]:
    """启发式挑「含图/表」的页，返回 ``[{page, figures, images, chars}]``。"""
    fitz = _fitz()
    out: List[Dict[str, Any]] = []
    try:
        with fitz.open(str(pdf_path)) as doc:
            end = min(doc.page_count, start + scan)
            for i in range(start, end):
                p = doc[i]
                text = p.get_text("text") or ""
                labels = sorted({f"{m.group(1).title()} {m.group(2)}"
                                 for m in FIG_RE.finditer(text)})
                n_img = len(p.get_images(full=True) or [])
                if labels or n_img:
                    out.append({"page": i, "figures": labels[:6],
                                "images": n_img, "chars": len(text)})
    except Exception:  # noqa: BLE001
        return []
    # 优先：有图注且图片多 → 页内文字少的图页；再按页码
    out.sort(key=lambda x: (-len(x["figures"]), -x["images"], x["page"]))
    return out[:max_pages]


def render_pdf_pages(pdf_path: str | Path, pages: Sequence[int], *,
                     width: int = 1280) -> List[Dict[str, Any]]:
    """批量渲染，返回 ``[{page, png, sha256, bytes}]``。"""
    out = []
    for i in pages:
        try:
            png = render_page(pdf_path, i, width=width)
        except Exception as exc:  # noqa: BLE001
            out.append({"page": i, "error": str(exc)[:160]})
            continue
        out.append({"page": i, "png": png,
                    "sha256": hashlib.sha256(png).hexdigest(),
                    "bytes": len(png)})
    return out
