"""图片库：原始 PNG + 结构化图注 + 模型/用量元数据，按内容 sha 去重.

目录结构::

    storage_cf/vision/
    ├── images/<sha256>.png          # 原始页面图（去重）
    ├── items.jsonl                  # 每页一条：来源、页码、图注、结构化字段
    └── meta.json                    # 集合统计

与向量库的关系：图注文本可直接写入 ``vector`` 的 ``images`` 集合，
从而支持「用文字找图」（如 "找有 Pareto 前沿的图"）。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..utils import now_iso


class ImageLibrary:
    def __init__(self, root: str | Path = "storage_cf/vision") -> None:
        self.root = Path(root)
        self.img_dir = self.root / "images"
        self.img_dir.mkdir(parents=True, exist_ok=True)
        self.items: List[Dict[str, Any]] = []
        self.meta: Dict[str, Any] = {"created_at": now_iso()}
        self.load()

    # -- 持久化 -----------------------------------------------------------
    @property
    def items_path(self) -> Path:
        return self.root / "items.jsonl"

    @property
    def meta_path(self) -> Path:
        return self.root / "meta.json"

    def load(self) -> "ImageLibrary":
        self.items = []
        if self.items_path.exists():
            with self.items_path.open(encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        self.items.append(json.loads(line))
        if self.meta_path.exists():
            try:
                self.meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        self.meta["count"] = len(self.items)
        return self

    def save(self) -> None:
        with self.items_path.open("w", encoding="utf-8") as fh:
            for it in self.items:
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")
        self.meta.update({"count": len(self.items), "updated_at": now_iso()})
        self.meta_path.write_text(json.dumps(self.meta, ensure_ascii=False, indent=2),
                                  encoding="utf-8")

    # -- 写入 -------------------------------------------------------------
    def add(self, png: bytes, *, source: str, page: int,
            caption: Optional[Dict[str, Any]] = None,
            model: str = "", usage: Optional[Dict[str, Any]] = None,
            latency: Optional[float] = None, extra: Optional[Dict[str, Any]] = None,
            save_png: bool = True) -> Dict[str, Any]:
        sha = hashlib.sha256(png).hexdigest()
        img_id = f"image:{sha[:16]}"
        for it in self.items:
            if it["id"] == img_id:
                return it
        if save_png:
            (self.img_dir / f"{sha}.png").write_bytes(png)
        item = {
            "id": img_id, "sha256": sha, "source": source, "page": page,
            "bytes": len(png), "model": model,
            "latency": latency, "usage": usage or {},
            "caption": caption or {}, "extra": extra or {},
            "created_at": now_iso(),
        }
        # 便于检索的扁平文本
        cap = caption or {}
        text_parts = [str(cap.get("summary", "")), str(cap.get("page_type", ""))]
        for f in (cap.get("figures") or [])[:6]:
            if isinstance(f, dict):
                text_parts += [str(f.get("label", "")), str(f.get("type", "")),
                               str(f.get("conclusion", ""))]
        item["text"] = " | ".join(p for p in text_parts if p)[:1200]
        self.items.append(item)
        return item

    def get(self, img_id: str) -> Optional[Dict[str, Any]]:
        for it in self.items:
            if it["id"] == img_id:
                return it
        return None

    def png_path(self, img_id: str) -> Optional[Path]:
        it = self.get(img_id)
        if not it:
            return None
        p = self.img_dir / f"{it['sha256']}.png"
        return p if p.exists() else None

    # -- 观察 -------------------------------------------------------------
    def stats(self) -> Dict[str, Any]:
        pages = sum(1 for it in self.items if not it["caption"].get("error"))
        by_type: Dict[str, int] = {}
        for it in self.items:
            t = str(it["caption"].get("page_type", "unknown"))
            by_type[t] = by_type.get(t, 0) + 1
        total_bytes = sum(int(it.get("bytes") or 0) for it in self.items)
        return {"count": len(self.items), "captioned": pages,
                "by_page_type": by_type, "bytes": total_bytes,
                "path": str(self.root), "meta": self.meta}

    def as_vector_items(self) -> List[Dict[str, Any]]:
        """转成向量库条目（``kind=image``）。"""
        return [{"id": it["id"], "text": it.get("text") or "",
                 "meta": {"kind": "image", "source": it["source"],
                          "page": it["page"], "page_type":
                          it["caption"].get("page_type", "")}}
                for it in self.items if it.get("text")]
