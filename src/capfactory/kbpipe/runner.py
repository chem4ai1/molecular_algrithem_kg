"""知识抽取与实例落地编排：PDF → 文本块 / 图片 / 向量 / PO 图.

四个阶段可独立跑、可断点续跑（``state.json`` 记录每篇文档完成的 stage）：

```
text    PDF --parse_pdf--> sections --chunk--> chunks.jsonl
vision  PDF --pick/render--> PNG --VL--> 结构化图注 --> ImageLibrary + captions.jsonl
vector  chunks + captions --> VectorStore(chunks) / VectorStore(images)
extract chunks --LLM(PO schema)--> 校验 --> POGraph
```

设计约束：
- 每阶段幂等：同一 ``doc_id`` 重跑只覆盖自己的记录；
- 单篇失败不阻断整批：错误写入 ``state.json`` 的 ``errors``；
- ``limit`` 用于先跑小样本验证效果，再放大到全量。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..utils import now_iso
from ..vector import VectorStore, index_texts
from ..vision import ImageLibrary, OpenRouterVL, caption_prompt, pick_figure_pages, render_page
from .chunker import Chunk, chunk_sections, to_items
from .extractor import ExtractionResult, OllamaChat, POExtractor

DEFAULT_DATA = "/home/zengshuxin/xKG-main/data"


class PipelineRunner:
    def __init__(self, data_dir: str | Path = DEFAULT_DATA,
                 out_dir: str | Path = "storage_cf/pipeline",
                 *, limit: int = 0, resume: bool = True) -> None:
        self.data = Path(data_dir)
        self.out = Path(out_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        self.pdf_dir = self.data / "papers/pdf"
        self.limit = limit
        self.resume = resume
        self.state_path = self.out / "state.json"
        self.state: Dict[str, Any] = {"created_at": now_iso(), "docs": {},
                                      "errors": []}
        if resume and self.state_path.exists():
            try:
                self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        self.state.setdefault("docs", {})
        self.state.setdefault("errors", [])

    # -- 工具 -------------------------------------------------------------
    def pdfs(self, limit: Optional[int] = None) -> List[Path]:
        files = sorted(self.pdf_dir.glob("*.pdf"))
        n = limit if limit is not None else self.limit
        return files[:n] if n else files

    def _doc(self, pdf: Path) -> Dict[str, Any]:
        return self.state["docs"].setdefault(pdf.stem, {"stages": {}})

    def _done(self, pdf: Path, stage: str) -> bool:
        return bool(self._doc(pdf)["stages"].get(stage, {}).get("done"))

    def _mark(self, pdf: Path, stage: str, info: Dict[str, Any]) -> None:
        self._doc(pdf)["stages"][stage] = {"done": True, "at": now_iso(), **info}
        self.save()

    def save(self) -> None:
        self.state["updated_at"] = now_iso()
        self.state_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2),
                                   encoding="utf-8")

    def _append_jsonl(self, name: str, rows: Iterable[Dict[str, Any]]) -> int:
        p = self.out / name
        n = 0
        with p.open("a", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                n += 1
        return n

    # -- 阶段 1：文本 -----------------------------------------------------
    def stage_text(self, *, limit: Optional[int] = None,
                   max_chars: int = 1600) -> Dict[str, Any]:
        from ..ingest.mineru import parse_pdf_smart
        done, chunks_total, t0 = 0, 0, time.time()
        for pdf in self.pdfs(limit):
            if self.resume and self._done(pdf, "text"):
                continue
            try:
                doc = parse_pdf_smart(pdf)
                sections = {k: v for k, v in (doc.get("sections") or {}).items() if v}
                if not sections and doc.get("abstract"):
                    sections = {"abstract": str(doc["abstract"])}
                chunks = chunk_sections(sections, pdf.stem, max_chars=max_chars)
                self._append_jsonl("chunks.jsonl", [c.to_dict() for c in chunks])
                self._mark(pdf, "text", {"sections": len(sections),
                                         "chunks": len(chunks),
                                         "chars": doc.get("full_chars", 0),
                                         "parser": doc.get("parser", "pymupdf"),
                                         "layout": doc.get("layout", {}),
                                         "mineru_seconds": doc.get("mineru_seconds")})
                done += 1
                chunks_total += len(chunks)
            except Exception as exc:  # noqa: BLE001
                self.state["errors"].append({"doc": pdf.stem, "stage": "text",
                                             "error": str(exc)[:200]})
                self.save()
        return {"docs": done, "chunks": chunks_total,
                "seconds": round(time.time() - t0, 1),
                "out": str(self.out / "chunks.jsonl")}

    # -- 阶段 2：图片 -----------------------------------------------------
    def stage_vision(self, *, limit: Optional[int] = None, pages_per_doc: int = 2,
                     model: Optional[str] = None, max_tokens: int = 6000
                     ) -> Dict[str, Any]:
        lib = ImageLibrary(self.out / "vision")
        vl = OpenRouterVL(model=model) if model else OpenRouterVL()
        if not vl.available:
            return {"error": "OPENROUTER_API_KEY 未配置", "images": 0}
        done, imgs, fails, t0 = 0, 0, 0, time.time()
        for pdf in self.pdfs(limit):
            if self.resume and self._done(pdf, "vision"):
                continue
            try:
                picked = pick_figure_pages(pdf, max_pages=pages_per_doc)
                if not picked:
                    picked = [{"page": 0, "figures": [], "images": 0}]
                for pick in picked:
                    page = int(pick["page"])
                    png = render_page(pdf, page, width=1280)
                    res = vl.describe(png, caption_prompt(), max_tokens=max_tokens)
                    if not res.get("ok"):
                        fails += 1
                        lib.add(png, source=pdf.stem, page=page,
                                caption={"error": res.get("error", "unknown")},
                                model=vl.model)
                        continue
                    cap = res.get("json") or {"summary": (res.get("text") or "")[:400]}
                    lib.add(png, source=pdf.stem, page=page, caption=cap,
                            model=res.get("model", vl.model),
                            usage=res.get("usage"), latency=res.get("latency"),
                            extra={"figures_found": pick.get("figures", [])})
                    imgs += 1
                lib.save()
                self._mark(pdf, "vision", {"pages": len(picked), "images": len(picked)})
                done += 1
            except Exception as exc:  # noqa: BLE001
                self.state["errors"].append({"doc": pdf.stem, "stage": "vision",
                                             "error": str(exc)[:200]})
                self.save()
        lib.save()
        return {"docs": done, "images": imgs, "failed": fails,
                "seconds": round(time.time() - t0, 1),
                "stats": lib.stats(), "vl_stats": vl.stats}

    # -- 阶段 3：向量 -----------------------------------------------------
    def stage_vector(self, *, batch_size: int = 8) -> Dict[str, Any]:
        t0 = time.time()
        chunk_rows = self._read_jsonl("chunks.jsonl")
        items = [{"id": r["id"], "text": f"[{r.get('section','')}] {r['text']}",
                  "meta": {"kind": "chunk", "doc_id": r["doc_id"],
                           "section": r.get("section", ""), "order": r.get("order", 0)}}
                 for r in chunk_rows]
        st_chunks = index_texts(items, name="chunks", root=self.out / "vector",
                                batch_size=batch_size) if items else None
        lib = ImageLibrary(self.out / "vision")
        img_items = lib.as_vector_items()
        st_images = index_texts(img_items, name="images", root=self.out / "vector",
                                batch_size=batch_size) if img_items else None
        return {"chunks_indexed": st_chunks.stats()["count"] if st_chunks else 0,
                "images_indexed": st_images.stats()["count"] if st_images else 0,
                "seconds": round(time.time() - t0, 1),
                "chunk_store": st_chunks.stats() if st_chunks else {},
                "image_store": st_images.stats() if st_images else {}}

    # -- 阶段 4：抽取 -----------------------------------------------------
    def stage_extract(self, *, limit: Optional[int] = None,
                      max_chunks_per_doc: int = 1,
                      chat_fn: Optional[Any] = None,
                      model: str = "qwen3.5:latest") -> Dict[str, Any]:
        from ..po.store import POGraph
        rows = self._read_jsonl("chunks.jsonl")
        if limit:
            keep = {p.stem for p in self.pdfs(limit)}
            rows = [r for r in rows if r.get("doc_id") in keep]
        if not rows:
            return {"error": "无 chunks，请先跑 stage_text", "chunks": 0}
        # 每篇最多 N 个块（优先 abstract/method/result）
        by_doc: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            by_doc.setdefault(r["doc_id"], []).append(r)
        picked: List[Chunk] = []
        for doc_id, rs in by_doc.items():
            rs.sort(key=lambda x: (0 if str(x.get("section", "")).lower().startswith(
                ("abstract", "method", "result")) else 1, x.get("order", 0)))
            for r in rs[:max_chunks_per_doc]:
                picked.append(Chunk(id=r["id"], doc_id=doc_id,
                                    section=r.get("section", ""),
                                    order=int(r.get("order", 0)),
                                    text=r["text"]))
        ex = POExtractor(chat_fn=chat_fn or OllamaChat(model=model))
        results: List[ExtractionResult] = []
        t0 = time.time()
        for c in picked:
            try:
                results.append(ex.extract(c, paper_id=c.doc_id,
                                          version_id=f"version:{c.doc_id}",
                                          locator=c.section))
            except Exception as exc:  # noqa: BLE001
                self.state["errors"].append({"doc": c.doc_id, "stage": "extract",
                                             "error": str(exc)[:200]})
        g = ex.to_graph(results)
        out = self.out / "po_extracted.json"
        g.save(out)
        for doc_id in by_doc:
            slot = self.state["docs"].setdefault(doc_id, {"stages": {}})
            slot["stages"]["extract"] = {"done": True, "at": now_iso()}
        self.save()
        return {"chunks": len(picked), "nodes": sum(r.kept for r in results),
                "assertions": sum(len(r.assertions) for r in results),
                "problems": sum(len(r.problems) for r in results),
                "graph_nodes": len(g.nodes), "graph_assertions": len(g.assertions),
                "seconds": round(time.time() - t0, 1),
                "graph_path": str(out),
                "sample_problems": [p for r in results for p in r.problems][:12],
                "chat_stats": getattr(ex.chat, "stats", {})}

    # -- 汇总 -------------------------------------------------------------
    def _read_jsonl(self, name: str) -> List[Dict[str, Any]]:
        p = self.out / name
        out: List[Dict[str, Any]] = []
        if p.exists():
            with p.open(encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        try:
                            out.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        return out

    def report(self) -> Dict[str, Any]:
        docs = self.state.get("docs", {})
        stages: Dict[str, int] = {}
        for d in docs.values():
            for s in d.get("stages", {}):
                stages[s] = stages.get(s, 0) + 1
        chunks = self._read_jsonl("chunks.jsonl")
        lib = ImageLibrary(self.out / "vision")
        return {
            "data_dir": str(self.data), "out_dir": str(self.out),
            "pdf_available": len(self.pdfs(0)),
            "docs_processed": len(docs), "stages": stages,
            "chunks": len(chunks),
            "chunk_sections": _top_sections(chunks),
            "images": lib.stats(),
            "errors": len(self.state.get("errors", [])),
            "error_samples": self.state.get("errors", [])[:5],
            "updated_at": self.state.get("updated_at"),
        }


def _top_sections(rows: Sequence[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for r in rows:
        k = str(r.get("section", "") or "unknown")[:40]
        counts[k] = counts.get(k, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1])[:10])
