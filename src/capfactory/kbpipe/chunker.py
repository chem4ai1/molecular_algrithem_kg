"""章节 → 检索/抽取块（按段落聚合，句子级兜底，带重叠）.

为什么不用固定窗口：论文的「方法/结果/局限」段落是语义单元，
按段落聚合能让一个块内自洽；固定 token 窗口会把表格前后的句子割裂。
重叠（``overlap``）用于避免边界处丢失主语。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

SENT_SPLIT = re.compile(r"(?<=[。．.!?！？])\s+|\n{2,}")
MIN_CHUNK = 160


@dataclass
class Chunk:
    id: str
    doc_id: str
    section: str
    order: int
    text: str
    chars: int = 0

    def __post_init__(self) -> None:
        self.chars = len(self.text)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _hash(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=8).hexdigest()[:12]


def chunk_text(text: str, *, max_chars: int = 1600, overlap: int = 180,
               min_chars: int = MIN_CHUNK) -> List[str]:
    """把长文本切成不超过 ``max_chars`` 的块。"""
    text = re.sub(r"[ \t]+", " ", (text or "").strip())
    if len(text) <= max_chars:
        return [text] if len(text) >= min_chars else ([text] if text else [])
    paras = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: List[str] = []
    buf = ""
    for p in paras:
        if len(buf) + len(p) + 1 <= max_chars:
            buf = f"{buf}\n\n{p}".strip()
            continue
        if buf:
            chunks.append(buf)
        if len(p) <= max_chars:
            buf = p
            continue
        # 超长段落：按句子切
        sents = [s for s in SENT_SPLIT.split(p) if s]
        cur = ""
        for s in sents:
            if len(cur) + len(s) + 1 <= max_chars:
                cur = f"{cur} {s}".strip()
            else:
                if cur:
                    chunks.append(cur)
                cur = s
        buf = cur
    if buf:
        chunks.append(buf)
    # 加重叠
    if overlap > 0 and len(chunks) > 1:
        out = [chunks[0]]
        for prev, cur in zip(chunks, chunks[1:]):
            tail = prev[-overlap:]
            out.append((tail + "\n" + cur).strip())
        chunks = out
    return [c for c in chunks if len(c) >= min_chars or not chunks]


def chunk_sections(sections: Dict[str, str], doc_id: str, *,
                   max_chars: int = 1600, overlap: int = 180,
                   sections_keep: Optional[Sequence[str]] = None) -> List[Chunk]:
    """把 ``{section: text}`` 切成带序号的块。"""
    order = 0
    out: List[Chunk] = []
    for name, body in sections.items():
        if sections_keep and name.lower() not in {s.lower() for s in sections_keep}:
            continue
        for piece in chunk_text(body, max_chars=max_chars, overlap=overlap):
            cid = f"chunk:{doc_id}:{order}:{_hash(piece)}"
            out.append(Chunk(id=cid, doc_id=doc_id, section=name,
                             order=order, text=piece))
            order += 1
    return out


def to_items(chunks: Sequence[Chunk]) -> List[Dict[str, Any]]:
    """转成向量库条目（``kind=chunk``）。"""
    return [{"id": c.id, "text": f"[{c.section}] {c.text}",
             "meta": {"kind": "chunk", "doc_id": c.doc_id,
                      "section": c.section, "order": c.order, "chars": c.chars}}
            for c in chunks]
