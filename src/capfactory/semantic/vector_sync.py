"""语义层向量索引：把 6 类节点向量化，并让检索结果自带论文溯源。

与历史 `storage_cf/vector*/` 的区别：
  - 历史索引是 34 算法 / 120 论文 / 111 块的旧快照，跟语义层不同步；
  - 本索引直接以 `batch10_semantic_v4.json` 为准，每条向量带
    `node_id / type / paper_ids`，检索结果可立即做溯源修正。
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

VEC_DIR = Path("storage_cf/semantic/vector")
NPY = VEC_DIR / "nodes.npy"
META = VEC_DIR / "nodes_meta.json"
SEM_GRAPH = Path("storage_cf/sciforge/batch10_semantic_v4.json")
PROV_INDEX = Path("storage_cf/sciforge/provenance/provenance_index.json")


def node_text(n: Any) -> str:
    """用于 embedding 的文本：名称 + 该类核心属性。"""
    a = n.attrs or {}
    parts = [n.label or a.get("name") or ""]
    keys = {
        "Paper": ("research_question", "domain", "why_hard", "keywords"),
        "Algorithm": ("mechanism", "problems_solved", "task_type",
                      "flow_family", "limitations"),
        "AlgorithmModule": ("mechanism", "inputs", "outputs", "formula"),
        "Benchmark": ("input_form", "output_form", "research_object",
                      "n_samples", "metrics"),
        "CodeFunction": ("purpose", "comment", "func_type", "params"),
        "CodeRepository": ("repo_url", "is_original_repo"),
    }.get(n.type, ())
    for k in keys:
        v = a.get(k)
        if isinstance(v, (list, tuple)):
            v = " ".join(str(x.get("name") if isinstance(x, dict) else x)
                         for x in v[:6])
        if v and str(v).lower() != "unknown":
            parts.append(str(v)[:200])
    return " | ".join(p for p in parts if p)[:800]


def build(graph=None, *, persist: bool = True) -> Dict[str, Any]:
    import numpy as np
    from ..po import POGraph
    from ..vector.embedder import BgeEmbedder
    g = graph or POGraph.load(str(SEM_GRAPH))
    prov = {}
    if PROV_INDEX.exists():
        try:
            prov = json.loads(PROV_INDEX.read_text(encoding="utf-8")
                              ).get("node_to_papers") or {}
        except Exception:  # noqa: BLE001
            pass
    items = [{"id": n.id, "type": n.type, "label": n.label,
              # Paper 节点自身就是来源，不溯源到它引用的其它论文
              "paper_ids": ([n.id] if n.type == "Paper"
                            else prov.get(n.id, []))}
             for n in g.nodes.values()
             if n.type in ("Paper", "Algorithm", "AlgorithmModule",
                           "Benchmark", "CodeFunction", "CodeRepository")]
    texts = [node_text(g.nodes[i["id"]]) for i in items]
    emb = BgeEmbedder()
    vec = emb.embed(texts).astype("float32")
    if persist:
        VEC_DIR.mkdir(parents=True, exist_ok=True)
        np.save(str(NPY), vec)
        META.write_text(json.dumps(
            {"count": len(items), "dim": int(vec.shape[1]),
             "source": str(SEM_GRAPH), "embedder": "bge-m3",
             "items": items}, ensure_ascii=False, indent=1),
            encoding="utf-8")
    return {"count": len(items), "dim": int(vec.shape[1]),
            "path": str(NPY),
            "by_type": {t: sum(1 for x in items if x["type"] == t)
                        for t in sorted({x["type"] for x in items})}}


def _norm(v):
    import numpy as np
    n = np.linalg.norm(v, axis=1, keepdims=True)
    return v / (n + 1e-9)


def search(query: str, *, types: Optional[List[str]] = None,
           k: int = 10) -> List[Dict[str, Any]]:
    """检索语义层节点，返回项自带 paper_ids（可直接溯源）。"""
    import numpy as np
    from ..vector.embedder import BgeEmbedder, cosine
    if not NPY.exists() or not META.exists():
        return []
    meta = json.loads(META.read_text(encoding="utf-8"))
    vec = _norm(np.load(str(NPY)))
    q = _norm(BgeEmbedder().embed([query]))[0]
    scores = vec @ q
    order = np.argsort(-scores)
    out = []
    for i in order:
        item = dict(meta["items"][int(i)])
        if types and item["type"] not in types:
            continue
        item["score"] = round(float(scores[int(i)]), 4)
        out.append(item)
        if len(out) >= k:
            break
    return out


def stats() -> Dict[str, Any]:
    if not META.exists():
        return {"exists": False}
    m = json.loads(META.read_text(encoding="utf-8"))
    return {"exists": True, "count": m["count"], "dim": m["dim"],
            "embedder": m.get("embedder"), "source": m.get("source"),
            "with_paper": sum(1 for x in m["items"] if x.get("paper_ids"))}
