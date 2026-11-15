"""AlgoGraph 命令行：构建、检视、演示与论文复现缺口导出。

    python -m capfactory.algograph.cli demo
    python -m capfactory.algograph.cli build --path solution.py --capability-id cap_toxipep \
        --paper-json papers.json --out storage_cf/algograph
    python -m capfactory.algograph.cli inspect --graph storage_cf/algograph/<id>.graph.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from .linker import GroundingEngine
from .repair import RepairLocator
from .store import AlgoGraph
from .version import build_capability_version


def _demo_payload() -> Dict[str, Any]:
    from ..web._legacy.algograph_api import DEMO_PAPERS, DEMO_SOURCE
    return {
        "sources": {"toxipep": DEMO_SOURCE},
        "paper_modules": DEMO_PAPERS,
        "metric_bindings": [{"metric_name": "roc_auc", "role": "gate", "threshold": 0.6}],
        "test_cases": [{"id": "tc_gate", "assertion": "roc_auc >= 0.6",
                        "metric_name": "roc_auc", "role": "gate"}],
    }


def _print_version(cv: Any) -> None:
    s = cv.stats()
    print(f"\n=== CapabilityVersion {cv.version_id} ===")
    print(f"节点 {s['n_nodes']} / 边 {s['n_edges']} / 校验问题 {len(s['problems'])}")
    print("节点类型:", s["nodes_by_type"])
    print("因果类型:", s["causal_types"])
    print("抽象层级:", s["abstraction_levels"])
    print("调用图:", cv.graph.meta.get("callgraph_stats"))
    print("Grounding 覆盖率:", (cv.grounding.get("summary") or {}).get("grounding_coverage"))
    for row in (cv.grounding.get("summary") or {}).get("conceptual_gaps", [])[:5]:
        print("  [conceptual gap]", row)
    gaps = cv.modules_and_gaps()
    for a in gaps["next_actions"][:5]:
        print("  [复现任务]", a["target"], "-", a["reason"])
    loc = RepairLocator().locate(cv, {"metric": "roc_auc", "value": 0.52,
                                      "threshold": 0.6})
    print("修复首选节点:", [x["label"] for x in loc["ranked_candidates"][:3]])
    print("块级精确片段:", len(loc["precise_blocks"]),
          "| 父函数上下文:", len(loc["function_context"]))
    if s["problems"]:
        print("校验问题:")
        for p in s["problems"][:10]:
            print("  -", p)


def _cmd_demo(args: argparse.Namespace) -> int:
    payload = _demo_payload()
    cv = build_capability_version(args.capability_id, payload["sources"],
                                  paper_modules=payload["paper_modules"],
                                  metric_bindings=payload["metric_bindings"],
                                  test_cases=payload["test_cases"])
    _print_version(cv)
    if args.out:
        out = Path(args.out)
        cv.save(out / f"{cv.version_id.replace('/', '_')}.json")
        print(f"\n已保存 -> {out / (cv.version_id.replace('/', '_') + '.json')}")
        print("Mermaid (meso):\n")
        from .causal import to_mermaid
        print(to_mermaid(cv.graph, level="meso"))
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.exists():
        print(f"文件不存在：{path}")
        return 2
    papers: List[Dict[str, Any]] = []
    if args.paper_json:
        pj = Path(args.paper_json)
        if pj.exists():
            data = json.loads(pj.read_text(encoding="utf-8"))
            papers = data if isinstance(data, list) else data.get("modules", [])
    cv = build_capability_version(
        args.capability_id, {path.stem: path.read_text(encoding="utf-8")},
        code_path=str(path), paper_modules=papers,
        metric_bindings=[{"metric_name": args.metric, "role": "gate",
                          "threshold": args.threshold}])
    _print_version(cv)
    out = Path(args.out)
    cv.save(out / f"{cv.version_id.replace('/', '_')}.json")
    print(f"\n已保存 -> {out}")
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    p = Path(args.graph)
    if not p.exists():
        print(f"文件不存在：{p}")
        return 2
    g = AlgoGraph.load(p)
    print(json.dumps(g.stats(), ensure_ascii=False, indent=2))
    if args.retrieve:
        print("\n检索结果:", json.dumps(
            g.retrieve(args.retrieve, granularity=args.granularity)[:3],
            ensure_ascii=False, indent=2)[:3000])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="CapFactory 细粒度算法图")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="用内置 ToxiPep 示例构建完整版本")
    d.add_argument("--capability-id", default="cap_toxicity_toxipep")
    d.add_argument("--out", default="")
    d.set_defaults(func=_cmd_demo)

    b = sub.add_parser("build", help="从 Python 文件构建")
    b.add_argument("--path", required=True)
    b.add_argument("--capability-id", default="cap_from_file")
    b.add_argument("--paper-json", default="")
    b.add_argument("--metric", default="roc_auc")
    b.add_argument("--threshold", type=float, default=0.6)
    b.add_argument("--out", default="storage_cf/algograph")
    b.set_defaults(func=_cmd_build)

    i = sub.add_parser("inspect", help="检视已落盘的图")
    i.add_argument("--graph", required=True)
    i.add_argument("--retrieve", default="")
    i.add_argument("--granularity", default="function", choices=("function", "block"))
    i.set_defaults(func=_cmd_inspect)

    args = ap.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
