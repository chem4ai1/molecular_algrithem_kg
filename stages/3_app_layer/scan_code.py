#!/usr/bin/env python3
"""扫本地仓库 → 代码域节点（CodeUnit/CodeSymbol/Dependency/EntryPoint/TestUnit/EnvSpec）。

用法：
    python stages/3_app_layer/scan_code.py --repo algomole__molcraft
    python stages/3_app_layer/scan_code.py --list
    python stages/3_app_layer/scan_code.py --repo X --out storage/sciforge/code_graph.json
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from capfactory.po import POGraph                       # noqa: E402
from capfactory.applayer.codescan import scan_repo     # noqa: E402
from capfactory.applayer.codegraph import build_code_graph  # noqa: E402

REPOS = ROOT / "data/repos/src"
DEFAULT_OUT = ROOT / "storage/sciforge/code_graph.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--repo")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    a = ap.parse_args()
    if a.list:
        names = sorted(p.name for p in REPOS.iterdir() if p.is_dir())
        print(f"{len(names)} 个仓库：")
        for n in names[:30]:
            print(" ", n)
        if len(names) > 30:
            print(f"  ... 另有 {len(names)-30} 个")
        return 0
    if not a.repo:
        ap.print_help()
        return 2
    d = REPOS / a.repo
    if not d.exists():
        print(f"仓库不存在：{d}")
        return 1
    scan = scan_repo(d)
    g = POGraph("code")
    n = build_code_graph(g, scan)
    g.save(a.out)
    print(json.dumps({"repo": a.repo, "stats": scan["stats"], "written": n,
                      "nodes": len(g.nodes), "assertions": len(g.assertions),
                      "out": a.out}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
