"""离线检索组件：BM25 + 哈希向量混合检索.

为什么不用 sentence-transformers / faiss？
----------------------------------------
运行环境无法访问 HuggingFace，且要求「开箱即跑」。因此实现一个**确定性、
零下载**的混合检索：

- BM25：负责术语精确匹配（算法名、指标名）；
- Hash-Embedding：对 word unigram + char 3-gram 做带符号哈希投影，
  近似捕捉词形/子词相似（"toxicity" ↔ "toxic"）；
- 二者加权融合，并对图邻居施加跳数衰减，形成「图增强检索」。
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]+|[\u4e00-\u9fff]{1,4}")


def tokenize(text: str) -> List[str]:
    """英文按词、中文按 1-2 字切分，并加入小写形式。"""
    text = (text or "").lower()
    tokens = TOKEN_RE.findall(text)
    out: List[str] = []
    for t in tokens:
        out.append(t)
        if len(t) > 4 and re.fullmatch(r"[a-z]+", t):
            # 简单词干：截断后缀，缓解 toxicity/toxic 类不匹配
            for suf in ("icity", "ation", "ities", "ing", "ed", "s"):
                if t.endswith(suf) and len(t) - len(suf) >= 4:
                    out.append(t[: -len(suf)])
    return out


class HashingEmbedder:
    """带符号特征哈希向量（确定性、离线、无需训练）。"""

    def __init__(self, dim: int = 512):
        self.dim = dim

    def _grams(self, text: str) -> Iterable[str]:
        for tok in tokenize(text):
            yield f"w:{tok}"
            if len(tok) >= 5:
                for i in range(len(tok) - 2):
                    yield f"c:{tok[i:i+3]}"

    def encode(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        counts = Counter(self._grams(text))
        for gram, cnt in counts.items():
            h = hash(gram) if False else _stable_hash(gram)
            idx = h % self.dim
            sign = 1.0 if (h >> 32) % 2 == 0 else -1.0
            vec[idx] += sign * (1.0 + math.log(cnt))
        norm = float(np.linalg.norm(vec))
        return vec / norm if norm else vec

    def encode_batch(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.vstack([self.encode(t) for t in texts])


def _stable_hash(text: str) -> int:
    """跨进程稳定的哈希（Python 内置 hash 受 PYTHONHASHSEED 影响）。"""
    import hashlib

    return int.from_bytes(hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest(), "big")


class BM25:
    """标准 BM25（k1=1.5, b=0.75）。"""

    def __init__(self, corpus: Sequence[str], k1: float = 1.5, b: float = 0.75):
        self.docs = [tokenize(d) for d in corpus]
        self.k1, self.b = k1, b
        self.doc_len = [len(d) for d in self.docs]
        self.avgdl = (sum(self.doc_len) / len(self.doc_len)) if self.doc_len else 0.0
        self.tf: List[Counter] = [Counter(d) for d in self.docs]
        df: Dict[str, int] = defaultdict(int)
        for tf in self.tf:
            for term in tf:
                df[term] += 1
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> np.ndarray:
        q = tokenize(query)
        out = np.zeros(len(self.docs), dtype=np.float32)
        if not self.docs or not q:
            return out
        for i, tf in enumerate(self.tf):
            denom_norm = self.k1 * (1 - self.b + self.b * self.doc_len[i] / (self.avgdl or 1))
            s = 0.0
            for term in q:
                f = tf.get(term)
                if not f:
                    continue
                s += self.idf.get(term, 0.0) * (f * (self.k1 + 1)) / (f + denom_norm)
            out[i] = s
        return out


@dataclass
class SearchHit:
    """一条检索结果。"""

    node_id: str
    score: float
    bm25: float = 0.0
    vector: float = 0.0
    graph_bonus: float = 0.0
    payload: Dict = field(default_factory=dict)


class HybridIndex:
    """BM25 + 向量 混合索引，支持图邻居增强。"""

    def __init__(self, dim: int = 512, bm25_weight: float = 0.5):
        self.embedder = HashingEmbedder(dim)
        self.bm25_weight = bm25_weight
        self.ids: List[str] = []
        self.texts: List[str] = []
        self.payloads: List[Dict] = []
        self.bm25: Optional[BM25] = None
        self.matrix: Optional[np.ndarray] = None
        self._pos: Dict[str, int] = {}

    def build(self, items: List[Tuple[str, str, Dict]]) -> None:
        """items: ``[(id, text, payload), ...]``"""
        self.ids = [i for i, _, _ in items]
        self.texts = [t for _, t, _ in items]
        self.payloads = [p for _, _, p in items]
        self._pos = {i: k for k, i in enumerate(self.ids)}
        self.bm25 = BM25(self.texts) if self.texts else None
        self.matrix = self.embedder.encode_batch(self.texts)

    def search(self, query: str, top_k: int = 8, min_score: float = 0.0) -> List[SearchHit]:
        if not self.ids:
            return []
        bm25_scores = self.bm25.scores(query) if self.bm25 else np.zeros(len(self.ids))
        if bm25_scores.max() > 0:
            bm25_norm = bm25_scores / bm25_scores.max()
        else:
            bm25_norm = bm25_scores
        qv = self.embedder.encode(query)
        vec_scores = self.matrix @ qv if self.matrix is not None and self.matrix.size else np.zeros(len(self.ids))
        # 余弦相似度裁剪到 [0,1]：正交（不相关）应为 0，而非 0.5
        vec_scores = np.clip(vec_scores, 0.0, 1.0)
        fused = self.bm25_weight * bm25_norm + (1 - self.bm25_weight) * vec_scores
        order = np.argsort(-fused)[:max(top_k, 1)]
        hits: List[SearchHit] = []
        for idx in order:
            if fused[idx] < min_score:
                continue
            hits.append(SearchHit(
                node_id=self.ids[idx], score=round(float(fused[idx]), 4),
                bm25=round(float(bm25_norm[idx]), 4), vector=round(float(vec_scores[idx]), 4),
                payload=self.payloads[idx],
            ))
        return hits

    def position(self, node_id: str) -> Optional[int]:
        return self._pos.get(node_id)

    def pairwise_similarity(self, text_a: str, text_b: str) -> float:
        va, vb = self.embedder.encode(text_a), self.embedder.encode(text_b)
        na, nb = np.linalg.norm(va), np.linalg.norm(vb)
        if not na or not nb:
            return 0.0
        return float((va @ vb) / (na * nb))
