"""Ollama bge-m3 向量化客户端（1024 维，批量 + 缓存 + 退避）.

为什么不用项目自带的 ``HashingEmbedder``：那是 512 维哈希特征，只能做词面近似，
无法支撑「语义相近但用词不同」的检索（如 "肽毒性" vs "haemolysis assay"）。
本模块接本地 Ollama ``bge-m3``，实测 1024 维、余弦区分度良好。

接口与 ``kg.retrieval`` 解耦：只负责 text → vector，存储与检索在 ``store.py``。
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np

DEFAULT_MODEL = "bge-m3"
DEFAULT_BASE = "http://127.0.0.1:11434"


class EmbedError(RuntimeError):
    pass


class BgeEmbedder:
    """Ollama ``/api/embed`` 封装。

    - ``batch_size`` 控制单请求条数（Ollama 对超长 list 会超时）；
    - ``cache_dir`` 按文本 sha1 缓存向量，避免重复 embedding；
    - 失败重试 3 次，指数退避；仍失败抛 ``EmbedError``（调用方可降级跳过）。
    """

    def __init__(self, model: str = DEFAULT_MODEL, base_url: str = DEFAULT_BASE,
                 *, batch_size: int = 16, timeout: int = 120,
                 cache_dir: Optional[str | Path] = "storage_cf/vector_cache",
                 retries: int = 3) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.batch_size = max(1, batch_size)
        self.timeout = timeout
        self.retries = retries
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._dim: Optional[int] = None
        self.stats = {"calls": 0, "texts": 0, "cache_hits": 0, "errors": 0,
                      "total_seconds": 0.0}

    # -- 缓存 -------------------------------------------------------------
    def _cache_path(self, text: str) -> Optional[Path]:
        if not self.cache_dir:
            return None
        h = hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()
        return self.cache_dir / f"{self.model.replace('/', '_')}__{h}.npy"

    # -- HTTP -------------------------------------------------------------
    def _post(self, texts: Sequence[str]) -> List[List[float]]:
        payload = {"model": self.model, "input": list(texts)}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/embed", data=data,
            headers={"Content-Type": "application/json"})
        last: Optional[Exception] = None
        for attempt in range(self.retries):
            try:
                t0 = time.time()
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                self.stats["calls"] += 1
                self.stats["total_seconds"] += time.time() - t0
                embs = body.get("embeddings")
                if not embs or len(embs) != len(texts):
                    raise EmbedError(f"返回条数不匹配：{len(embs or [])} vs {len(texts)}")
                if self._dim is None:
                    self._dim = len(embs[0])
                elif len(embs[0]) != self._dim:
                    raise EmbedError(f"维度不一致：{len(embs[0])} vs {self._dim}")
                return embs
            except Exception as exc:  # noqa: BLE001
                last = exc
                self.stats["errors"] += 1
                time.sleep(min(2 ** attempt, 8))
        raise EmbedError(f"Ollama embedding 失败（{self.model}）：{last}")

    # -- 公共 API ---------------------------------------------------------
    @property
    def dim(self) -> Optional[int]:
        return self._dim

    def embed(self, texts: Sequence[str], *, use_cache: bool = True) -> np.ndarray:
        """批量向量化，返回 ``(n, dim) float32``。空文本返回零向量。"""
        texts = [t if isinstance(t, str) else str(t) for t in texts]
        if not texts:
            return np.zeros((0, self._dim or 1024), dtype=np.float32)
        out: List[np.ndarray] = [None] * len(texts)  # type: ignore[list-item]
        pending: List[int] = []
        for i, t in enumerate(texts):
            cp = self._cache_path(t) if use_cache else None
            if cp and cp.exists():
                out[i] = np.load(cp)
                self.stats["cache_hits"] += 1
            elif not t.strip():
                out[i] = np.zeros(self._dim or 1024, dtype=np.float32)
            else:
                pending.append(i)
        for start in range(0, len(pending), self.batch_size):
            idx = pending[start:start + self.batch_size]
            embs = self._post([texts[i] for i in idx])
            arr = np.asarray(embs, dtype=np.float32)
            for j, i in enumerate(idx):
                out[i] = arr[j]
                cp = self._cache_path(texts[i]) if use_cache else None
                if cp:
                    np.save(cp, arr[j])
            self.stats["texts"] += len(idx)
        dim = self._dim or (len(out[0]) if out and out[0] is not None else 1024)
        mat = np.zeros((len(texts), dim), dtype=np.float32)
        for i, v in enumerate(out):
            if v is not None:
                mat[i] = v
        return mat

    def embed_one(self, text: str, *, use_cache: bool = True) -> np.ndarray:
        return self.embed([text], use_cache=use_cache)[0]

    def health(self) -> Dict[str, Any]:
        """探测 Ollama 是否可用（不加载模型，只查 /api/tags）。"""
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=5) as r:
                tags = json.loads(r.read().decode("utf-8"))
            names = [m.get("name") for m in tags.get("models", [])]
            return {"ok": self.model in names or any(
                n and n.startswith(self.model.split(":")[0]) for n in names),
                "model": self.model, "available_models": names[:12]}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "model": self.model, "error": str(exc)[:200]}


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))
