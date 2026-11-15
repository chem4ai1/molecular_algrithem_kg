"""CapFactory 命令行入口.

常用命令::

    python -m capfactory.cli status
    python -m capfactory.cli build -q 'abs:"peptide toxicity" AND abs:prediction' -n 2 \
        --repo 'toxinpred|https://github.com/raghavagps/toxinpred3'
    python -m capfactory.cli search "toxicity prediction"
    python -m capfactory.cli replicate --capability "toxicity" --candidates 2
    python -m capfactory.cli research
    python -m capfactory.cli export
    python -m capfactory.cli serve --port 8080
    python -m capfactory.cli selftest      # 离线自检（无需 LLM / 网络）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from .config import get_settings
from .utils import setup_logging


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def cmd_status(args) -> int:
    from .pipeline import CapFactory

    st = CapFactory().status()
    s = st["stats"]
    print("\n=== CapFactory 状态 ===")
    print(f"论文 {s['n_papers']} · 能力 {s['n_capabilities']} · 已验证 {s['n_verified']} · "
          f"节点 {s['n_nodes']} · 边 {s['n_edges']}")
    print(f"平均成熟度 {s['avg_maturity']:.2f} · 数据集 {len(st['datasets'])} 个")
    print(f"LLM: {'在线' if st['llm']['available'] else '离线'} ({st['llm']['model']})")
    if st["runs"]:
        print("最近运行：")
        for r in st["runs"][:5]:
            print(f"  {r['id']:<16} {r['kind']:<10} {r['status']:<8} {r.get('summary', '')[:60]}")
    return 0


def cmd_build(args) -> int:
    from .pipeline import CapFactory

    repos: List[dict] = []
    for spec in args.repo or []:
        if "|" in spec:
            match, url = spec.split("|", 1)
        else:
            match, url = "", spec
        repos.append({"match": match.strip(), "url": url.strip()})
    result = CapFactory().build_kg(
        queries=args.query, max_papers=args.max_papers, repos=repos,
        fetch_code=not args.no_code,
        progress=lambda lvl, msg: print(f"  [{lvl}] {msg}"),
    )
    print("\n=== 抽取完成 ===")
    _print({"papers": len(result["papers"]), "stats": result["stats"],
            "exports": result["exports"], "elapsed_s": result["elapsed_s"]})
    return 0


def cmd_search(args) -> int:
    from .kg import KnowledgeGraph

    graph = KnowledgeGraph().load()
    hits = graph.search_capabilities(args.query, top_k=args.limit)
    if not hits:
        print("未检索到能力，请先执行 build")
        return 1
    for i, h in enumerate(hits, 1):
        node = graph.get(h.node_id) or {}
        a = node.get("attrs", {})
        ver = a.get("verification", {})
        print(f"{i}. {node.get('label')}  [score={h.score:.3f} 成熟度={a.get('maturity', 0):.2f}"
              f"{' 已验证' if ver.get('passed') else ''}]")
        print(f"   任务：{a.get('task', '')} | {(a.get('summary') or '')[:120]}")
    return 0


def cmd_replicate(args) -> int:
    from .pipeline import CapFactory

    settings = get_settings()
    if args.candidates:
        settings.data["replicate"]["max_candidates"] = args.candidates
    result = CapFactory(settings).replicate(
        capability=args.capability, dataset=args.dataset,
        progress=lambda lvl, msg: print(f"  [{lvl}] {msg}"),
    )
    best = result["best"]
    print("\n=== 复刻结果 ===")
    print(f"能力：{result['capability_name']} | 方案：{best['plan']} | "
          f"{'通过' if best['passed'] else '未通过'} | score={best['score']:.3f}")
    print("指标：", json.dumps(best["metrics"], ensure_ascii=False))
    print("代码：", best["code_path"])
    for i, c in enumerate(result["candidates"], 1):
        r = c["report"]
        print(f"  候选{i} {c['plan']['name'][:44]:<46} score={r['overall_score']:.3f} "
              f"{'✓' if c['passed'] else '✗'} "
              f"auc={(r['metrics'].get('values') or {}).get('roc_auc', 0)}")
    _print({"run_dir": result["run_dir"], "run_id": result["run_id"]})
    return 0 if best["passed"] else 2


def cmd_research(args) -> int:
    from .pipeline import CapFactory

    result = CapFactory().research(needs=args.need,
                                   progress=lambda lvl, msg: print(f"  [{lvl}] {msg}"))
    cov = result["coverage"]["summary"]
    print(f"\n覆盖：已覆盖 {cov['covered']} / 部分 {cov['partial']} / 缺口 {cov['gap']}"
          f"（覆盖率 {cov['coverage_rate']:.1%}）")
    for i, d in enumerate(result["directions"], 1):
        print(f"{i}. [{d['priority']:.2f}] {d['title']}")
        print(f"   缺口：{d['gap'][:120]}")
    print(f"\n报告：{result['report_path']}")
    return 0


def cmd_export(args) -> int:
    from .kg import KnowledgeGraph
    from .kg.export import export_all

    graph = KnowledgeGraph().load()
    files = export_all(graph, get_settings().path("kg_dir") / "exports")
    _print(files)
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    uvicorn.run("capfactory.web.server:app", host=args.host, port=args.port)
    return 0


def cmd_selftest(args) -> int:
    """离线端到端自检：合成数据 → 构图 → 模板复刻 → 验证 → 报告。"""
    from .selftest import run_selftest

    ok = run_selftest(verbose=True)
    return 0 if ok else 1


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="capfactory", description="算法能力工厂 CLI")
    ap.add_argument("--offline", action="store_true", help="强制离线模式（不调用 LLM）")
    ap.add_argument("--log-level", default="INFO")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("status", help="查看总体状态")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("build", help="能力抽取：检索论文 → 解析 → 构图")
    p.add_argument("-q", "--query", action="append", required=True, help="arXiv 检索式，可多次指定")
    p.add_argument("-n", "--max-papers", type=int, default=3, help="每个检索式取多少篇")
    p.add_argument("--repo", action="append", help="代码仓库，格式 匹配词|URL")
    p.add_argument("--no-code", action="store_true", help="不拉取代码仓库")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("search", help="检索能力")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=5)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("replicate", help="能力复刻 + 自动验证")
    p.add_argument("--capability", required=True, help="能力 ID 或检索词")
    p.add_argument("--dataset", default=None, help="数据集目录或 CSV 路径")
    p.add_argument("--candidates", type=int, default=None, help="候选方案数量")
    p.set_defaults(func=cmd_replicate)

    p = sub.add_parser("research", help="覆盖度分析与研究方向建议")
    p.add_argument("--need", action="append", help="企业需求，可多次指定")
    p.set_defaults(func=cmd_research)

    p = sub.add_parser("export", help="导出 GraphML / Neo4j CSV / Turtle")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("serve", help="启动 Web 服务")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("selftest", help="离线端到端自检")
    p.set_defaults(func=cmd_selftest)

    args = ap.parse_args(argv)
    setup_logging(args.log_level)
    if args.offline:
        settings = get_settings()
        settings.data["llm"]["offline"] = True
        from .llm import LLMClient, set_client

        set_client(LLMClient(settings, offline=True))
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n已中断")
        return 130
    except Exception as exc:  # noqa: BLE001 - CLI 顶层兜底
        print(f"错误：{type(exc).__name__}: {exc}", file=sys.stderr)
        if args.log_level.upper() == "DEBUG":
            raise
        return 1


if __name__ == "__main__":
    sys.exit(main())
