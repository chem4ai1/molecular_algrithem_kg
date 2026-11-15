"""MinerU 适配层：双栏 PDF 走 MinerU，单栏走 PyMuPDF.

为什么按版式分流：

* PyMuPDF 按「文本块」抽取，双栏论文的左右栏会被按 y 坐标交错读出，
  句子在栏间跳跃，切块后语义断裂；
* MinerU（docker ``mineru-api``，:8886）做版面分析 + 阅读顺序恢复，
  双栏、表格、公式都能按人类阅读顺序输出 Markdown；
* 但 MinerU 单篇约 60–90 s（GPU、pipeline 后端），单栏论文用 PyMuPDF
  只要 0.1–0.3 s。**只对双栏用 MinerU**，是成本与质量的折中。

双栏判定：取每页文本块 bbox，若「右边界落在左半页」与「左边界落在右半页」
的块各 ≥3 且合计占比 ≥75%，该页记一票；多数页投票即判双栏。
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from ..utils import now_iso
from .pdf import parse_pdf as parse_pdf_pymupdf

DEFAULT_BASE = "http://127.0.0.1:8886"
DEFAULT_BACKEND = "pipeline"      # hybrid-auto-engine 需要额外 VLM 服务
DEFAULT_LANG = "en"


# ---------------------------------------------------------------------------
# 版式判定
# ---------------------------------------------------------------------------
@dataclass
class LayoutInfo:
    two_column: bool
    votes: int
    pages_checked: int
    ratio: float

    def to_dict(self) -> Dict[str, Any]:
        return {"two_column": self.two_column, "votes": self.votes,
                "pages_checked": self.pages_checked, "ratio": round(self.ratio, 3)}


def detect_two_column(pdf_path: str | Path, *, pages: int = 4,
                      min_blocks: int = 8) -> LayoutInfo:
    """按文本块 x 坐标判定是否双栏（不依赖 PDF 元数据）。"""
    try:
        import fitz  # PyMuPDF
    except Exception:  # noqa: BLE001
        return LayoutInfo(False, 0, 0, 0.0)
    votes = checked = 0
    try:
        with fitz.open(str(pdf_path)) as doc:
            for i in range(min(pages, doc.page_count)):
                page = doc[i]
                width = page.rect.width or 1.0
                blocks = [b for b in page.get_text("blocks") if (b[4] or "").strip()]
                if len(blocks) < min_blocks:
                    continue
                checked += 1
                left = sum(1 for b in blocks if b[2] <= width * 0.52)
                right = sum(1 for b in blocks if b[0] >= width * 0.48)
                if left >= 3 and right >= 3 and (left + right) / len(blocks) >= 0.75:
                    votes += 1
    except Exception:  # noqa: BLE001
        return LayoutInfo(False, 0, 0, 0.0)
    ratio = votes / checked if checked else 0.0
    return LayoutInfo(bool(checked and ratio >= 0.6), votes, checked, ratio)


# ---------------------------------------------------------------------------
# MinerU HTTP 客户端（multipart 手写，零新增依赖）
# ---------------------------------------------------------------------------
class MinerUClient:
    def __init__(self, base_url: str = DEFAULT_BASE, *, timeout: int = 600,
                 backend: str = DEFAULT_BACKEND, lang: str = DEFAULT_LANG) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.backend = backend
        self.lang = lang
        self.stats = {"calls": 0, "errors": 0, "seconds": 0.0, "chars": 0}

    def available(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/openapi.json", timeout=5) as r:
                info = json.loads(r.read().decode("utf-8"))
            return "/file_parse" in (info.get("paths") or {})
        except Exception:  # noqa: BLE001
            return False

    def parse(self, pdf_path: str | Path, *,
              start_page: int = 0, end_page: int = 99999) -> Dict[str, Any]:
        """调用 ``/file_parse`` 拿 Markdown。失败抛 ``RuntimeError``。"""
        path = Path(pdf_path)
        boundary = f"----CapFactory{uuid.uuid4().hex[:12]}"
        fields = {
            "backend": self.backend,
            "lang_list": self.lang,
            "parse_method": "auto",
            "formula_enable": "true",
            "table_enable": "true",
            "return_md": "true",
            "return_content_list": "false",
            "return_images": "false",
            "response_format_zip": "false",
            "start_page_id": str(start_page),
            "end_page_id": str(end_page),
        }
        body = bytearray()
        for k, v in fields.items():
            body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n"
                     f"{v}\r\n").encode("utf-8")
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; "
                 f"filename=\"{path.name}\"\r\nContent-Type: application/pdf\r\n\r\n"
                 ).encode("utf-8")
        body += path.read_bytes() + b"\r\n"
        body += f"--{boundary}--\r\n".encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/file_parse", data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                payload = json.loads(r.read().decode("utf-8"))
            self.stats["calls"] += 1
            self.stats["seconds"] += time.time() - t0
        except urllib.error.HTTPError as exc:
            self.stats["errors"] += 1
            raise RuntimeError(f"MinerU HTTP {exc.code}: "
                               f"{exc.read().decode('utf-8', 'replace')[:200]}") from exc
        except Exception as exc:  # noqa: BLE001
            self.stats["errors"] += 1
            raise RuntimeError(f"MinerU 请求失败：{exc}") from exc

        results = payload.get("results") or {}
        if not results:
            raise RuntimeError(f"MinerU 返回无结果：{str(payload)[:200]}")
        item = next(iter(results.values()))
        md = item.get("md_content") or item.get("md") or ""
        if not md.strip():
            raise RuntimeError("MinerU 返回空 Markdown")
        self.stats["chars"] += len(md)
        return {"md": md, "chars": len(md), "backend": payload.get("backend", self.backend),
                "version": payload.get("version", ""),
                "seconds": round(time.time() - t0, 1)}


# ---------------------------------------------------------------------------
# 智能分流
# ---------------------------------------------------------------------------
def parse_pdf_smart(pdf_path: str | Path, *, force: Optional[str] = None,
                    client: Optional[MinerUClient] = None,
                    out_dir: Optional[Path] = None) -> Dict[str, Any]:
    """双栏 → MinerU；单栏 → PyMuPDF；MinerU 失败自动回退 PyMuPDF。

    ``force`` 可取 ``"mineru"`` / ``"pymupdf"`` / ``None``（自动）。
    返回结构与 ``ingest.pdf.parse_pdf`` 一致，另加 ``parser`` / ``layout`` 字段。
    """
    path = Path(pdf_path)
    layout = detect_two_column(path)
    use_mineru = (force == "mineru") or (force is None and layout.two_column)
    doc: Dict[str, Any] = {}
    if use_mineru:
        cli = client or MinerUClient()
        try:
            got = cli.parse(path)
            from .pdf import extract_abstract, split_sections
            sections = split_sections(got["md"])
            doc = {
                "abstract": extract_abstract(got["md"], sections),
                "sections": sections,
                "n_sections": len(sections),
                "full_chars": got["chars"],
                "markdown": got["md"],
                "parser": "mineru",
                "mineru_backend": got["backend"],
                "mineru_seconds": got["seconds"],
            }
        except Exception as exc:  # noqa: BLE001
            doc = {}
            layout_fallback_reason = str(exc)[:200]
    if not doc:
        doc = parse_pdf_pymupdf(path, out_dir) if out_dir else parse_pdf_pymupdf(path)
        doc["parser"] = "pymupdf"
        if use_mineru:
            doc["mineru_failed"] = locals().get("layout_fallback_reason", "")
    doc["layout"] = layout.to_dict()
    doc["parsed_at"] = now_iso()
    if out_dir and doc.get("markdown"):
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{path.stem}.md").write_text(doc["markdown"], encoding="utf-8")
    doc.pop("markdown", None)
    return doc
