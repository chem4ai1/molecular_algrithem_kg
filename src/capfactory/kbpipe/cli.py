"""知识底座流水线 CLI.

    python3 -m capfactory.pipeline.cli inventory
    python3 -m capfactory.pipeline.cli text    --limit 3
    python3 -m capfactory.pipeline.cli vision  --limit 2 --pages 2
    python3 -m capfactory.pipeline.cli vector
    python3 -m capfactory.pipeline.cli extract --limit 1 --chunks 1
    python3 -m capfactory.pipeline.cli report
    python3 -m capfactory.pipeline.cli search --query "peptide toxicity" --collection chunks
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from .runner import DEFAULT_DATA, PipelineRunner


def _p(obj: Any, limit: int = 3500) -> None:
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    print(text[:limit] + ("\n..." if len(text) > limit else ""))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="知识底座抽取与落地流水线")
    ap.add_argument("stage", choices=["inventory", "text", "vision", "vector",
                                      "extract", "report", "search"])
    ap.add_argument("--data", default=DEFAULT_DATA)
    ap.add_argument("--out", default="storage_cf/pipeline")
    ap.add_argument("--limit", type=int, default=0, help="处理前 N 篇 PDF（0=全量）")
    ap.add_argument("--pages", type=int, default=2, help="每篇抽多少个图页")
    ap.add_argument("--chunks", type=int, default=1, help="每篇最多抽多少个文本块")
    ap.add_argument("--max-chars", type=int, default=1600)
    ap.add_argument("--model", default="qwen3.5:latest", help="抽取用文本模型")
    ap.add_argument("--vl-model", default="", help="覆盖默认 VL 模型")
    ap.add_argument("--no-resume", action="store_true")
    ap.add_argument("--query", default="")
    ap.add_argument("--collection", default="chunks", choices=["chunks", "images", "papers"])
    ap.add_argument("--top-k", type=int, default=5)
    args = ap.parse_args(argv)

    if args.stage == "inventory":
        from ..catalog.inventory import write
        _p(write(None, args.data, "storage_cf/catalog"))
        return 0

    if args.stage == "search":
        from ..vector import VectorStore
        root = Path(args.out) / "vector"
        st = VectorStore(root, args.collection)
        if not st.items:
            print(f"集合 {args.collection} 为空：{root/args.collection}")
            return 2
        _p({"collection": args.collection, "count": len(st.items),
            "hits": st.search(args.query, top_k=args.top_k)})
        return 0

    r = PipelineRunner(args.data, args.out, limit=args.limit,
                       resume=not args.no_resume)
    if args.stage == "text":
        _p(r.stage_text(limit=args.limit or None, max_chars=args.max_chars))
    elif args.stage == "vision":
        _p(r.stage_vision(limit=args.limit or None,
                          pages_per_doc=args.pages or 2,
                          model=args.vl_model or None))
    elif args.stage == "vector":
        _p(r.stage_vector())
    elif args.stage == "extract":
        _p(r.stage_extract(limit=args.limit or None,
                           max_chunks_per_doc=args.chunks or 1,
                           model=args.model))
    else:
        _p(r.report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
