"""批量 PDF → Markdown：先分版式，再分流解析，产出可复核的 manifest.

两阶段（这是把 783 篇从「几小时盲跑」变成「可预估」的关键）：

1. **预扫描**：只读文本块 bbox 判单/双栏，783 篇约 40 s；
2. **分流解析**：
   - 单栏 → PyMuPDF（0.2 s/篇，线程池 8 路）
   - 双栏 → MinerU（18–69 s/篇，容器并发 1，串行）

产物：

```
data/docx/<arxiv_id>.md          每篇的 Markdown（带 # 层级）
data/docx/_manifest.jsonl        追加式清单：doc_id/parser/layout/chars/seconds/ok
data/docx/_progress.log          阶段进度（便于 tail -f）
```

断点续跑：目标 md 已存在且 >500 字符则跳过；失败写入 manifest 而不中断整批。
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..utils import now_iso
from ..ingest.mineru import MinerUClient, detect_two_column, parse_pdf_smart

DEFAULT_PDF = "/home/zengshuxin/xKG-main/data/papers/pdf"
DEFAULT_OUT = "/home/zengshuxin/xKG-main/data/docx"
MIN_CHARS = 500


def _log(msg: str, log_path: Optional[Path] = None) -> None:
    line = f"[{now_iso()}] {msg}"
    print(line, flush=True)
    if log_path:
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def scan_layouts(pdf_dir: str | Path, *, limit: int = 0,
                 log_path: Optional[Path] = None) -> Dict[str, Any]:
    """预扫描单/双栏，返回分组清单（不解析正文）。"""
    pdfs = sorted(Path(pdf_dir).glob("*.pdf"))
    if limit:
        pdfs = pdfs[:limit]
    t0 = time.time()
    single: List[str] = []
    double: List[str] = []
    for i, p in enumerate(pdfs, 1):
        info = detect_two_column(p)
        (double if info.two_column else single).append(p.stem)
        if i % 100 == 0:
            _log(f"预扫描 {i}/{len(pdfs)}：单栏 {len(single)} / 双栏 {len(double)}", log_path)
    return {"n": len(pdfs), "single": single, "double": double,
            "seconds": round(time.time() - t0, 1),
            "double_ratio": round(len(double) / max(len(pdfs), 1), 3)}


def _parse_one(pdf: Path, out_dir: Path, *, force: Optional[str],
               client: Optional[MinerUClient]) -> Dict[str, Any]:
    t0 = time.time()
    try:
        doc = parse_pdf_smart(pdf, force=force, client=client, out_dir=out_dir)
        md_path = out_dir / f"{pdf.stem}.md"
        chars = int(doc.get("full_chars") or 0)
        ok = md_path.exists() and chars >= MIN_CHARS
        return {"doc_id": pdf.stem, "ok": ok, "chars": chars,
                "sections": doc.get("n_sections", 0),
                "parser": doc.get("parser", ""),
                "layout": doc.get("layout", {}),
                "mineru_seconds": doc.get("mineru_seconds"),
                "mineru_failed": doc.get("mineru_failed", ""),
                "seconds": round(time.time() - t0, 1),
                "md": str(md_path) if ok else "",
                "error": "" if ok else "empty_or_missing_markdown"}
    except Exception as exc:  # noqa: BLE001
        return {"doc_id": pdf.stem, "ok": False, "chars": 0, "parser": "",
                "seconds": round(time.time() - t0, 1), "error": str(exc)[:200]}


def batch_parse(pdf_dir: str | Path = DEFAULT_PDF,
                out_dir: str | Path = DEFAULT_OUT, *,
                limit: int = 0, workers: int = 8, resume: bool = True,
                force: Optional[str] = None,
                only: Optional[Sequence[str]] = None,
                log_path: Optional[Path] = None) -> Dict[str, Any]:
    pdf_dir, out_dir = Path(pdf_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_path or (out_dir / "_progress.log")
    manifest_path = out_dir / "_manifest.jsonl"

    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if only:
        wanted = set(only)
        pdfs = [p for p in pdfs if p.stem in wanted]
    if limit:
        pdfs = pdfs[:limit]

    todo = []
    skipped = 0
    for p in pdfs:
        md = out_dir / f"{p.stem}.md"
        if resume and md.exists() and md.stat().st_size >= MIN_CHARS:
            skipped += 1
            continue
        todo.append(p)

    _log(f"待解析 {len(todo)} 篇（跳过已完成 {skipped}）", log_path)
    layout = scan_layouts(pdf_dir, limit=0, log_path=log_path) if not only else {}
    groups = {"single": [p for p in todo if p.stem in set(layout.get("single", []))],
              "double": [p for p in todo if p.stem in set(layout.get("double", []))]}
    if only or not layout:
        # 指定文件时按单篇重新判版式
        groups = {"single": [], "double": []}
        for p in todo:
            (groups["double"] if detect_two_column(p).two_column else groups["single"]).append(p)

    results: List[Dict[str, Any]] = []
    client = MinerUClient()
    if not client.available():
        _log("MinerU 不可用：双栏将回退 PyMuPDF", log_path)

    # 阶段 1：单栏（线程池）
    t1 = time.time()
    if groups["single"]:
        _log(f"阶段 1/2：单栏 {len(groups['single'])} 篇（PyMuPDF，{workers} 路）", log_path)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(_parse_one, p, out_dir, force="pymupdf", client=None)
                    for p in groups["single"]]
            for i, f in enumerate(futs, 1):
                r = f.result()
                results.append(r)
                if i % 50 == 0:
                    ok = sum(1 for x in results if x["ok"])
                    _log(f"  单栏 {i}/{len(futs)}：成功 {ok}", log_path)
    _log(f"阶段 1 完成：{round(time.time()-t1,1)} s", log_path)

    # 阶段 2：双栏（串行，容器并发 1）
    t2 = time.time()
    if groups["double"]:
        _log(f"阶段 2/2：双栏 {len(groups['double'])} 篇（MinerU，串行）", log_path)
        for i, p in enumerate(groups["double"], 1):
            r = _parse_one(p, out_dir, force="mineru" if client.available() else "pymupdf",
                           client=client)
            results.append(r)
            _log(f"  双栏 {i}/{len(groups['double'])} {p.stem} "
                 f"{r.get('parser')} {r.get('seconds')}s ok={r['ok']}", log_path)
    _log(f"阶段 2 完成：{round(time.time()-t2,1)} s", log_path)

    with manifest_path.open("a", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    ok = sum(1 for r in results if r["ok"])
    by_parser: Dict[str, int] = {}
    for r in results:
        by_parser[r.get("parser", "?")] = by_parser.get(r.get("parser", "?"), 0) + 1
    summary = {"processed": len(results), "ok": ok, "failed": len(results) - ok,
               "skipped": skipped, "by_parser": by_parser,
               "layout": {k: len(v) for k, v in groups.items()},
               "seconds": round(time.time() - t1 + 0, 1),
               "out_dir": str(out_dir), "manifest": str(manifest_path)}
    _log(f"完成：成功 {ok}/{len(results)}，解析器分布 {by_parser}", log_path)
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="批量 PDF → Markdown（双栏走 MinerU）")
    ap.add_argument("--pdf-dir", default=DEFAULT_PDF)
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--only", nargs="*", default=None, help="只处理指定 arxiv id")
    ap.add_argument("--force", default=None, choices=["mineru", "pymupdf"])
    ap.add_argument("--no-resume", action="store_true")
    ap.add_argument("--scan-only", action="store_true", help="只做版式预扫描")
    a = ap.parse_args(argv)

    if a.scan_only:
        info = scan_layouts(a.pdf_dir, limit=a.limit)
        print(json.dumps({k: (v if k != "single" and k != "double" else len(v))
                          for k, v in info.items()}, ensure_ascii=False, indent=2))
        return 0
    out = batch_parse(a.pdf_dir, a.out_dir, limit=a.limit, workers=a.workers,
                      resume=not a.no_resume, force=a.force, only=a.only)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
