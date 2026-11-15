"""多向量库：一条记录多列向量 + 元数据过滤 + 加权融合检索.

与单向量 ``VectorStore`` 的区别：

| 单向量 | 多向量（本模块） |
|---|---|
| 一个 ``text`` 一个向量 | ``content`` / ``context`` / ``summary`` 多列 |
| 只能过滤 id | 可按 ``section_role`` / ``domain_codes`` / ``chunk_role`` 等过滤 |
| 固定相似度 | 按查询意图调权重（结果类查询偏 context，背景类偏 summary） |

为什么需要多列：

* ``content``：原文细节，适合「这段话具体怎么说」；
* ``context``：原文 + 元数据标签（节/角色/实体/数值），适合「某某指标的数值是多少」；
* ``summary``：LLM 一句话摘要，适合「这篇论文在做什么」这类粗粒度问题。

权重经验值：``content 0.5 / context 0.3 / summary 0.2``；
按 ``query_class`` 可再调（见 ``WEIGHTS_BY_CLASS``）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

import numpy as np

from ..utils import now_iso
from .embedder import BgeEmbedder
from .meta import to_embedding_text

DEFAULT_WEIGHTS = {"content": 0.5, "context": 0.3, "summary": 0.2}
WEIGHTS_BY_CLASS = {
    "method_mechanism": {"content": 0.6, "context": 0.2, "summary": 0.2},
    "benchmark_result": {"content": 0.3, "context": 0.5, "summary": 0.2},
    "data_protocol": {"content": 0.4, "context": 0.4, "summary": 0.2},
    "limitation_failure": {"content": 0.5, "context": 0.2, "summary": 0.3},
    "background_motivation": {"content": 0.2, "context": 0.2, "summary": 0.6},
    "code_resource": {"content": 0.4, "context": 0.2, "summary": 0.4},
}


def _match(meta: Dict[str, Any], filters: Optional[Dict[str, Any]]) -> bool:
    if not filters:
        return True
    for k, want in filters.items():
        if want in (None, "", [], ()):
            continue
        got = meta.get(k)
        if isinstance(want, (list, tuple, set)):
            if isinstance(got, (list, tuple, set)):
                if not set(map(str, got)) & set(map(str, want)):
                    return False
            elif str(got) not in {str(x) for x in want}:
                return False
        else:
            if isinstance(got, (list, tuple, set)):
                if str(want) not in {str(x) for x in got}:
                    return False
            elif str(got) != str(want):
                return False
    return True


class MultiVectorStore:
    def __init__(self, root: str | Path = "storage_cf/vector2",
                 name: str = "chunks",
                 embedder: Optional[BgeEmbedder] = None) -> None:
        self.dir = Path(root) / name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.name = name
        self.embedder = embedder or BgeEmbedder()
        self.items: List[Dict[str, Any]] = []
        self.vectors: Dict[str, np.ndarray] = {}
        self.meta: Dict[str, Any] = {"name": name, "created_at": now_iso()}
        self.load()

    # -- 持久化 -----------------------------------------------------------
    @property
    def items_path(self) -> Path:
        return self.dir / "items.jsonl"

    def load(self) -> "MultiVectorStore":
        self.items = []
        if self.items_path.exists():
            with self.items_path.open(encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        self.items.append(json.loads(line))
        for p in self.dir.glob("vectors_*.npy"):
            key = p.stem.replace("vectors_", "")
            arr = np.load(p)
            if arr.size:
                self.vectors[key] = arr.astype(np.float32)
        if (self.dir / "meta.json").exists():
            try:
                self.meta = json.loads((self.dir / "meta.json").read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        self.meta["count"] = len(self.items)
        return self

    def save(self) -> None:
        with self.items_path.open("w", encoding="utf-8") as fh:
            for it in self.items:
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")
        for k, v in self.vectors.items():
            np.save(self.dir / f"vectors_{k}.npy", v)
        self.meta.update({"count": len(self.items), "updated_at": now_iso(),
                          "dims": {k: int(v.shape[1]) for k, v in self.vectors.items()}})
        (self.dir / "meta.json").write_text(
            json.dumps(self.meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # -- 写入 -------------------------------------------------------------
    def build(self, records: Sequence[Dict[str, Any]], *, batch_size: int = 8,
              columns: Sequence[str] = ("content", "context", "summary")) -> Dict[str, Any]:
        """``records[i] = {id, text, meta}``；一次性重建三类向量。"""
        if not records:
            return {"count": 0}
        self.items = [{"id": r["id"], "text": r["text"], "meta": r["meta"]}
                      for r in records]
        cols: Dict[str, List[str]] = {"content": [], "context": [], "summary": []}
        for r in records:
            m = r["meta"]
            cols["content"].append(r["text"])
            cols["context"].append(to_embedding_text(r["text"], m))
            cols["summary"].append(str(m.get("summary") or r["text"][:300]))
        self.vectors = {}
        stats: Dict[str, Any] = {"count": len(records), "columns": {}}
        for k in columns:
            mat = self.embedder.embed(cols[k], use_cache=True)
            self.vectors[k] = mat
            stats["columns"][k] = {"dim": int(mat.shape[1]),
                                   "chars": int(sum(len(x) for x in cols[k]))}
        self.meta.update({"built_at": now_iso(), "columns": list(columns),
                          "embedder": getattr(self.embedder, "model", "")})
        self.save()
        return stats

    # -- 检索 -------------------------------------------------------------
    def _norm(self, k: str) -> np.ndarray:
        mat = self.vectors.get(k)
        if mat is None or not mat.size:
            return np.zeros((0, 1), dtype=np.float32)
        n = np.linalg.norm(mat, axis=1, keepdims=True)
        n[n == 0] = 1.0
        return mat / n

    def search(self, query: str, *, top_k: int = 5,
               weights: Optional[Dict[str, float]] = None,
               query_class: str = "",
               filters: Optional[Dict[str, Any]] = None,
               min_score: float = 0.0) -> List[Dict[str, Any]]:
        if not self.items or not self.vectors:
            return []
        w = dict(weights or WEIGHTS_BY_CLASS.get(query_class) or DEFAULT_WEIGHTS)
        w = {k: v for k, v in w.items() if k in self.vectors}
        if not w:
            return []
        q = self.embedder.embed_one(query)
        qn = q / (np.linalg.norm(q) or 1.0)
        total = np.zeros(len(self.items), dtype=np.float32)
        for k, weight in w.items():
            sims = self._norm(k) @ qn
            total += float(weight) * sims
        idx = [i for i, it in enumerate(self.items) if _match(it.get("meta") or {}, filters)]
        if not idx:
            return []
        order = sorted(idx, key=lambda i: -total[i])[:top_k]
        out: List[Dict[str, Any]] = []
        for i in order:
            score = float(total[i])
            if score < min_score:
                break
            it = self.items[i]
            m = it.get("meta") or {}
            out.append({"id": it["id"], "score": round(score, 4),
                        "text": it["text"][:400],
                        "section": m.get("section_role"),
                        "role": m.get("chunk_role"),
                        "doc_id": m.get("doc_id"),
                        "domains": m.get("domain_codes", []),
                        "algos": m.get("algo_codes", []),
                        "summary": m.get("summary", "")})
        return out

    # -- 观察 -------------------------------------------------------------
    def stats(self) -> Dict[str, Any]:
        return {"name": self.name, "count": len(self.items),
                "columns": {k: list(v.shape) for k, v in self.vectors.items()},
                "bytes": int(sum(v.nbytes for v in self.vectors.values())),
                "path": str(self.dir),
                "meta": self.meta}
