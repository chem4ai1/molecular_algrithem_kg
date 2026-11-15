"""Benchmark 派生与 SOTA 榜：把「数据集」升级为「可复现评测基准 + 排行榜」.

现状问题（改造前）：

* ``Dataset`` 只有 ``name`` / ``versionStatus`` / ``sourceEvidenceIds``，
  没有**输入输出结构、研究对象、对应任务与问题**；
* ``MetricObservation`` 的 ``dataset_id`` 全为空（0/41），观测只能经由
  ``EvaluationRun --USES_DATASET--> Dataset`` 间接定位；
* 没有 ``Benchmark`` 与 ``LeaderboardEntry``，因此**无法回答「这个基准上
  当前 SOTA 是多少、谁测的、代码在哪」**。

本模块从现有图**派生**（不重跑、不猜值）：

```
Dataset + DatasetSplit + EvaluationRun + MetricObservation
        └─► Benchmark(name, input/output schema, research_object, problems,
                      metrics, split, tested_by_papers/codes)
                 └─► LeaderboardEntry(benchmark, metric, value, direction,
                                      subject, paper, code, comparability_key)
                          └─► rank + is_sota（按 15 维可比键分组后排序）
```

**诚实性约束**：只有同 ``comparability_key`` 且组内 ≥2 条成绩时，
才允许称「SOTA」；单条成绩标 ``sota_claimable=False``，只表示「唯一的报告值」。
缺失状态（``value is None``）不参与排名。
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..utils import now_iso
from .comparability import comparability_key, compare_observations
from .concepts import Concept
from .store import POGraph

BENCHMARK_PREFIX = "benchmark:"


def _short(x: str) -> str:
    return hashlib.blake2b(str(x).encode("utf-8"), digest_size=8).hexdigest()[:10]


def _suffix(node_id: str) -> str:
    return str(node_id).split(":", 1)[-1]


def _norm_name(label: str) -> str:
    """把自然语言短语规范成可读的基准名（保留原文，去重空白）。"""
    return " ".join(str(label or "").split())[:120] or "unnamed_benchmark"


def _run_papers(graph: POGraph) -> Dict[str, str]:
    """EvaluationRun → paper 节点 id（``source_paper`` 是编号如 "19"）。"""
    out: Dict[str, str] = {}
    for run in graph.by_type("EvaluationRun"):
        raw = str(run.attrs.get("source_paper") or "")
        if not raw:
            continue
        for cand in (raw, f"paper:{raw}", f"paper:{raw.zfill(2)}"):
            if cand in graph.nodes:
                out[run.id] = cand
                break
    return out


def _parse_io(raw: Any) -> Tuple[Any, Any]:
    """``Task.input_output`` 可能是 dict、JSON 字符串或纯文本（报告包三种都有）。"""
    if isinstance(raw, dict):
        return raw.get("inputs"), raw.get("outputs")
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed.get("inputs"), parsed.get("outputs")
        except json.JSONDecodeError:
            pass
        return raw.strip()[:300], None      # 纯文本契约，原样保留
    return None, None


def _task_schema(graph: POGraph, paper_id: str) -> Tuple[Any, Any, str]:
    """从 Paper → ResearchQuestion → Task 取输入/输出契约与任务族。"""
    for e in graph.outgoing(paper_id, "FORMULATES"):
        q = graph.nodes.get(e.target)
        if not q:
            continue
        for e2 in graph.outgoing(q.id, "OPERATIONALIZED_AS"):
            task = graph.nodes.get(e2.target)
            if not task:
                continue
            inputs, outputs = _parse_io(task.attrs.get("input_output"))
            return (inputs, outputs, str(task.attrs.get("task_family") or ""))
    return None, None, ""


def derive_benchmarks(graph: POGraph, *, overwrite: bool = True) -> Dict[str, Any]:
    """Dataset → Benchmark，并补齐输入输出、研究对象、问题、指标与测试者。"""
    stats: Dict[str, Any] = {"benchmarks": 0, "with_schema": 0, "with_object": 0,
                             "with_problems": 0, "with_metrics": 0,
                             "tested_by_papers": 0, "tested_by_codes": 0,
                             "skipped": []}
    run_paper = _run_papers(graph)

    for ds in graph.by_type("Dataset"):
        bid = f"{BENCHMARK_PREFIX}{_suffix(ds.id)}"
        if bid in graph.nodes and not overwrite:
            continue

        # 1) 使用该数据集的评测运行
        runs = [s for s in (e.source for e in graph.incoming(ds.id, "USES_DATASET"))
                if s in graph.nodes and graph.nodes[s].type == "EvaluationRun"]
        metrics: List[str] = []
        papers: List[str] = []
        observations: List[Concept] = []
        for rid in runs:
            for e in graph.outgoing(rid, "USES_METRIC"):
                if e.target not in metrics:
                    metrics.append(e.target)
            pid = run_paper.get(rid)
            if pid and pid not in papers:
                papers.append(pid)
            for e in graph.outgoing(rid, "PRODUCES_OBSERVATION"):
                o = graph.nodes.get(e.target)
                if o is not None and o.type == "MetricObservation":
                    observations.append(o)

        # 2) 切分规则
        splits = [graph.nodes[e.target] for e in graph.outgoing(ds.id, "HAS_SPLIT")
                  if e.target in graph.nodes]
        split_types = [str(s.attrs.get("rule") or "") for s in splits if s.attrs.get("rule")]

        # 3) 输入/输出契约与任务族（取第一个能解析的论文）
        inputs = outputs = None
        task_family = ""
        for pid in papers:
            inputs, outputs, task_family = _task_schema(graph, pid)
            if inputs or outputs or task_family:
                break

        # 4) 研究对象：观测里出现最多的 target / subject
        targets = Counter(str(o.attrs.get("target")) for o in observations
                          if o.attrs.get("target"))
        subjects = Counter(str(o.attrs.get("subject")) for o in observations
                           if o.attrs.get("subject"))
        research_object = (targets.most_common(1)[0][0] if targets
                           else (subjects.most_common(1)[0][0] if subjects else ""))

        # 5) 待解决问题：论文 ADDRESSES 的问题
        problems: List[str] = []
        for pid in papers:
            for e in graph.outgoing(pid, "ADDRESSES"):
                if e.target not in problems:
                    problems.append(e.target)

        # 6) 代码资源
        codes: List[str] = []
        for pid in papers:
            for e in graph.outgoing(pid, "HAS_CODE"):
                if e.target not in codes:
                    codes.append(e.target)

        concept = graph.node(
            bid, "Benchmark", _norm_name(ds.label),
            name=_norm_name(ds.label),
            dataset_id=ds.id,
            version=str(ds.attrs.get("version_status") or "as_described_by_paper"),
            split_type="; ".join(r for r in split_types if r)[:300],
            task_family=task_family or "other",
            input_schema=inputs if inputs else "not_extracted",
            output_schema=outputs if outputs else "not_extracted",
            research_object=research_object or "not_extracted",
            metric_ids=list(metrics),
            problem_ids=list(problems),
            tested_by_papers=list(papers),
            tested_by_codes=list(codes),
            n_observations=len(observations),
            license_status=str(ds.attrs.get("license_status") or "see_dataset"),
            source_evidence_ids=list(ds.attrs.get("source_evidence_ids") or []),
            derived_from=ds.id,
            derivation="deterministic_from_graph",
            derived_at=now_iso(),
        )
        # 边：基准→数据集/指标/问题/代码/论文
        graph.assert_rel(bid, ds.id, "USES_DATASET", attribution="analyst_derived")
        for m in metrics:
            graph.assert_rel(bid, m, "USES_METRIC", attribution="analyst_derived")
        for p in problems:
            graph.assert_rel(bid, p, "BENCHMARK_FOR", attribution="analyst_derived")
        for pid in papers:
            graph.assert_rel(pid, bid, "EVALUATED_ON", attribution="analyst_derived")
        for cid in codes:
            graph.assert_rel(cid, bid, "EVALUATED_ON", attribution="analyst_derived")

        stats["benchmarks"] += 1
        stats["with_schema"] += int(bool(inputs or outputs))
        stats["with_object"] += int(bool(research_object))
        stats["with_problems"] += int(bool(problems))
        stats["with_metrics"] += int(bool(metrics))
        stats["tested_by_papers"] += len(papers)
        stats["tested_by_codes"] += len(codes)
        if not metrics:
            stats["skipped"].append({"benchmark": bid, "reason": "no_evaluation_run"})

    return stats


def _direction(graph: POGraph, obs: Concept) -> str:
    d = str(obs.attrs.get("direction") or "")
    if d:
        return d
    mid = str(obs.attrs.get("metric_definition_id") or "")
    m = graph.nodes.get(mid)
    if m is not None:
        return str(m.attrs.get("direction") or "higher")
    return "higher"


def build_leaderboard(graph: POGraph, *, overwrite: bool = True) -> Dict[str, Any]:
    """MetricObservation → LeaderboardEntry，并按可比键分组排名。"""
    stats: Dict[str, Any] = {"entries": 0, "skipped_missing": 0, "skipped_no_benchmark": 0,
                             "groups": 0, "sota_groups": 0, "single_entry_groups": 0}
    run_paper = _run_papers(graph)

    # EvaluationRun → benchmark（经 USES_DATASET）
    run_bench: Dict[str, str] = {}
    for run in graph.by_type("EvaluationRun"):
        for e in graph.outgoing(run.id, "USES_DATASET"):
            bid = f"{BENCHMARK_PREFIX}{_suffix(e.target)}"
            if bid in graph.nodes:
                run_bench[run.id] = bid
                break

    # 观测 → 所属 run/benchmark
    obs_owner: Dict[str, Tuple[str, str]] = {}
    for rid, bid in run_bench.items():
        for e in graph.outgoing(rid, "PRODUCES_OBSERVATION"):
            obs_owner[e.target] = (bid, rid)

    entries: List[Concept] = []
    for oid, (bid, rid) in obs_owner.items():
        obs = graph.nodes.get(oid)
        if obs is None or obs.attrs.get("value") is None:
            stats["skipped_missing"] += 1
            continue
        metric_id = str(obs.attrs.get("metric_definition_id")
                        or obs.attrs.get("metric") or "")
        direction = _direction(graph, obs)
        # 观测常缺 dataset_id / 结构化 condition：从 benchmark 与 context 文本回填，
        # 否则不同论文、不同数据集、不同实验条件的同名指标会被混进同一榜单。
        ck_input = dict(obs.attrs)
        bench = graph.nodes.get(bid)
        if not ck_input.get("dataset_id") and bench is not None:
            ck_input["dataset_id"] = str(bench.attrs.get("dataset_id") or "")
        if not ck_input.get("condition") and not ck_input.get("condition_hash"):
            ctx = str(obs.attrs.get("context") or "").strip()
            if ctx:
                ck_input["condition"] = {"context": ctx}
        ck = comparability_key(ck_input)
        key = ck.key()                    # 完整 16 维（展示）
        group_key = ck.blocking_key()     # 14 维（分组）
        subject = str(obs.attrs.get("subject") or obs.attrs.get("target")
                      or run_paper.get(rid, ""))
        pid = run_paper.get(rid, "")
        codes = [e.target for e in graph.outgoing(pid, "HAS_CODE")] if pid else []
        eid = f"entry:{_suffix(bid)}:{_short(metric_id)}:{_short(key)}:{_short(subject)}"
        if eid in graph.nodes and not overwrite:
            entries.append(graph.nodes[eid])
            continue
        concept = graph.node(
            eid, "LeaderboardEntry",
            f"{_norm_name(graph.nodes[bid].label)} · {metric_id.split(':')[-1]} · {subject}"[:120],
            benchmark_id=bid,
            metric_id=metric_id,
            value=float(obs.attrs["value"]),
            unit=str(obs.attrs.get("unit") or ""),
            direction=direction,
            subject=subject,
            paper_id=pid,
            code_id=codes[0] if codes else "",
            comparability_key=key,
            group_key=group_key,
            protocol_signature=str(obs.attrs.get("context") or "")[:200],
            modality=str(obs.attrs.get("modality") or ""),
            stage=str(obs.attrs.get("stage") or ""),
            subject_source_observation=oid,
            derived_at=now_iso(),
        )
        graph.assert_rel(bid, eid, "HAS_LEADERBOARD", attribution="analyst_derived")
        graph.assert_rel(eid, oid, "FROM_OBSERVATION", attribution="analyst_derived")
        if pid:
            graph.assert_rel(eid, pid, "REPORTED_BY", attribution="analyst_derived")
        entries.append(concept)
        stats["entries"] += 1

    # 去重：同一 (benchmark, metric, key, subject) 重复观测只保留一个节点，
    # 否则「重复引用」会被误算成同组多条成绩，凭空造出 SOTA。
    uniq: Dict[str, Concept] = {}
    for e in entries:
        uniq[e.id] = e
    entries = list(uniq.values())

    # 分组排名：同 (benchmark, metric, key, direction) 才可比
    groups: Dict[Tuple[str, str, str, str], List[Concept]] = defaultdict(list)
    for e in entries:
        groups[(str(e.attrs.get("benchmark_id")), str(e.attrs.get("metric_id")),
                str(e.attrs.get("group_key")),
                str(e.attrs.get("direction")))].append(e)

    for (_b, _m, _k, direction), items in groups.items():
        items.sort(key=lambda x: float(x.attrs.get("value") or 0),
                   reverse=(direction != "lower"))
        claimable = len(items) >= 2
        for i, it in enumerate(items):
            it.attrs["rank"] = i + 1
            it.attrs["is_sota"] = bool(i == 0 and claimable)
            it.attrs["sota_claimable"] = claimable
            it.attrs["group_size"] = len(items)
        stats["groups"] += 1
        stats["sota_groups"] += int(claimable)
        stats["single_entry_groups"] += int(not claimable)
    return stats


def sota_report(graph: POGraph, *, only_claimable: bool = False) -> Dict[str, Any]:
    """输出分组 SOTA 表（诚实标注「唯一报告值」与「SOTA」的区别）。"""
    groups: Dict[Tuple[str, str, str, str], List[Concept]] = defaultdict(list)
    for e in graph.by_type("LeaderboardEntry"):
        groups[(str(e.attrs.get("benchmark_id")), str(e.attrs.get("metric_id")),
                str(e.attrs.get("group_key")),
                str(e.attrs.get("direction")))].append(e)

    rows: List[Dict[str, Any]] = []
    for (bid, mid, key, direction), items in groups.items():
        items.sort(key=lambda x: float(x.attrs.get("value") or 0),
                   reverse=(direction != "lower"))
        best = items[0]
        claimable = len(items) >= 2
        if only_claimable and not claimable:
            continue
        rows.append({
            "benchmark": bid,
            "benchmark_name": (graph.nodes[bid].label if bid in graph.nodes else ""),
            "metric": mid.split(":")[-1] or mid,
            "direction": direction,
            "comparability_key": key,
            "group_size": len(items),
            "sota_claimable": claimable,
            "sota": {
                "value": best.attrs.get("value"),
                "unit": best.attrs.get("unit"),
                "subject": best.attrs.get("subject"),
                "paper": best.attrs.get("paper_id"),
                "code": best.attrs.get("code_id"),
                "stage": best.attrs.get("stage"),
                "modality": best.attrs.get("modality"),
                "entry": best.id,
            },
            "runners_up": [{"value": x.attrs.get("value"),
                            "subject": x.attrs.get("subject"),
                            "paper": x.attrs.get("paper_id")} for x in items[1:4]],
            "caveat": ("" if claimable else
                       "仅一条可比成绩，只能称「唯一报告值」，不构成 SOTA 比较"),
        })
    rows.sort(key=lambda r: (-r["group_size"], r["benchmark"], r["metric"]))
    return {
        "n_groups": len(rows),
        "n_claimable": sum(1 for r in rows if r["sota_claimable"]),
        "n_single": sum(1 for r in rows if not r["sota_claimable"]),
        "groups": rows,
        "note": ("SOTA 只在同一 15 维可比键内成立；跨预算/阶段/阈值/条件的数值"
                 "不可直接比较，故不进入同一榜单。"),
    }


def purge_derived(graph: POGraph) -> int:
    """删除全部派生的 Benchmark / LeaderboardEntry 及其边（幂等重建用）。"""
    ids = {n.id for n in graph.by_type("Benchmark")} | \
          {n.id for n in graph.by_type("LeaderboardEntry")}
    if not ids:
        return 0
    for i in list(ids):
        graph.nodes.pop(i, None)
    graph.assertions[:] = [a for a in graph.assertions
                           if a.source not in ids and a.target not in ids]
    return len(ids)


def apply_all(graph: POGraph, *, overwrite: bool = True) -> Dict[str, Any]:
    """一站式：清理旧派生 → 派生基准 → 建榜 → 输出 SOTA 摘要。"""
    purged = purge_derived(graph) if overwrite else 0
    b = derive_benchmarks(graph, overwrite=overwrite)
    l = build_leaderboard(graph, overwrite=overwrite)
    s = sota_report(graph)
    graph.meta["benchmark"] = {"purged": purged, "derive": b, "leaderboard": l,
                               "sota_groups": s["n_groups"],
                               "sota_claimable": s["n_claimable"],
                               "applied_at": now_iso()}
    return {"derive": b, "leaderboard": l,
            "sota": {"n_groups": s["n_groups"],
                     "n_claimable": s["n_claimable"],
                     "n_single": s["n_single"]},
            "n_benchmarks": len(graph.by_type("Benchmark")),
            "n_entries": len(graph.by_type("LeaderboardEntry"))}


def to_markdown(sota: Dict[str, Any], *, top_k: int = 30) -> str:
    lines = ["# 基准与 SOTA 榜（按 15 维可比键分组）", "",
             f"- 可比组：{sota['n_groups']}（可称 SOTA {sota['n_claimable']}，"
             f"单条报告值 {sota['n_single']}）", "",
             "| 基准 | 指标 | 方向 | 组内条数 | SOTA 值 | 方法/对象 | 论文 | 代码 | 可称 SOTA |",
             "|---|---|---|---:|---|---|---|---|---|"]
    for r in sota["groups"][:top_k]:
        s = r["sota"]
        lines.append(
            f"| {r['benchmark_name'] or r['benchmark']} | {r['metric']} | {r['direction']} | "
            f"{r['group_size']} | {s['value']} {s['unit'] or ''} | {str(s['subject'])[:28]} | "
            f"{s['paper'] or '-'} | {s['code'] or '-'} | {'是' if r['sota_claimable'] else '否'} |")
    lines += ["", f"> {sota['note']}"]
    return "\n".join(lines)


def main() -> int:
    import argparse
    import json
    from pathlib import Path

    ap = argparse.ArgumentParser(description="从 PO 图派生 Benchmark 与 SOTA 榜")
    ap.add_argument("--graph", default="storage_cf/po/report_graph.json")
    ap.add_argument("--out", default="")
    ap.add_argument("--markdown", default="")
    a = ap.parse_args()

    g = POGraph.load(a.graph)
    stats = apply_all(g)
    if a.out:
        g.save(a.out)
    sota = sota_report(g)
    if a.markdown:
        Path(a.markdown).write_text(to_markdown(sota), encoding="utf-8")
    print(json.dumps({**stats, "graph_path": a.out or a.graph,
                      "validation_problems": len(g.validate())},
                     ensure_ascii=False, indent=2)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
