"""P0-3：从 reserved 升级 8 类复现运行时应用节点（GGR 蓝图 §3.4 / §9.2）。

**为什么不直接改 applayer/tbox.py**：
``tests/test_layered_tbox.py:107-108`` 锁定应用层基础契约 ``8 类 / 9 关系``，
``tests/Phase/test_graph_slice.py:248`` 与 ``test_layered_tbox.py:178-179`` 锁定
legacy ``46 类 / 105 关系``。把新类塞进这两处会让 798 项回归立刻退化。

因此采用**扩展声明 + 独立运行时图**：
  1. 本模块定义 8 类（带 fields / derived_from / miner / source），并在
     ``applayer/tasks.py`` 的 reproduction TaskSpec 里声明为允许类；
  2. 4 条新关系定义在 ``reprospec/relations.py`` 的 ``REPRO_APP_RELATIONS``；
  3. 运行时节点**只写** ``<out_dir>/app_repro_runtime.json``，
     不写 ``app_reproduction.json``、不写语义层图、不改页面默认快照；
  4. 每个节点带 ``layer="application"`` / ``task="reproduction"`` /
     ``derived_from`` / ``miner="repro_runtime"`` / ``run_id``。

8 类与文献对照：MethodLock(SciForge) / CodeGenerationTask(PaperCoder) /
StaticCheck(PaperCoder/SUPER) / CompileReport(CORE-Bench) /
ExperimentNode(SciForge S2) / ReproductionResult(AutoReproduce) /
EvaluationResult(SA-Bench/PaperBench) / ClaimAnchor(SciForge result-to-claim)。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .relations import REPRO_APP_RELATIONS, APP_RELATIONS

# ---------------------------------------------------------------------------
# 8 类升级清单：name -> (说明, 字段元组, 来源)
# ---------------------------------------------------------------------------
REPRO_APP_CLASSES: Dict[str, Dict[str, Any]] = {
    "RubricNode": {
        "desc": "层次化 rubric 树节点（branch=方法/模块/基准分支，leaf=逐条 SAU）",
        "fields": ("path", "depth", "parent_id", "node_role",
                   "n_leaves", "score", "sau_id", "kind"),
        "source": "rubric_tree", "reserved": False,
    },
    "MethodLock": {
        "desc": "冻结方法 SAU 规格，结果出来后不得改",
        "fields": ("spec_hash", "method_sau_hash", "n_method_sau", "locked"),
        "source": "spec", "reserved": True,
    },
    "CodeGenerationTask": {
        "desc": "依赖有序的代码生成任务（PaperCoder planning）",
        "fields": ("module_id", "order", "strategy", "status"),
        "source": "runtime", "reserved": True,
    },
    "StaticCheck": {
        "desc": "语法 / import / 依赖 / stub 静态检查",
        "fields": ("checks", "n_pass", "n_fail", "status"),
        "source": "runtime", "reserved": True,
    },
    "CompileReport": {
        "desc": "环境安装与 smoke 结果（CORE-Bench / SUPER）",
        "fields": ("compiled", "reason", "duration_s", "effort"),
        "source": "runtime", "reserved": True,
    },
    "ExperimentNode": {
        "desc": "一次 toy/subset/full 实验运行（SciForge S2 ladder）",
        "fields": ("stage", "executed", "seed", "duration_s"),
        "source": "runtime", "reserved": True,
    },
    "ReproductionResult": {
        "desc": "实跑数值；dry 模式 value=None 且 unverified=True",
        "fields": ("metric", "value", "unit", "unverified"),
        "source": "runtime", "reserved": True,
    },
    "EvaluationResult": {
        # 诚实标注：legacy reserved 里只有 EvaluationRun / ReviewVerdict，
        # 没有「逐 SAU 判定」这一语义，因此本类是应用层新增而非升级。
        "desc": "逐类 SAU 的判定汇总（SA-Bench / PaperBench rubric）",
        "fields": ("sau_kind", "n_aligned", "n_mismatch", "n_stub",
                   "n_absent", "n_unverified", "score"),
        "source": "runtime", "reserved": False,
        "legacy_counterpart": "EvaluationRun / ReviewVerdict",
    },
    "ClaimAnchor": {
        "desc": "code_sha / inputs_sha / outputs_sha 三哈希锚",
        "fields": ("code_sha", "inputs_sha", "outputs_sha", "spec_hash"),
        "source": "runtime", "reserved": True,
    },
}

# 有效复现任务契约 = 应用层基础 8 类 / 9 关系 + 升级 8 类 / 4 关系
EFFECTIVE_CLASSES: frozenset = frozenset(
    {"ResearchQuestion", "ProblemCategory", "MetricDefinition",
     "LeaderboardEntry", "DataContract", "Evidence", "Limitation",
     "SourcePaper"} | set(REPRO_APP_CLASSES))
EFFECTIVE_RELATIONS: frozenset = frozenset(
    set(APP_RELATIONS) | set(REPRO_APP_RELATIONS))


def snapshot() -> Dict[str, Any]:
    return {
        "n_upgraded_classes": len(REPRO_APP_CLASSES),
        "upgraded_classes": sorted(REPRO_APP_CLASSES),
        "n_upgraded_relations": len(REPRO_APP_RELATIONS),
        "upgraded_relations": sorted(REPRO_APP_RELATIONS),
        "n_effective_classes": len(EFFECTIVE_CLASSES),
        "n_effective_relations": len(EFFECTIVE_RELATIONS),
        "base_app_contract": "8 classes / 9 relations (unchanged)",
        "output": "<out_dir>/app_repro_runtime.json",
    }


def reserved_status() -> Dict[str, Any]:
    """核对 8 类与 legacy reserved 的关系（防止把新增类伪装成升级）。

    实测：7 类在 reserved 中；``EvaluationResult``（SA-Bench 逐 SAU 判定）与
    ``RubricNode``（层次化 rubric 树）都是**应用层新增类**，如实单独列出。
    """
    from capfactory.ontology.tbox import RESERVED_CLASSES
    have = set(REPRO_APP_CLASSES)
    in_res = sorted(have & set(RESERVED_CLASSES))
    new_cls = sorted(have - set(RESERVED_CLASSES))
    return {
        "n_requested": len(have),
        "n_upgraded_from_reserved": len(in_res),
        "n_new_application_classes": len(new_cls),
        "in_reserved": in_res,
        "not_in_reserved": new_cls,
        "declared_new": sorted(k for k, v in REPRO_APP_CLASSES.items()
                               if not v.get("reserved", True)),
        "n_reserved_total": len(RESERVED_CLASSES),
    }


def validate_repro_edge(src_type: str, rel: str,
                        dst_type: str) -> List[str]:
    """应用层自己的 domain/range 判定（不依赖 legacy TBox）。

    返回问题描述列表，空 = 合法。新关系只在 ``REPRO_APP_RELATIONS`` 中判定；
    既有关系交给 ``applayer.tbox`` / ``semantic.tbox_v4``。
    """
    if rel not in REPRO_APP_RELATIONS:
        return [f"unknown_repro_relation:{rel}"]
    dom, rng, _ = REPRO_APP_RELATIONS[rel]
    bad: List[str] = []
    if src_type not in dom.split("|"):
        bad.append(f"domain: {src_type} not in {dom}")
    if dst_type not in rng.split("|"):
        bad.append(f"range: {dst_type} not in {rng}")
    return bad


def _sha(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
        .encode("utf-8")).hexdigest()[:24]


def materialize_runtime_nodes(
        spec: Any, sau_report: Any, *, run_id: str,
        graph: Any = None, out_dir: Optional[str | Path] = None,
        results: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """把复现运行时节点写进**独立图**，返回统计。

    不修改传入的 ``graph``，不写 ``app_reproduction.json`` 或语义层图。

    参数
        spec       : ReproSpec（P0-2）
        sau_report : SAUReport（P0-4，可为 None）
        run_id     : 本次 run 标识，用于节点 id 前缀
        graph      : 可选的锚点图（只复制被引用的节点作为溯源锚）
        out_dir    : 给出时保存 ``app_repro_runtime.json``
        results    : 实跑结果（dry 为 None）
    """
    from capfactory.po import POGraph

    g = POGraph(f"repro_runtime::{run_id}")
    by_type: Dict[str, int] = {}

    def add(nid: str, typ: str, label: str, *, derived: List[str],
            **attrs: Any) -> str:
        if typ not in REPRO_APP_CLASSES or nid in g.nodes:
            return nid
        g.node(nid, typ, label,
               layer="application", task="reproduction",
               derived_from=derived, miner="repro_runtime",
               run_id=run_id, **attrs)
        by_type[typ] = by_type.get(typ, 0) + 1
        return nid

    def rel(s: str, r: str, t: str, **props: Any) -> bool:
        if s not in g.nodes or t not in g.nodes:
            return False
        st, tt = g.nodes[s].type, g.nodes[t].type
        if validate_repro_edge(st, r, tt):
            return False
        return bool(g.assert_rel(s, t, r, layer="application",
                                 task="reproduction", **props))

    # **先**复制被引用的锚点节点（否则后面 4 条关系两端不齐，边会被静默丢弃）。
    # 只复制 spec 引用到的几十个节点，不复制整张 8300 节点图。
    anchor_ids: Set[str] = {spec.paper_id}
    anchor_ids.update((spec.code_plan or {}).get("order") or [])
    for s in spec.sau:
        anchor_ids.update(s.source_node_ids)
    if graph is not None:
        src_nodes = getattr(graph, "nodes", {}) or {}
        for nid in sorted(anchor_ids):
            n = src_nodes.get(nid)
            if n is not None and nid not in g.nodes:
                a = {k: v for k, v in (getattr(n, "attrs", {}) or {}).items()
                     if k != "label"}
                a.setdefault("layer", "semantic")
                g.node(n.id, n.type, n.label, **a)

    rid = "".join(c if c.isalnum() or c in "-_" else "" for c in run_id)
    prefix = f"reprorun:{rid}"

    # 1) MethodLock
    lock_id = add(f"{prefix}:methodlock", "MethodLock", "方法规格锁",
                  derived=[spec.paper_id],
                  spec_hash=spec.spec_hash,
                  method_sau_hash=spec.method_lock.get("method_sau_hash"),
                  n_method_sau=spec.method_lock.get("n_method_sau", 0),
                  locked=True)

    # 2) CodeGenerationTask（每个模块一条，带顺序）
    order = (spec.code_plan or {}).get("order") or []
    task_ids: List[str] = []
    for i, mod in enumerate(order):
        tid = add(f"{prefix}:codetask:{i:03d}", "CodeGenerationTask",
                  f"代码任务 {i + 1}", derived=[mod],
                  module_id=mod, order=i,
                  strategy=(spec.code_plan or {}).get("strategy", ""),
                  status="planned")
        task_ids.append(tid)
        rel(tid, "GENERATED_BY", mod)

    # 3) StaticCheck（汇总 SAU 静态判定）
    verdicts = getattr(sau_report, "verdicts", None) or []
    static_n = sum(1 for v in verdicts if v.get("verdict") != "unverified")
    chk_id = add(f"{prefix}:staticcheck", "StaticCheck", "静态检查汇总",
                 derived=[spec.paper_id],
                 checks={"n_checked": static_n,
                         "n_total": len(verdicts)},
                 n_pass=sum(1 for v in verdicts
                            if v.get("verdict") == "aligned"),
                 n_fail=sum(1 for v in verdicts
                            if v.get("verdict") in ("mismatch", "stub", "absent")),
                 status="dry_static" if results is None else "executed")

    # 4) CompileReport / 5) ExperimentNode / 6) ReproductionResult
    cp_id = add(f"{prefix}:compile", "CompileReport", "编译与环境报告",
                derived=[spec.paper_id],
                compiled=bool(results), reason="dry_no_execution"
                if results is None else "executed", duration_s=None,
                effort=(spec.budgets or {}).get("effort", "dry"))
    en_id = add(f"{prefix}:experiment", "ExperimentNode", "实验运行节点",
                derived=[spec.paper_id], stage="dry" if results is None
                else "full", executed=bool(results), seed=None,
                duration_s=None)
    rr_id = add(f"{prefix}:result", "ReproductionResult", "复现数值",
                derived=[spec.paper_id], metric="", value=None, unit="",
                unverified=results is None)

    # 7) EvaluationResult：每类 SAU 一条汇总
    counts = getattr(sau_report, "counts", None) or {}
    for kind in ("method", "code_grounding", "protocol", "numeric", "ordering"):
        c = counts.get(kind, {}) if isinstance(counts, dict) else {}
        ev_id = add(f"{prefix}:eval:{kind}", "EvaluationResult",
                    f"SAU 判定 · {kind}", derived=[spec.paper_id],
                    sau_kind=kind,
                    n_aligned=c.get("aligned", 0),
                    n_mismatch=c.get("mismatch", 0),
                    n_stub=c.get("stub", 0), n_absent=c.get("absent", 0),
                    n_unverified=c.get("unverified", 0),
                    score=getattr(sau_report, "score_by_kind", {}).get(kind))
        # VERIFIES 指向该类的一个合法 source 节点；
        # domain/range 不允许的类型（如 Algorithm）会被 rel 拒绝，继续找下一个。
        for s in spec.by_kind(kind)[:1]:
            for src in s.source_node_ids:
                if src in g.nodes and rel(ev_id, "VERIFIES", src):
                    break

    # 8) ClaimAnchor：三哈希（dry 时 outputs_sha 明确为空，不编造）
    ca_id = add(f"{prefix}:claimanchor", "ClaimAnchor", "声明三哈希锚",
                derived=[spec.paper_id],
                code_sha=_sha((spec.code_plan or {}).get("functions") or []),
                inputs_sha=_sha(spec.data_contract),
                outputs_sha=_sha(results) if results else "",
                spec_hash=spec.spec_hash)

    # DEVIATES_FROM：有实跑值时才连（dry 不造偏离边）
    if results is not None:
        for s in spec.by_kind("numeric")[:1]:
            for src in s.source_node_ids:
                if src in g.nodes and g.nodes[src].type == "LeaderboardEntry" \
                        and rel(rr_id, "DEVIATES_FROM", src):
                    break

    # LINEAGE_OF：SourcePaper → Paper（若图中已有该应用节点）
    if graph is not None:
        src_nodes = getattr(graph, "nodes", {}) or {}
        for nid, n in src_nodes.items():
            if getattr(n, "type", "") == "SourcePaper" and \
                    (getattr(n, "attrs", {}) or {}).get("layer") == "application":
                if nid not in g.nodes:
                    g.node(n.id, n.type, n.label,
                           **{k: v for k, v in (n.attrs or {}).items()
                              if k != "label"})
                if spec.paper_id in g.nodes:
                    rel(nid, "LINEAGE_OF", spec.paper_id)

    rep = {
        "run_id": run_id, "graph_id": g.graph_id,
        "by_type": by_type,
        "n_nodes": len(g.nodes), "n_assertions": len(g.assertions),
        "n_upgraded_classes_present": len([t for t in by_type
                                           if t in REPRO_APP_CLASSES]),
        "relations_used": sorted({a.relation for a in g.assertions
                                  if a.relation in REPRO_APP_RELATIONS}),
        "layer": "application", "task": "reproduction",
        "semantic_layer_untouched": True,
    }
    if out_dir is not None:
        p = Path(out_dir)
        p.mkdir(parents=True, exist_ok=True)
        target = p / "app_repro_runtime.json"
        g.save(str(target))
        rep["path"] = str(target)
        # 新 run 自动带上层次化 rubric 树：缺树则即时编译，再挂进运行时图。
        # 全流程 try/except，树编译失败绝不阻断复现主流程。
        try:
            from . import rubric_runtime, rubric_tree
            tf = p / "RUBRIC_TREE.json"
            if not tf.exists():
                sau = [x.to_dict() if hasattr(x, "to_dict") else dict(x)
                       for x in (getattr(spec, "sau", None) or [])]
                if sau:
                    t = rubric_tree.build_rubric_tree(
                        sau,
                        paper_id=str(getattr(spec, "paper_id", "") or ""),
                        arxiv_id=str(getattr(spec, "arxiv_id", "") or ""),
                        spec_hash=str(getattr(spec, "spec_hash", "") or ""))
                    tf.write_text(json.dumps(t, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
            # 有逐条判定就同时产出树评分（无论树是新建还是已存在）
            verd = list(getattr(sau_report, "verdicts", None) or [])
            sf = p / "RUBRIC_TREE_SCORES.json"
            if verd and tf.exists():
                t = json.loads(tf.read_text(encoding="utf-8"))
                sc = rubric_tree.tree_score(t, verd)
                sf.write_text(json.dumps(sc, ensure_ascii=False, indent=2),
                              encoding="utf-8")
            rr = rubric_runtime.attach(p)
            rep["rubric_runtime"] = rr
            if rr.get("n_leaf_nodes"):
                # 树节点也是运行时产物，计入 by_type 与升级类计数
                by_type["RubricNode"] = (rr.get("n_branch_nodes", 0)
                                         + rr.get("n_leaf_nodes", 0))
                rep["n_upgraded_classes_present"] = len(
                    [t for t in by_type if t in REPRO_APP_CLASSES])
        except Exception as exc:  # noqa: BLE001
            rep["rubric_runtime"] = {"error":
                                     type(exc).__name__ + ":" + str(exc)[:120]}
    rep["graph"] = g
    return rep
