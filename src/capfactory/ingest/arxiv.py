"""arXiv 检索与 PDF 下载.

直接使用 arXiv Atom API（无需 Key），并做本地缓存，避免重复请求触发限流。
"""

from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from ..config import Settings, get_settings
from ..utils import ensure_dir, read_json, slugify, write_json

logger = logging.getLogger(__name__)

ARXIV_API = "https://export.arxiv.org/api/query"
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"


def _text(node: Optional[ET.Element]) -> str:
    return (node.text or "").strip() if node is not None else ""


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


class ArxivClient:
    """arXiv 检索客户端。"""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.cache_dir = ensure_dir(self.settings.path("cache_dir") / "arxiv")
        self.rate_limit = float(self.settings.ingest.get("arxiv_rate_limit_seconds", 3.0))
        self._last_call = 0.0

    def _throttle(self) -> None:
        delta = time.time() - self._last_call
        if delta < self.rate_limit:
            time.sleep(self.rate_limit - delta)
        self._last_call = time.time()

    def search(self, query: str, max_results: int = 8, sort: str = "relevance") -> List[Dict[str, Any]]:
        """检索论文，返回标准化的元信息列表。"""
        import requests

        cache_file = self.cache_dir / f"{slugify(query, 60)}_{max_results}_{sort}.json"
        cached = read_json(cache_file)
        if cached:
            logger.info("arXiv 命中缓存：%s (%d 条)", query, len(cached))
            return cached

        self._throttle()
        params = {
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": sort,
            "sortOrder": "descending",
        }
        url = f"{ARXIV_API}?{ '&'.join(f'{k}={quote_plus(str(v))}' for k, v in params.items()) }"
        logger.info("arXiv 检索：%s", query)
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("arXiv 检索失败：%s", exc)
            return []

        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError as exc:
            logger.warning("arXiv 响应解析失败：%s", exc)
            return []

        results: List[Dict[str, Any]] = []
        for entry in root.findall(f"{ATOM}entry"):
            raw_id = _text(entry.find(f"{ATOM}id"))
            arxiv_id = raw_id.rsplit("/", 1)[-1]
            pdf_url = ""
            for link in entry.findall(f"{ATOM}link"):
                if link.get("title") == "pdf" or link.get("type") == "application/pdf":
                    pdf_url = link.get("href", "")
            year = None
            published = _text(entry.find(f"{ATOM}published"))
            if published[:4].isdigit():
                year = int(published[:4])
            results.append({
                "arxiv_id": arxiv_id,
                "title": _clean(_text(entry.find(f"{ATOM}title"))),
                "abstract": _clean(_text(entry.find(f"{ATOM}summary"))),
                "authors": [_text(a.find(f"{ATOM}name")) for a in entry.findall(f"{ATOM}author")],
                "published": published,
                "year": year,
                "url": raw_id,
                "pdf_url": pdf_url or f"https://arxiv.org/pdf/{arxiv_id}",
                "primary_category": (entry.find(f"{ARXIV_NS}primary_category").get("term")
                                     if entry.find(f"{ARXIV_NS}primary_category") is not None else ""),
                "comment": _clean(_text(entry.find(f"{ARXIV_NS}comment"))),
            })
        write_json(cache_file, results)
        logger.info("arXiv 返回 %d 条结果", len(results))
        return results

    def download_pdf(self, arxiv_id: str, dest_dir: Path) -> Optional[Path]:
        """下载 PDF 到 ``dest_dir``，返回本地路径。"""
        import requests

        dest_dir = ensure_dir(dest_dir)
        target = dest_dir / f"{arxiv_id.replace('/', '_')}.pdf"
        if target.exists() and target.stat().st_size > 20_000:
            return target
        url = f"https://arxiv.org/pdf/{arxiv_id}"
        for attempt in range(3):
            try:
                resp = requests.get(url, timeout=120)
                if resp.status_code == 200 and resp.content[:4] == b"%PDF":
                    target.write_bytes(resp.content)
                    logger.info("已下载 PDF：%s (%.1f KB)", target.name, len(resp.content) / 1024)
                    return target
                logger.warning("PDF 下载异常 %s: HTTP %s", arxiv_id, resp.status_code)
            except Exception as exc:
                logger.warning("PDF 下载失败 %s（第 %d 次）：%s", arxiv_id, attempt + 1, exc)
            time.sleep(2 + attempt * 3)
        return None
