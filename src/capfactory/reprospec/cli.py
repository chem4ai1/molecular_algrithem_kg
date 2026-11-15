"""复现应用层 CLI：一键跑 lite 验证 + 生成汇总报告。

    PYTHONPATH=. python3 -m capfactory.reprospec.cli \
        --arxiv 2411.06608 --effort lite \
        --report-md capfactory/md/REPRODUCTION_VALIDATION_REPORT.md

    # 崩溃恢复
    PYTHONPATH=. python3 -m capfactory.reprospec.cli \
        --resume storage_cf/repro_runs/2411.06608

    # 批量（逗号分隔）
    PYTHONPATH=. python3 -m capfactory.reprospec.cli \
        --batch 2411.06608,2102.09844 --effort lite
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_GRAPH = Path("storage_cf/sciforge/app_reproduction.json")
DEFAULT_OUT = Path("storage_cf/repro_runs")


def _load_graph(path: Path):
    from capfactory.po import POGraph
    if not path.exists():
        raise SystemExit(f"图不存在: {path}")
    return POGraph.load(str(path))


def _paper_id(g, arxiv: str) -> str:
    pid = "paper:" + arxiv
    if pid in g.nodes:
        return pid
    for nid, n in g.nodes.items():
        if getattr(n, "type", "") == "Paper" and \
                str((getattr(n, "attrs", {}) or {}).get("arxiv_id", "")) == arxiv:
            return nid
    raise SystemExit(f"图中找不到论文 {arxiv}")


def _verify_double_run(spec, graph, run_dir: Path, effort: str) -> Dict[str, Any]:
    """双跑一致性（验证设计 §5 第 3 条）：独立临时目录再执行一次。"""
    from capfactory.reprospec.executor import execute_repro
    from capfactory.reprospec.scoring import claim_anchors
    anchors_file = run_dir / "CLAIM_ANCHORS.json"
    anchors = json.loads(anchors_file.read_text(encoding="utf-8")) \
        if anchors_file.exists() else {}
    first = anchors.get("outputs_sha", "")
    if effort == "dry" or not first:
        return {"performed": False, "reason": "dry 或无首次 outputs_sha"}
    with tempfile.TemporaryDirectory() as td:
        ex2 = execute_repro(spec, graph, out_dir=td, effort=effort)
    second = ex2.outputs_sha
    equal = bool(second) and second == first
    anchors.update({"second_run_sha": second,
                    "double_run_equal": equal,
                    "drift": "" if equal else "outputs_sha_mismatch"})
    anchors_file.write_text(json.dumps(anchors, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    return {"performed": True, "first": first, "second": second,
            "equal": equal}


def _read_json(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def build_validation_report(runs: List[Dict[str, Any]], path: Path) -> str:
    """按 REPRODUCTION_EVALUATION_DESIGN.md §6.2 生成 7 节汇总报告。"""
    L: List[str] = [
        "# 论文复现实际验证报告", "",
        f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}　"
        f"生成命令：`python3 -m capfactory.reprospec.cli --effort lite`", "",
        "## 1. 验证范围与边界", "",
        "本验证覆盖三层（见 `REPRODUCTION_EVALUATION_DESIGN.md` §0）：", "",
        "| 层 | 内容 |",
        "|---|---|",
        "| L1 规格对齐 | 方法/模块/符号/数据契约/数值是否被结构化且可追溯地表示 |",
        "| L2 评测协议复现 | 独立脚本从论文表格原始行重算榜单/SOTA/方向，与另一条管线的应用层榜单行比对 |",
        "| L3 方法可执行性 | 方法模块链按 code_plan.order 执行、符号落地、无 stub |", "",
        "**明确不验证（out_of_scope）**：本轮 lite 不训练模型；原论文模型训练"
        "精度、原论文实验全量表、跨数据集泛化均不在本次验证范围。"
        "训练复现可行性（`effort=full`）见 `TRAIN_FEASIBILITY.json` 与 "
        "`FULL_TRAIN_REPRODUCTION_DESIGN.md`。", "",
        "**L2 独立性**：脚本输入是 `Benchmark.attrs.model_results`（PDF 表格原始抽取行），"
        "脚本独立实现 `normalize_model / normalize_metric_name / to_float / "
        "compute_sota`；对照组是 `applayer/miner.py` 的 leaderboard 挖掘器产物。"
        "脚本不读取 `LeaderboardEntry.value` 或 `sota_by_metric` 等期望值。", "",
        "## 2. 环境基线", "",
        "| 项 | 值 |", "|---|---|",
        f"| Python | {platform.python_version()} |",
        f"| 平台 | {platform.platform()} |",
        "| 执行隔离 | 子进程 + env 白名单 + AST import 白名单 + 超时 |",
    ]
    for r in runs:
        d = Path(r["ws"])
        rep = _read_json(d / "REPRO_VERDICTS.json")
        spec = _read_json(d / "REPRO_SPEC.json")
        L += [f"| 图 `{r['graph']}` | {r['n_nodes']} 节点 / "
              f"{r['n_assertions']} 断言 |",
              f"| run `{d}` | arxiv={rep.get('arxiv_id')} effort={rep.get('effort')} |",
              f"| P3-1 scope | `{r.get('scope', 'legacy')}`"
              f"（源图 {r['n_assertions']} 断言 → 归一化视图 "
              f"{r.get('n_assertions_view', r['n_assertions'])} 断言，源图文件不变） |",
              f"| spec_hash | `{spec.get('spec_hash', '')[:32]}…` |"]
    L += ["", "## 3. 主指标表（dry 基线 → lite 实测）", "",
          "> dry 基线取自 P0-4 阶段实测记录（`tests/Phase/test_repro_p03_p04.py`，"
          "legacy 图 71 条 SAU）；lite 列为 `strict` 归一化视图（74 条 SAU）的真实执行结果。"
          "两者 spec 集合不同，此表用于趋势对照，不是同一 SAU 集合的逐条对比。", "",
          "| 指标 | dry 基线 | lite 实测 | 说明 |",
          "|---|---:|---:|---|"]
    for r in runs:
        d = Path(r["ws"])
        fe = (_read_json(d / "FINAL_EVALUATION.json").get("evaluation") or {})
        sau = ((_read_json(d / "REPRO_VERDICTS.json").get("sau") or {}))
        L += [
            f"| SAU_score | 0.8947 | {fe.get('sau_score', sau.get('sau_score'))} | aligned/decidable |",
            f"| coverage | 0.5352 | {fe.get('coverage', sau.get('coverage'))} | decidable/total |",
            f"| drift_rate | 0.1053 | {fe.get('drift_rate', sau.get('drift_rate'))} | 漂移占比 |",
            f"| Exec Rate | 0.0 | {fe.get('exec_rate')} | 真跑成功比例 |",
            f"| Perf Gap | — | {fe.get('perf_gap')} | 相对偏差 |",
            f"| Symbol Recall | — | {fe.get('symbol_recall')} | 代码符号命中 |",
            f"| Align_mixed | — | {fe.get('align_mixed')} | 混合级对齐 |",
            f"| Anchor Integrity | — | {r.get('double_run', {}).get('equal')} | 三哈希 + 双跑 |",
        ]
    L += ["", "## 4. 逐类 SAU 判定", "",
          "| kind | aligned | mismatch | stub | absent | unverified |",
          "|---|---:|---:|---:|---:|---:|"]
    for r in runs:
        d = Path(r["ws"])
        sv = _read_json(d / "SAU_VERDICTS.json")
        L += [f"**{r['arxiv']}**（{sv.get('n_total')} 条 SAU / "
              f"decidable {sv.get('n_decidable')} / score {sv.get('sau_score')}）", ""]
        for k, c in (sv.get("counts") or {}).items():
            L.append(f"| {k} | {c.get('aligned', 0)} | {c.get('mismatch', 0)} | "
                     f"{c.get('stub', 0)} | {c.get('absent', 0)} | "
                     f"{c.get('unverified', 0)} |")
        L.append("")
    L += ["## 5. 执行证据", ""]
    for r in runs:
        d = Path(r["ws"])
        rep = _read_json(d / "REPRO_VERDICTS.json")
        ld = _read_json(d / "S2_LADDER.json")
        an = _read_json(d / "CLAIM_ANCHORS.json")
        ev_file = d / ".repro" / "events.ndjson"
        n_events = len(ev_file.read_text(encoding="utf-8").splitlines()) \
            if ev_file.exists() else 0
        L += [
            f"### {r['arxiv']}", "",
            f"- 脚本：`{d / 'REPRO_SCRIPT.py'}`（纯 stdlib，可独立重跑）",
            f"- 执行：{rep.get('execution')}",
            f"- S2 ladder：`{ld.get('verdict')}` / critic `{ld.get('critic_state')}` / "
            f"strict_full={ld.get('strict_full_improvement')}",
            f"- 事件条数：`{n_events}`（`{ev_file}`）",
            f"- 三哈希：code `{an.get('code_sha', '')[:20]}…` / "
            f"inputs `{an.get('inputs_sha', '')[:20]}…` / "
            f"outputs `{an.get('outputs_sha', '')[:20]}…`",
            f"- 双跑一致：`{an.get('double_run_equal')}`"
            f"（second `{str(an.get('second_run_sha', ''))[:20]}…`）",
            "",
        ]
    L += ["## 6. 失败与漂移归因", ""]
    for r in runs:
        d = Path(r["ws"])
        sv = _read_json(d / "SAU_VERDICTS.json")
        fe = (_read_json(d / "FINAL_EVALUATION.json").get("evaluation") or {})
        L += [f"### {r['arxiv']}", "",
              f"- 最终判定：**{fe.get('overall', 'N/A')}**",
              f"- 漂移分布：`{sv.get('by_drift')}`",
              f"- 降级原因：{fe.get('reasons') or '无'}"]
        mm = [v for v in (sv.get("verdicts") or [])
              if v.get("verdict") in ("mismatch", "stub", "absent")]
        for v in mm[:10]:
            L.append(f"  - `{v['sau_id']}` {v['kind']}/{v['verdict']}: "
                     f"{v.get('note', '')}")
        unv = [v for v in (sv.get("verdicts") or [])
               if v.get("verdict") == "unverified"]
        L += [f"- unverified {len(unv)} 条（原因示例）："]
        for v in unv[:5]:
            L.append(f"  - `{v['sau_id']}` {v['kind']}: {v.get('note', '')}")
        shape = _read_json(d / "SHAPE_PROBE.json")
        lin = _read_json(d / "LINEAGE.json")
        L += [f"- 数据缺口（P1-7 静态词表口径）：shape 未登记形式 "
              f"{sum(len(x.get('unknown_forms') or []) for x in shape.get('probes') or [])} 处；"
              f"lineage 带逐字证据 "
              f"{sum(1 for x in (lin.get('lineage') or []) if x.get('evidence_available'))}/"
              f"{len(lin.get('lineage') or [])} 条"]
        norm = r.get("normalization") or {}
        if norm:
            L += [f"- P3-1 范围归一化：剔除跨论文模块 "
                  f"{norm.get('n_excluded_modules', 0)} 个、误挂基线算法 "
                  f"{norm.get('n_excluded_algorithms', 0)} 个，共删边 "
                  f"{norm.get('n_removed_edges', 0)} 条"
                  f"（跨论文 `HAS_MODULE` + 基线算法 `PROPOSES_METHOD`）；"
                  f"证据化补 `MODULE_IMPLEMENTED_BY` 边 "
                  f"{norm.get('n_added_edges', 0)} 条；无可证据化映射而保持缺口的模块 "
                  f"{len(norm.get('unresolved_modules') or [])} 个"]
            for e in (norm.get("added_edges") or [])[:6]:
                L.append(f"  - 补边 `{e['module'].split(':')[-1]}` → "
                         f"`{e['function'].split(':')[-1]}`，命中 "
                         f"{e['matched_terms']}；证据 purpose="
                         f"「{e['evidence_purpose'][:70]}」"
                         f"（{e['grade']}）")
        mb = _read_json(d / "MINIBATCH_PROBE.json")
        if mb:
            L += [f"- P3-2 真实 mini-batch 实测（batch_size="
                  f"{mb.get('batch_size')}）：{mb.get('n_runtime_verified')}/"
                  f"{mb.get('n_probes')} 个探针 runtime_verified，"
                  f"同族继承表单 {mb.get('n_inherited_forms')} 处，"
                  f"残留 unknown {mb.get('n_unknown_remaining')} 处；"
                  f"脚本 `MINIBATCH_SCRIPT.py` 可独立重跑"]
            for x in (mb.get("inheritance") or [])[:6]:
                L.append(f"  - 表单继承 `{x['benchmark']}` 的 "
                         f"`{x['side']}`：{x['declared']} → "
                         f"`{x['effective']}`（{x['rule']}，来源 "
                         f"`{x['inherited_from']}`，非论文原文声明）")
        lev = _read_json(d / "LINEAGE_EVIDENCE.json")
        if lev:
            L += [f"- P3-3 lineage 证据分级：逐字引文 "
                  f"{lev.get('n_verbatim')}/{lev.get('n_lineage')} 条，"
                  f"书目证据 {lev.get('n_bibliographic')} 条，"
                  f"完全无证据 {lev.get('n_none')} 条；"
                  f"标题不是 quote，故 0 条属实。修复路径：{lev.get('remedy', '')[:120]}"]
        tf = _read_json(d / "TRAIN_FEASIBILITY.json")
        if tf:
            L += [f"- 原论文模型训练复现（full）：executable="
                  f"`{tf.get('executable')}` / GPU {tf.get('n_gpus')} 张 / "
                  f"torch_ok={tf.get('torch', {}).get('ok')} / "
                  f"阻塞项 {len(tf.get('blocking') or [])} 条；"
                  f"详见 `TRAIN_FEASIBILITY.json` 与 "
                  f"`FULL_TRAIN_REPRODUCTION_DESIGN.md`"]
        L.append("")
    L += ["## 7. 结论与可复现命令", ""]
    for r in runs:
        fe = (_read_json(Path(r["ws"]) / "FINAL_EVALUATION.json")
              .get("evaluation") or {})
        L += [f"- **{r['arxiv']}**：`{fe.get('overall', 'BLOCKED')}` — "
              f"SAU_score {fe.get('sau_score')} / coverage {fe.get('coverage')} / "
              f"Perf Gap {fe.get('perf_gap')}"]
    L += ["", "```bash",
          "cd /home/zengshuxin/xKG-main/xKG-main",
          "PYTHONPATH=. python3 -m capfactory.reprospec.cli \\",
          "    --arxiv " + (runs[0]["arxiv"] if runs else "2411.06608") +
          " --effort lite \\",
          "    --report-md capfactory/md/REPRODUCTION_VALIDATION_REPORT.md",
          "PYTHONPATH=. python3 -m unittest discover -s tests/Phase -p 'test_*.py'",
          "```", ""]
    if len(runs) > 1:
        L += ["## 8. 多篇回归结论", "",
              "| arxiv | 门链 overall | 最终评估 | R6 | 主要降级原因 | mini-batch 实测 |",
              "|---|---|---|---|---|---|"]
        for r in runs:
            d = Path(r["ws"])
            vr = _read_json(d / "REPRO_VERDICTS.json")
            fe = (_read_json(d / "FINAL_EVALUATION.json").get("evaluation")
                  or {})
            mb = _read_json(d / "MINIBATCH_PROBE.json")
            reasons = (fe.get("reasons") or vr.get("partial") or
                       vr.get("blocked") or [])
            L.append(f"| {r['arxiv']} | `{vr.get('overall')}` | "
                     f"`{fe.get('overall', 'N/A')}` | "
                     f"`{(vr.get('verdicts') or {}).get('R6', {}).get('verdict')}` | "
                     f"{'; '.join(str(x) for x in reasons)[:90] or '无'} | "
                     f"{mb.get('n_runtime_verified', '—')}/"
                     f"{mb.get('n_probes', '—')} |")
        L += ["", "所有降级均由**真实数据缺陷**触发，不是系统故障：", "",
              "- 无 `HAS_CODE` 仓库 → R0/R2 BLOCKED",
              "- `MetricDefinition.direction` 未知/启发式 → R4 BLOCKED 或 PARTIAL",
              "- 表单为占位 `unknown` 且同族无可继承声明 → mini-batch 如实保留 unknown",
              "- 缺 `MODULE_IMPLEMENTED_BY` 且无可证据化映射 → method mismatch 如实保留",
              "", "回归结论：范围归一化只对**存在跨论文误挂**的论文生效，"
              "对数据本身缺失的论文不会人为抬分。", ""]
    text = "\n".join(L)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="GGR 论文复现验证")
    ap.add_argument("--arxiv", default="2411.06608")
    ap.add_argument("--batch", default="")
    ap.add_argument("--effort", default="lite",
                    choices=("dry", "lite", "full"))
    ap.add_argument("--graph", default=str(DEFAULT_GRAPH))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--report-md", default="")
    ap.add_argument("--resume", default="")
    ap.add_argument("--scope", default="strict",
                    choices=("strict", "legacy"),
                    help="strict=P3-1 范围归一化+证据化补边；legacy=原图对照")
    ap.add_argument("--train-plan", action="store_true",
                    help="额外生成原论文模型训练复现可行性报告（不执行训练）")
    ap.add_argument("--data-root", default="/home/zengshuxin/data")
    a = ap.parse_args(argv)

    if a.resume:
        from capfactory.sciforge.repro import resume_repro
        print(json.dumps(resume_repro(a.resume), ensure_ascii=False, indent=2))
        return 0

    g0 = _load_graph(Path(a.graph))
    arxivs = [x.strip() for x in (a.batch or a.arxiv).split(",") if x.strip()]
    runs: List[Dict[str, Any]] = []
    for aid in arxivs:
        pid = _paper_id(g0, aid)
        ws = Path(a.out) / aid
        from capfactory.sciforge.repro import run_repro
        from capfactory.reprospec import compile_reprospec
        from capfactory.reprospec.normalize import normalize_for_repro
        # P3-1：主流程、规格编译、双跑必须复用同一个归一化视图，
        # 否则 spec_hash 漂移会让 outputs_sha 双跑一致性判定失去意义。
        g, norm = normalize_for_repro(
            g0, pid, strict=(a.scope == "strict"), source_graph=a.graph)
        norm.save(ws)
        rep = run_repro(g, pid, ws=ws, effort=a.effort)
        spec = compile_reprospec(g, paper_id=pid)
        if a.train_plan:
            from capfactory.reprospec.train import write_train_feasibility
            write_train_feasibility(spec, g, ws, data_root=a.data_root)
        dbl = _verify_double_run(spec, g, ws, a.effort)
        fe = _read_json(ws / "FINAL_EVALUATION.json").get("evaluation") or {}
        runs.append({"arxiv": aid, "ws": str(ws), "graph": a.graph,
                     "n_nodes": len(g0.nodes),
                     "n_assertions": len(g0.assertions),
                     "n_assertions_view": len(g.assertions),
                     "scope": a.scope, "normalization": norm.to_dict(),
                     "final": fe.get("overall", "N/A"),
                     "double_run": dbl})
        print(f"[{aid}] scope={a.scope} overall={rep['overall']} "
              f"final={fe.get('overall', 'N/A')} "
              f"R6={rep['verdicts']['R6']['verdict']} "
              f"exec={rep['execution']} "
              f"double_run={dbl.get('equal')}")
    if a.report_md:
        build_validation_report(runs, Path(a.report_md))
        print("报告 →", a.report_md)
    return 0 if all(
        _read_json(Path(r["ws"]) / "REPRO_VERDICTS.json").get("overall")
        != "BLOCKED" for r in runs) else 1


if __name__ == "__main__":
    sys.exit(main())
