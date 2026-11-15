"""批量抽取：已解析的 Markdown → 概念/断言 → 三态链接 → 入图 + 入向量库.

与 ``eval.run_group`` 的区别：这是**落地**而不是评测——
抽取结果会真正写进一张 PO 图（``storage_cf/po/batch.json``）和
多向量库（``storage_cf/vector3``），并保留 ``link_state`` 与来源 chunk。

流程：

```
data/docx/<id>.md → split_sections → chunk（abstract/method/result 优先）
   → POExtractor（LLM，PO schema）
   → link_extraction（linked / subsumed / novel）
   → merge_into（参考实体复用，观测/证据新建）
   → MultiVectorStore（content/context/summary 三列）
```

why 先选 abstract/method/result：这三节覆盖「做什么 / 怎么做 / 结果如何」，
是能力主张与数值证据最集中的地方；引言与相关工作多是背景，抽取性价比低。
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..po import POGraph
from ..po.concepts import Concept
from ..utils import now_iso
from ..vector import BgeEmbedder
from ..vector.meta import build_entity_lexicon, build_meta, meta_summary, to_embedding_text
from ..vector.multistore import MultiVectorStore
from .chunker import Chunk, chunk_sections
from .emergence import OtherBuffer
from .extractor import OllamaChat, POExtractor
from .linking import link_extraction, merge_into

SECTION_PRIORITY = ("abstract", "introduction", "method", "methods", "experiment",
                    "experiments", "result", "results", "approach",
                    "results and discussion", "conclusion", "conclusions")

# 分流：骨架节（摘要/引言/结论）整篇读，细则节（方法/结果）切块读。
# 依据：整篇能抽到 ResearchQuestion/ProblemContext/Workflow/Domain 这类跨节骨架节点，
# 块级在方法/结果上单位密度更高（4.5 vs 2.6 节点/千字符）且可重试。
SECTION_MODE = {
    "abstract": "whole", "introduction": "whole", "background": "whole",
    "conclusion": "whole", "conclusions": "whole",
    "discussion": "whole", "discussions": "whole",
    "limitation": "whole", "limitations": "whole",
    "method": "block", "methods": "block", "approach": "block",
    "experiment": "block", "experiments": "block",
    "result": "block", "results": "block", "results and discussion": "block",
}
WHOLE_MAX_CHARS = 20000      # 骨架节整篇上限（约 6.7K token，留足 32K 输出）


_SEC_PREFIX = re.compile(r"^\s*(\d+(\.\d+)*\.?|chapter\s+\d+|appendix\s+[a-z])\s*", re.I)


def _norm_section(section: str) -> str:
    low = " ".join(str(section or "").lower().split())
    low = _SEC_PREFIX.sub("", low)
    return low.split(":")[0].strip()


def _mode_of(section: str) -> str:
    """骨架节 → whole，细则节 → block。

    标题残缺（``of drug-like molecules (4)`` 这类把句子当标题）不参与匹配，
    避免把正文误判成摘要。
    """
    low = _norm_section(section)
    if not low or len(low) > 40 or low.count(" ") > 6:
        return "block"
    for key, mode in SECTION_MODE.items():
        if low == key or low.startswith(key + " "):
            return mode
    return "block"


# 以介词/连词开头的「标题」几乎都是被误判的正文片段
_BAD_PREFIX = ("of ", "for ", "in ", "to ", "with ", "and ", "by ", "the ",
               "that ", "which ", "as ", "on ", "from ", "at ")


def _looks_like_fragment(section: str) -> bool:
    low = _norm_section(section)
    return (not low) or low.startswith(_BAD_PREFIX) or low.count(" ") > 6


def _sections_degraded(sections: Dict[str, str]) -> bool:
    """章节切分是否退化：标题识别失败 / 单节吃掉大半正文 / 过半标题是正文片段。"""
    if len(sections) < 4:
        return True
    total = sum(len(v) for v in sections.values()) or 1
    if max(len(v) for v in sections.values()) / total > 0.7:
        return True
    frags = sum(1 for k in sections if _looks_like_fragment(k))
    return frags / len(sections) > 0.5


def _pick_sections(sections: Dict[str, str], *, per_doc: int = 2
                   ) -> List[Tuple[str, str, str]]:
    """按优先级挑节，返回 ``[(section, body, mode)]``；``mode`` = whole / block。

    分流依据：骨架节（摘要/引言/结论）整篇读能拿到跨节主张；
    细则节（方法/结果）切块读单位密度更高、可重试。
    """
    # 章节结构退化时不做分流：整篇按块切，避免把正文当摘要整篇塞进去
    if _sections_degraded(sections):
        merged = "\n\n".join(f"## {k}\n{v}" for k, v in sections.items())
        return [("fulltext", merged, "block")]

    picked: List[Tuple[str, str, str]] = []
    for key, body in sections.items():
        low = key.lower()
        if any(low.startswith(p) or p in low for p in SECTION_PRIORITY):
            picked.append((key, body, _mode_of(key)))
        if len(picked) >= per_doc:
            break
    if len(picked) < per_doc:
        rest = sorted(((k, v) for k, v in sections.items()
                       if k not in {x[0] for x in picked}), key=lambda kv: -len(kv[1]))
        for k, v in rest[: per_doc - len(picked)]:
            picked.append((k, v, _mode_of(k)))
    return picked


def _graph_entities(graph: POGraph) -> Dict[str, str]:
    """doc_id → 图里是否已有同名 Paper（用于归属判断）。"""
    out = {}
    for p in graph.by_type("Paper"):
        for key in (p.attrs.get("arxiv_id"), p.id.split(":")[-1],
                    str(p.attrs.get("number") or "")):
            if key:
                out[str(key)] = p.id
    return out


def extract_docs(doc_ids: Sequence[str], *,
                 md_dir: str | Path = "/home/zengshuxin/xKG-main/data/docx",
                 base_graph: str | Path = "storage_cf/po/report_graph.json",
                 out_graph: str | Path = "storage_cf/po/batch.json",
                 vector_root: str | Path = "storage_cf/vector3",
                 per_doc: int = 2, max_chars: int = 1800,
                 model: str = "",
                 backend: str = "qwen38",
                 chat_fn: Optional[Any] = None,
                 workers: int = 1) -> Dict[str, Any]:
    md_dir = Path(md_dir)
    base = POGraph.load(Path(base_graph)) if Path(base_graph).exists() else POGraph("base")
    lexicon = build_entity_lexicon(base)
    emb = BgeEmbedder(batch_size=8)
    if chat_fn is not None:
        fn = chat_fn
    elif backend == "qwen38":
        from ..vector.labeler import VLLMBackend
        v = VLLMBackend()
        v.available()
        fn = lambda prompt: v.chat(prompt, max_tokens=32768)   # noqa: E731
        model = v.model
    else:
        model = model or "qwen3.5:latest"
        fn = OllamaChat(model=model, num_predict=2200)
    extractor = POExtractor(chat_fn=fn, max_nodes=10)
    buffer = OtherBuffer(Path(vector_root) / "other_nodes.jsonl", embedder=emb)

    from ..ingest.pdf import split_sections

    records: List[Dict[str, Any]] = []
    per_doc_stats: List[Dict[str, Any]] = []
    t0 = time.time()
    for doc_id in doc_ids:
        md = md_dir / f"{doc_id}.md"
        if not md.exists():
            per_doc_stats.append({"doc_id": doc_id, "ok": False, "error": "md_missing"})
            continue
        text = md.read_text(encoding="utf-8", errors="replace")
        sections = split_sections(text)
        picked = _pick_sections(sections, per_doc=per_doc)
        chunks: List[Chunk] = []
        for name, body, mode in picked:
            if mode == "whole":
                # 整篇：不切块，直接把该节全文交给 LLM（上限 WHOLE_MAX_CHARS）
                chunks.append(Chunk(id=f"whole:{doc_id}:{name}", doc_id=doc_id,
                                    section=name, order=len(chunks),
                                    text=body[:WHOLE_MAX_CHARS]))
            else:
                chunks.extend(chunk_sections({name: body}, doc_id,
                                             max_chars=max_chars)[:1])
        results = []
        for c in chunks:
            try:
                results.append(extractor.extract(
                    c, paper_id=doc_id, version_id=f"version:{doc_id}", locator=c.section,
                    whole=(c.id.startswith("whole:"))))
            except Exception as exc:  # noqa: BLE001
                per_doc_stats.append({"doc_id": doc_id, "chunk": c.id,
                                      "error": str(exc)[:160]})
        ext = extractor.to_graph(results)
        link = link_extraction(ext, base, embedder=emb)
        buffer.observe_many(link["links"],
                            papers={n.id: n.attrs.get("source_paper", doc_id)
                                    for n in ext.nodes.values()})
        merge = merge_into(base, ext, embedder=emb)

        # 向量库记录（三列：原文 / 元数据注入 / 摘要）
        for c in chunks:
            meta = build_meta(c, base, lexicon=lexicon)
            meta.update({"doc_id": doc_id, "source": "batch_extract",
                         "link_states": {s["source_label"]: s["state"]
                                         for s in link["links"][:20]}})
            records.append({"id": c.id, "text": c.text, "meta": meta})
        per_doc_stats.append({
            "doc_id": doc_id, "ok": True, "sections": len(sections),
            "picked": list(picked), "chunks": len(chunks),
            "nodes": sum(r.kept for r in results),
            "assertions": sum(len(r.assertions) for r in results),
            "link": link["by_state"], "resolve_rate": link["resolve_rate"],
            "reused": merge["reused"], "added_nodes": merge["added_nodes"],
            "added_edges": merge["added_edges"],
        })
        print(f"[{doc_id}] nodes={per_doc_stats[-1]['nodes']} "
              f"states={link['by_state']} reused={merge['reused']}", flush=True)

    buffer.save()
    base.meta["batch_extract"] = {"doc_ids": list(doc_ids), "at": now_iso(),
                                  "model": model, "per_doc": per_doc_stats}
    base.save(Path(out_graph))
    store = MultiVectorStore(vector_root, "docs", embedder=emb)
    build_stats = store.build(records) if records else {"count": 0}
    return {
        "docs": len(doc_ids), "ok": sum(1 for d in per_doc_stats if d.get("ok")),
        "seconds": round(time.time() - t0, 1),
        "graph": {"path": str(out_graph), "nodes": len(base.nodes),
                  "assertions": len(base.assertions),
                  "validation": len(base.validate())},
        "vector": {"path": str(vector_root), **build_stats},
        "meta_coverage": meta_summary([r["meta"] for r in records]),
        "other_buffer": buffer.stats(),
        "per_doc": per_doc_stats,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="批量抽取 Markdown → PO 图 + 向量库")
    ap.add_argument("docs", nargs="+", help="arXiv id 列表")
    ap.add_argument("--md-dir", default="/home/zengshuxin/xKG-main/data/docx")
    ap.add_argument("--base-graph", default="storage_cf/po/report_graph.json")
    ap.add_argument("--out-graph", default="storage_cf/po/batch.json")
    ap.add_argument("--vector-root", default="storage_cf/vector3")
    ap.add_argument("--per-doc", type=int, default=2)
    ap.add_argument("--model", default="")
    ap.add_argument("--backend", default="qwen38", choices=["qwen38", "ollama"])
    a = ap.parse_args(argv)
    out = extract_docs(a.docs, md_dir=a.md_dir, base_graph=a.base_graph,
                       out_graph=a.out_graph, vector_root=a.vector_root,
                       per_doc=a.per_doc, model=a.model, backend=a.backend)
    print(json.dumps({k: v for k, v in out.items() if k != "per_doc"},
                     ensure_ascii=False, indent=2)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
