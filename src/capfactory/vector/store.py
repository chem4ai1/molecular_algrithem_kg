"""本地向量库：JSONL 元数据 + ``.npy`` 矩阵 + 余弦检索（无外部服务）.

设计取舍：

* **为什么不用 FAISS/Milvus**：当前规模（≤ 10 万条 × 1024 维 float32 ≈ 400MB）
  用内存矩阵 + 归一化点积即可，``8 万条`` 检索约 10–20ms；避免引入重依赖与运维；
* **增量友好**：``items.jsonl`` 追加、``vectors.npy`` 重写，天然支持断点续跑；
* **多集合**：``papers`` / ``chunks`` / ``images`` / ``po_nodes`` 各一个子目录，
  共享同一 embedder 与检索接口。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from ..utils import now_iso
from .embedder import BgeEmbedder, EmbedError


class VectorStore:
    """一个向量集合（collection）。"""

    def __init__(self, root: str | Path = "storage_cf/vector",
                 name: str = "papers",
                 embedder: Optional[BgeEmbedder] = None) -> None:
        self.dir = Path(root) / name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.name = name
        self.embedder = embedder or BgeEmbedder()
        self.items: List[Dict[str, Any]] = []
        self.vectors: Optional[np.ndarray] = None
        self.meta: Dict[str, Any] = {"name": name, "created_at": now_iso(),
                                     "dim": None, "count": 0}
        self.load()

    # -- 持久化 -----------------------------------------------------------
    @property
    def items_path(self) -> Path:
        return self.dir / "items.jsonl"

    @property
    def vectors_path(self) -> Path:
        return self.dir / "vectors.npy"

    @property
    def meta_path(self) -> Path:
        return self.dir / "meta.json"

    def load(self) -> "VectorStore":
        self.items = []
        if self.items_path.exists():
            with self.items_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        self.items.append(json.loads(line))
        if self.vectors_path.exists():
            arr = np.load(self.vectors_path)
            self.vectors = arr if arr.size else None
        if self.meta_path.exists():
            try:
                self.meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        self.meta.update({"count": len(self.items),
                          "dim": (int(self.vectors.shape[1])
                                  if self.vectors is not None and self.vectors.ndim == 2 else None)})
        return self

    def save(self) -> None:
        with self.items_path.open("w", encoding="utf-8") as fh:
            for it in self.items:
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")
        if self.vectors is not None and self.vectors.size:
            np.save(self.vectors_path, self.vectors.astype(np.float32))
        self.meta.update({"count": len(self.items),
                          "dim": (int(self.vectors.shape[1])
                                  if self.vectors is not None and self.vectors.ndim == 2 else None),
                          "updated_at": now_iso()})
        self.meta_path.write_text(json.dumps(self.meta, ensure_ascii=False, indent=2),
                                  encoding="utf-8")

    # -- 写入 -------------------------------------------------------------
    def add(self, items: Sequence[Dict[str, Any]],
            vectors: Optional[np.ndarray] = None, *, embed: bool = True) -> int:
        """追加条目。``items[i]`` 需含 ``id`` 与 ``text``；重复 id 会跳过。"""
        if not items:
            return 0
        existing = {it.get("id") for it in self.items}
        fresh = [it for it in items if it.get("id") not in existing]
        if not fresh:
            return 0
        if vectors is None:
            if not embed:
                raise ValueError("未提供 vectors 且 embed=False")
            vectors = self.embedder.embed([it["text"] for it in fresh])
        vectors = np.asarray(vectors, dtype=np.float32)
        if vectors.shape[0] != len(fresh):
            raise ValueError(f"向量条数 {vectors.shape[0]} 与条目 {len(fresh)} 不匹配")
        if self.vectors is None or not self.vectors.size:
            self.vectors = vectors
        else:
            if self.vectors.shape[1] != vectors.shape[1]:
                raise ValueError(f"维度不一致：{self.vectors.shape[1]} vs {vectors.shape[1]}")
            self.vectors = np.vstack([self.vectors, vectors])
        for it in fresh:
            self.items.append({"id": it["id"], "text": it["text"],
                               "meta": it.get("meta") or {}})
        return len(fresh)

    # -- 检索 -------------------------------------------------------------
    def _norm_matrix(self) -> np.ndarray:
        if self.vectors is None or not self.vectors.size:
            return np.zeros((0, 1), dtype=np.float32)
        norms = np.linalg.norm(self.vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return self.vectors / norms

    def search(self, query: str, *, top_k: int = 8, min_score: float = 0.0,
               filter_fn: Optional[Callable[[Dict[str, Any]], bool]] = None
               ) -> List[Dict[str, Any]]:
        if not self.items or self.vectors is None:
            return []
        q = self.embedder.embed_one(query)
        qn = q / (np.linalg.norm(q) or 1.0)
        sims = self._norm_matrix() @ qn
        order = np.argsort(-sims)
        out: List[Dict[str, Any]] = []
        for i in order:
            if len(out) >= top_k:
                break
            score = float(sims[i])
            if score < min_score:
                break
            it = self.items[int(i)]
            if filter_fn and not filter_fn(it):
                continue
            out.append({"id": it["id"], "score": round(score, 4),
                        "text": it["text"][:600], "meta": it.get("meta") or {}})
        return out

    def search_by_vector(self, vec: np.ndarray, *, top_k: int = 8
                         ) -> List[Dict[str, Any]]:
        if not self.items or self.vectors is None:
            return []
        v = np.asarray(vec, dtype=np.float32)
        v = v / (np.linalg.norm(v) or 1.0)
        sims = self._norm_matrix() @ v
        order = np.argsort(-sims)[:top_k]
        return [{"id": self.items[int(i)]["id"], "score": round(float(sims[i]), 4),
                 "text": self.items[int(i)]["text"][:600],
                 "meta": self.items[int(i)].get("meta") or {}} for i in order]

    # -- 观察 -------------------------------------------------------------
    def stats(self) -> Dict[str, Any]:
        return {"name": self.name, "count": len(self.items),
                "dim": (int(self.vectors.shape[1]) if self.vectors is not None
                        and self.vectors.ndim == 2 else None),
                "bytes": (int(self.vectors.nbytes) if self.vectors is not None else 0),
                "path": str(self.dir),
                "embedder": getattr(self.embedder, "model", ""),
                "embedder_stats": getattr(self.embedder, "stats", {})}

    def kinds(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for it in self.items:
            k = str((it.get("meta") or {}).get("kind", "unknown"))
            out[k] = out.get(k, 0) + 1
        return out
