#!/usr/bin/env python3
"""二次抽取 CLI：基于已有抽取结果，回原文对应段落补抽。

示例：
    python stages/1_extraction/refine_run.py --list
    python stages/1_extraction/refine_run.py --paper 2411.06608 --target R1_contribution --dry-run
    python stages/1_extraction/refine_run.py --paper 2411.06608 --target R2_experiment_arm --apply

--dry-run  只打印 prompt 与候选段落，不调模型（默认）
--apply    调模型并把结果写回图（写回前会备份到 storage/extract_target_backup/）
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from capfactory.po import POGraph                       # noqa: E402
from capfactory.semantic.extractspec import loader, run_refine  # noqa: E402

GRAPH = ROOT / "storage_cf/sciforge/batch10_semantic_v4.json"   # 只读：语义层事实
OUT = ROOT / "storage_cf/sciforge/app_refine.json"              # 写入：二次抽取产物
MD = ROOT / "data/docx"
BACKUP = ROOT / "storage/extract_target_backup"


DEFAULT_ERNIE = "baidu/ernie-5.5-flash-preview:free"


def _chat(backend: str = "vllm", model: str = ""):
    """返回 (prompt -> text)；不可用时返回 None（退化为 dry-run）。"""
    try:
        if backend == "openrouter":
            from capfactory.vector.labeler import OpenRouterBackend
            b = OpenRouterBackend(model=model or DEFAULT_ERNIE)
            if not b.ok:
                return None
            return lambda prompt: b.chat(prompt, max_tokens=4000)
        from capfactory.llm.backends import chat as _chat  # 与 runner.py 同一入口
        return lambda prompt: _chat(prompt, backend=backend)
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--paper")
    ap.add_argument("--target")
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--apply", dest="apply", action="store_true")
    ap.add_argument("--backend", default="vllm",
                    choices=["vllm", "openrouter", "ollama"])
    ap.add_argument("--model", default="",
                    help="openrouter 模型；默认 baidu/ernie-5.5-flash-preview:free")
    a = ap.parse_args()

    if a.list:
        d = loader.load(force=True)
        print("一次抽取阶段：")
        for s in sorted(d["stages"].values(), key=lambda x: x.order):
            print(f"  {s.order}. {s.stage:<14} classes={s.classes} "
                  f"字段={s.fields[:4]}{'…' if len(s.fields) > 4 else ''}")
        print("二次抽取目标：")
        for r in sorted(d["refines"].values(), key=lambda x: x.order):
            print(f"  {r.order}. {r.refine:<20} class={r.cls:<14} "
                  f"relation={r.relation or '-'} 字段={r.field_names}")
        if d["errors"]:
            print("配置错误：")
            for e in d["errors"]:
                print("  -", e)
        return 0

    if not (a.paper and a.target):
        ap.print_help()
        return 2
    # 在已有二次抽取图上累积；没有则从语义层快照起步
    base = OUT if OUT.exists() else GRAPH
    g = POGraph.load(str(base))
    out = run_refine(g, a.paper, a.target,
                     chat_fn=_chat(a.backend, a.model) if a.apply else None,
                     md_dir=MD, dry_run=not a.apply,
                     compact=(a.backend == "openrouter"))
    if a.apply and out.get("applied", {}).get("nodes"):
        BACKUP.mkdir(parents=True, exist_ok=True)
        (BACKUP / f"{a.paper}.{a.target}.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        g.save(str(OUT))
        print(f"已写回 {OUT.name}：+{out['applied']['nodes']} 节点（语义层图未改动）")
    print(json.dumps({k: v for k, v in out.items() if k != "prompt"},
                     ensure_ascii=False, indent=2, default=str))
    if out.get("prompt"):
        print("\n--- prompt ---\n" + out["prompt"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
