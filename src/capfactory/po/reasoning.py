"""确定性推理、缺口发现、统计与总结（不依赖 LLM）.

LLM 负责「读文本、下判断」，本模块负责「可复算的事实」：
推理规则 R1–R10（见 ``semantics.INFERENCE_RULES``）、覆盖矩阵、缺口排序。
这样 LLM 的输出可以被确定性校验器接住，避免「模型说缺、其实图里有」。

适配两种图：
- ``POGraph``：``nodes: Dict[str, Concept]`` + ``assertions: List[Assertion]``；
- ``KnowledgeGraph``：``nodes: Dict[str, dict]`` + ``edges: List[dict]``。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .comparability import compare_observations
from .concepts import CONCEPT_SPECS, DIMENSIONS
from .semantics import CONCEPT_SEMANTICS
from .taxonomy import ALGO_NAMES, DOMAIN_NAMES, taxonomy_matrix
from .vocab import default_registry

GAP_TYPES = {
    "no_implementation": ("高", "论文声称的能力没有对应代码/算法实现"),
    "problem_unaddressed": ("高", "P01–P11 中某子问题没有任何论文尝试处理"),
    "no_evaluation": ("中", "能力主张没有任何评测记录"),
    "no_evidence": ("中", "节点/断言缺少证据定位"),
    "metric_not_measured": ("中", "指标仅有 not_measured/not_reported 观测"),
    "domain_coverage_gap": ("中", "某领域没有任何论文"),
    "algo_coverage_gap": ("低", "某算法族没有任何论文使用"),
    "no_code": ("低", "论文没有公开代码资源"),
    "shared_platform_not_independent": ("低", "多篇论文共享平台/数据，不构成独立复现"),
}


# ---------------------------------------------------------------------------
# 适配层
# ---------------------------------------------------------------------------
def _nodes(g: Any) -> List[Any]:
    return list(g.nodes.values()) if isinstance(g.nodes, dict) else list(g.nodes)


def _edges(g: Any) -> List[Any]:
    return list(getattr(g, "assertions", None) or getattr(g, "edges", []) or [])


def _type(n: Any) -> str:
    return n.type if hasattr(n, "type") else str(n.get("type", ""))


def _id(n: Any) -> str:
    return n.id if hasattr(n, "id") else str(n.get("id", ""))


def _label(n: Any) -> str:
    return getattr(n, "label", "") if hasattr(n, "label") else str(n.get("label", ""))


def _attrs(n: Any) -> Dict[str, Any]:
    return dict(n.attrs) if hasattr(n, "attrs") else dict(n.get("attrs") or {})


def _rel(e: Any) -> str:
    return getattr(e, "relation", "") if hasattr(e, "relation") else str(e.get("type", ""))


def _src(e: Any) -> str:
    return getattr(e, "source", "") if hasattr(e, "source") else str(e.get("source", ""))


def _tgt(e: Any) -> str:
    return getattr(e, "target", "") if hasattr(e, "target") else str(e.get("target", ""))


def _by_type(g: Any, t: str) -> List[Any]:
    return [n for n in _nodes(g) if _type(n) == t]


def _papers(g: Any) -> List[Any]:
    """PO 用 ``Paper``，主图用 ``paper``。"""
    return _by_type(g, "Paper") or _by_type(g, "paper")


def _claims(g: Any) -> List[Any]:
    return _by_type(g, "CapabilityClaim") or _by_type(g, "capability")


# ---------------------------------------------------------------------------
# 推理
# ---------------------------------------------------------------------------
def infer(g: Any) -> Dict[str, Any]:
    """执行确定性推理，返回新增结论与可解释依据。"""
    idx = {_id(n): n for n in _nodes(g)}
    out: Dict[str, Any] = {"inferred": [], "comparable_groups": [],
                           "transitive_broader": [], "shared_families": [],
                           "stats": {}}

    # R1/R2：领域与算法族继承到能力主张
    for paper in _by_type(g, "Paper"):
        doms = _attrs(paper).get("domain_codes", [])
        algos = _attrs(paper).get("algo_codes", [])
        for e in _edges(g):
            if _rel(e) == "HAS_CLAIM" and _src(e) == _id(paper) and _tgt(e) in idx:
                claim = idx[_tgt(e)]
                ca = claim.attrs if hasattr(claim, "attrs") else claim.setdefault("attrs", {})
                for d in doms:
                    if d not in ca.setdefault("domain_codes", []):
                        ca["domain_codes"].append(d)
                        out["inferred"].append({"rule": "R1", "node": _id(claim),
                                                "statement": f"继承领域 {d}（来自 {_id(paper)}）"})
                for a in algos:
                    if a not in ca.setdefault("algo_codes", []):
                        ca["algo_codes"].append(a)
                        out["inferred"].append({"rule": "R2", "node": _id(claim),
                                                "statement": f"继承算法族 {a}（来自 {_id(paper)}）"})

    # R4：BROADER 传递闭包
    parent: Dict[str, str] = {}
    for e in _edges(g):
        if _rel(e) == "BROADER" and _tgt(e) in idx:
            parent[_src(e)] = _tgt(e)

    def root(x: str, guard: int = 0) -> str:
        while x in parent and guard < 16:
            x = parent[x]
            guard += 1
        return x

    for pid in list(parent):
        r = root(pid)
        if r != parent.get(pid):
            out["transitive_broader"].append({"problem": pid, "root_category": r})

    # R5：可比性分组（15 维键相同才可同组）
    groups: Dict[str, List[Any]] = defaultdict(list)
    for o in _by_type(g, "MetricObservation"):
        a = _attrs(o)
        key = a.get("comparability_key") or compare_observations(a, a)["key_a"]
        groups[key].append(o)
    conflicts = 0
    for key, obs in groups.items():
        if len(obs) > 1:
            for i, x in enumerate(obs):
                for y in obs[i + 1:]:
                    if not compare_observations(_attrs(x), _attrs(y))["comparable"]:
                        conflicts += 1
    out["comparable_groups"] = [
        {"key": k, "size": len(v), "metrics": sorted({_attrs(n).get("metric", "") for n in v})}
        for k, v in groups.items() if len(v) > 1][:20]
    out["stats"]["comparable_groups"] = len([v for v in groups.values() if len(v) > 1])
    out["stats"]["cross_group_conflicts"] = conflicts
    # 同名指标但可比键不同 → 不可横排（报告 CQ3）
    by_metric: Dict[str, List[Any]] = defaultdict(list)
    for o in _by_type(g, "MetricObservation"):
        by_metric[str(_attrs(o).get("metric") or _label(o))].append(o)
    incomparable = 0
    for _m, obs in by_metric.items():
        for i, x in enumerate(obs):
            for y in obs[i + 1:]:
                if not compare_observations(_attrs(x), _attrs(y))["comparable"]:
                    incomparable += 1
    out["stats"]["incomparable_pairs"] = incomparable

    # R10：共享平台
    for fam in _by_type(g, "EvidenceFamily"):
        members = [_src(e) for e in _edges(g)
                   if _rel(e) == "MEMBER_OF" and _tgt(e) == _id(fam)]
        if members:
            out["shared_families"].append({
                "family": _id(fam), "label": _label(fam),
                "basis": _attrs(fam).get("basis", ""),
                "independence": _attrs(fam).get("independence_status", ""),
                "members": members,
                "note": "共享平台/数据不构成多次独立复现"})

    out["stats"]["inferred"] = len(out["inferred"])
    out["stats"]["transitive_broader"] = len(out["transitive_broader"])
    out["stats"]["shared_families"] = len(out["shared_families"])
    return out


# ---------------------------------------------------------------------------
# 缺口发现
# ---------------------------------------------------------------------------
def discover_gaps(g: Any, *, top_k: int = 30) -> Dict[str, Any]:
    """按 R6–R10 + 结构覆盖发现缺口，带严重度与建议动作。"""
    gaps: List[Dict[str, Any]] = []
    nodes = _nodes(g)
    edges = _edges(g)
    idx = {_id(n): n for n in nodes}

    def add(gtype: str, obj: str, severity: str, evidence: Sequence[str],
            rationale: str, action: str) -> None:
        gaps.append({"type": gtype, "object": obj, "severity": severity,
                     "evidence": list(evidence)[:6], "rationale": rationale,
                     "suggested_action": action})

    # R6：领域 / 算法族空覆盖
    used_dom: Counter = Counter()
    used_algo: Counter = Counter()
    for n in nodes:
        a = _attrs(n)
        for d in a.get("domain_codes", []) or []:
            used_dom[d] += 1
        for c in a.get("algo_codes", []) or []:
            used_algo[c] += 1
    for code, name in DOMAIN_NAMES.items():
        if code == "D0":
            continue
        if used_dom.get(code, 0) == 0:
            add("domain_coverage_gap", f"{code} {name}", "中", [],
                "该领域没有任何论文/能力节点", "补充该领域的代表工作或标注遗漏的论文")
    for code, name in ALGO_NAMES.items():
        if used_algo.get(code, 0) == 0:
            add("algo_coverage_gap", f"{code} {name}", "低", [],
                "该算法族没有被任何论文使用", "确认是否为真空白，或补标使用该族的论文")

    # R7：论文宣称但缺实现/评测/证据
    paper_has_code = {_src(e) for e in edges if _rel(e) == "HAS_CODE"}
    claim_paper = {_tgt(e): _src(e) for e in edges if _rel(e) == "HAS_CLAIM"}
    algo_implemented = {_tgt(e) for e in edges
                        if _rel(e) in ("HAS_CODE", "IMPLEMENTS")}
    has_eval = {_src(e) for e in edges if _rel(e) in ("EVALUATED_IN", "PRODUCES_OBSERVATION")}
    has_support = {_src(e) for e in edges if _rel(e) == "SUPPORTED_BY"}
    for claim in _claims(g):
        cid = _id(claim)
        pid = claim_paper.get(cid, "")
        methods = {_tgt(e) for e in edges
                   if _rel(e) == "ABOUT_METHOD" and _src(e) == cid}
        implemented = bool(pid and pid in paper_has_code) or bool(methods & algo_implemented)
        if not implemented:
            add("no_implementation", _label(claim) or cid, "高", [cid] + ([pid] if pid else []),
                "能力主张既无公开代码、也无已实现算法指向", "补齐实现或把该主张标为「论文声称未实现」")
        if cid not in has_eval:
            add("no_evaluation", _label(claim) or cid, "中", [cid],
                "能力主张没有评测记录", "补充评测记录或下调证据等级")
        if cid not in has_support:
            add("no_evidence", _label(claim) or cid, "中", [cid],
                "能力主张没有证据定位", "补充 Evidence 与版本定位")

    # R8：指标未测/未报告
    missing_by_metric: Dict[str, List[str]] = defaultdict(list)
    measured: Set[str] = set()
    for o in _by_type(g, "MetricObservation"):
        a = _attrs(o)
        metric = str(a.get("metric") or _label(o))
        if a.get("value") is None:
            missing_by_metric[metric].append(_id(o))
        else:
            measured.add(metric)
    for metric, obs in missing_by_metric.items():
        if metric not in measured:
            add("metric_not_measured", metric, "中", obs,
                f"{len(obs)} 条观测均为缺失状态，指标不可比较",
                "补充实测值，或在结论中排除该指标")

    # 问题未覆盖
    addressed = {_tgt(e) for e in edges
                 if _rel(e) in ("ADDRESSES", "ANALYST_RELEVANT_TO", "EXPOSES_LIMITATION")}
    for p in _by_type(g, "ResearchProblem"):
        if _id(p) not in addressed:
            add("problem_unaddressed", f"{_id(p)} {_label(p)}", "高", [_id(p)],
                "没有任何论文关联该子问题", "补充文献或把该问题标为开放缺口")

    # 无代码
    papers_with_code = {_src(e) for e in edges if _rel(e) == "HAS_CODE"}
    for paper in _papers(g):
        if _id(paper) not in papers_with_code:
            add("no_code", _label(paper) or _id(paper), "低", [_id(paper)],
                "论文没有公开代码资源", "标注 closed_commercial / 未公开，或寻找替代实现")

    # R10：共享平台提示
    for fam in _by_type(g, "EvidenceFamily"):
        members = [_src(e) for e in edges
                   if _rel(e) == "MEMBER_OF" and _tgt(e) == _id(fam)]
        if len(members) >= 2:
            add("shared_platform_not_independent", _label(fam) or _id(fam), "低", members,
                f"{len(members)} 篇论文共享同一平台/数据，不能算独立复现",
                "在比较与结论中降权，避免重复计数")

    order = {"高": 0, "中": 1, "低": 2}
    gaps.sort(key=lambda x: (order.get(x["severity"], 9), x["type"], x["object"]))
    counts = Counter(x["type"] for x in gaps)
    sev = Counter(x["severity"] for x in gaps)
    return {
        "gaps": gaps[:top_k],
        "n_gaps": len(gaps),
        "by_type": dict(counts),
        "by_severity": dict(sev),
        "gap_type_catalog": {k: {"severity": v[0], "definition": v[1]}
                             for k, v in GAP_TYPES.items()},
        "note": ("缺口依据图结构计算；「未抽取」不同于「不存在」，"
                 "详见 semantics.TASK_PROTOCOLS.gap_discovery"),
    }


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------
def stats_report(g: Any) -> Dict[str, Any]:
    """按类型 / 维度 / 领域 / 算法族统计节点与边。"""
    nodes = _nodes(g)
    edges = _edges(g)
    by_type = Counter(_type(n) for n in nodes)
    by_rel = Counter(_rel(e) for e in edges)
    by_dim: Counter = Counter()
    for n in nodes:
        spec = CONCEPT_SPECS.get(_type(n))
        by_dim[spec.dimension if spec else "other"] += 1

    dom: Counter = Counter()
    algo: Counter = Counter()
    for n in nodes:
        a = _attrs(n)
        for d in a.get("domain_codes", []) or []:
            dom[d] += 1
        for c in a.get("algo_codes", []) or []:
            algo[c] += 1

    measured = sum(1 for o in _by_type(g, "MetricObservation")
                   if _attrs(o).get("value") is not None)
    n_obs = len(_by_type(g, "MetricObservation"))
    evidence = len(_by_type(g, "Evidence"))
    papers = len(_by_type(g, "Paper")) or len(_by_type(g, "paper"))
    caps = len(_by_type(g, "CapabilityClaim")) or len(_by_type(g, "capability"))
    code = len(_by_type(g, "CodeArtifact"))
    dataset = len(_by_type(g, "Dataset")) or len(_by_type(g, "dataset"))
    algo_nodes = len(_by_type(g, "Algorithm"))

    problems = []
    if hasattr(g, "validate"):
        problems = g.validate()

    return {
        "totals": {"nodes": len(nodes), "edges": len(edges),
                   "papers": papers, "capabilities": caps, "algorithms": algo_nodes,
                   "datasets": dataset, "code_artifacts": code,
                   "evidence": evidence, "observations": n_obs,
                   "measured_observations": measured,
                   "measurement_rate": round(measured / n_obs, 4) if n_obs else 0.0},
        "by_type": dict(by_type),
        "by_relation": dict(by_rel),
        "by_dimension": dict(by_dim),
        "domains": {k: {"name": DOMAIN_NAMES.get(k, k), "count": v}
                    for k, v in sorted(dom.items(), key=lambda kv: -kv[1])},
        "algorithms": {k: {"name": ALGO_NAMES.get(k, k), "count": v}
                       for k, v in sorted(algo.items(), key=lambda kv: -kv[1])},
        "domain_algorithm_matrix": (taxonomy_matrix(g) if hasattr(g, "by_type")
                                    and _by_type(g, "Paper") else {}),
        "validation_problems": len(problems),
        "schema_coverage": {
            "declared_classes": len(CONCEPT_SPECS),
            "instantiated_classes": len([t for t in by_type
                                         if t in CONCEPT_SPECS and by_type[t] > 0]),
            "instantiated": sorted(t for t in by_type
                                   if t in CONCEPT_SPECS and by_type[t] > 0),
            "empty_classes": sorted(t for t in CONCEPT_SPECS if not by_type.get(t)),
        },
    }


# ---------------------------------------------------------------------------
# 总结
# ---------------------------------------------------------------------------
def summarize(g: Any, *, scope: str = "all", top_k: int = 8) -> Dict[str, Any]:
    """生成结构化摘要 + Markdown（数字全部来自 stats，不做估计）。"""
    stats = stats_report(g)
    gaps = discover_gaps(g, top_k=top_k)
    inf = infer(g)
    t = stats["totals"]

    headline = (f"共 {t['nodes']} 个节点 / {t['edges']} 条断言；"
                f"{t['papers']} 篇论文、{t['capabilities']} 条能力主张、"
                f"{t['algorithms']} 个算法、{t['datasets']} 个数据集、"
                f"{t['code_artifacts']} 个代码资源；"
                f"{t['evidence']} 条证据、{t['observations']} 条指标观测"
                f"（实测 {t['measured_observations']} 条）")

    top_dom = list(stats["domains"].items())[:5]
    top_algo = list(stats["algorithms"].items())[:5]
    lines = [f"# PO 图摘要（scope={scope}）", "", headline, "",
             "## 领域分布", ""]
    lines += [f"- {k} {v['name']}：{v['count']} 个节点" for k, v in top_dom]
    lines += ["", "## 算法族分布", ""]
    lines += [f"- {k} {v['name']}：{v['count']} 个节点" for k, v in top_algo]
    lines += ["", "## 覆盖与质量", "",
              f"- 已实例化概念类：{stats['schema_coverage']['instantiated_classes']}"
              f" / {stats['schema_coverage']['declared_classes']}",
              f"- 结构校验问题：{stats['validation_problems']}",
              f"- 指标实测率：{t['measurement_rate']:.1%}"]
    lines += ["", "## 主要缺口", ""]
    for x in gaps["gaps"][:top_k]:
        lines.append(f"- [{x['severity']}] {x['type']}：{x['object']}"
                     f"（{x['rationale']}）")
    lines += ["", "## 推理结论", "",
              f"- 继承新增结论 {inf['stats'].get('inferred', 0)} 条",
              f"- 可比分组 {inf['stats'].get('comparable_groups', 0)} 组，"
              f"跨组冲突 {inf['stats'].get('cross_group_conflicts', 0)} 对",
              f"- 共享平台家族 {inf['stats'].get('shared_families', 0)} 个（不构成独立复现）"]
    lines += ["", "> 边界：未抽取 ≠ 不存在；结构校验通过 ≠ 生物学结论成立。"]

    return {
        "scope": scope,
        "headline": headline,
        "stats": stats,
        "gaps": gaps,
        "inferences": inf,
        "markdown": "\n".join(lines),
        "caveats": ["未抽取不等于不存在", "作者报告值不等于独立复现",
                    "结构校验通过不等于科学结论成立", "共享平台不计独立验证"],
    }
