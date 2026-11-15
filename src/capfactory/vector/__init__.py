"""向量层：Ollama bge-m3 向量化 + 本地余弦检索库 + 索引器."""

from .embedder import BgeEmbedder, EmbedError, cosine
from .store import VectorStore
from .indexer import (
    demo_queries, index_paper_abstracts, index_po_graph, index_texts,
)

__all__ = [
    "BgeEmbedder", "EmbedError", "cosine", "VectorStore",
    "index_paper_abstracts", "index_po_graph", "index_texts", "demo_queries",
]
