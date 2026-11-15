"""P0-2：从既有图谱确定性编译 ReproSpec（GGR 蓝图 §4–§5，R0.5）。

设计约束（务必遵守）：
  * **只读图、不写图**；编译结果只写 ``out_dir`` 下的 JSON
  * **零 LLM**：SAU 集合完全由图上的节点/边/属性推导
  * 关系名一律走 ``relations.py`` 的规范名，不认历史别名（除了 READ 侧兼容）
  * 无事实就记 ``gaps`` / ``warnings``，**绝不编造数值或符号**
  * 同一输入必须得到同一 ``spec_hash``（幂等，供 MethodLock 与重跑复用）

用法：
    from capfactory.reprospec import compile_reprospec

    spec = compile_reprospec(arxiv_id="2411.06608")
    spec.counts()          # {'method': 14, 'code_grounding': 17, ...}
    spec.spec_hash         # 'sha256:...'
    spec.save("storage_cf/repro_runs/2411.06608")

    # 也可以传自己的图
    from capfactory.po import POGraph
    g = POGraph.load("storage_cf/sciforge/app_reproduction.json")
    spec = compile_reprospec(g, paper_id="paper:2411.06608")
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .contract import DEFAULT_BUDGETS, ReproSpec, SAU
from .relations import resolve_relation

DEFAULT_APP_GRAPH = Path("storage_cf/sciforge/app_reproduction.json")
COMPILER_VERSION = "ggr-spec-0.2.0"

# 编译时使用的规范关系（全部来自 relations.SEMANTIC_RELATIONS / APP_RELATIONS）
_REL = {
    "method": "PROPOSES_METHOD",
    "module": "HAS_MODULE",
    "impl": "MODULE_IMPLEMENTED_BY",
    "impl_rev": "BELONGS_TO_MODULE",
    "repo": "HAS_CODE",
    "repo_fn": "HAS_FUNCTION",
    "bench": "EVALUATED_ON",
    "contract": "HAS_CONTRACT",
    "entry": "HAS_ENTRY",
    "entry_metric": "USES_METRIC",
    "bench_metric": "HAS_METRIC",
    "evidence": "SUPPORTED_BY",
    "related": "RELATED_TO",
    "subclass": "SUBCLASS_OF",
    "source_paper": "SITUATED_IN",
}


# ---------------------------------------------------------------------------
# 图访问适配层（POGraph 与 duck-typed 对象都支持）
# ---------------------------------------------------------------------------
def _nodes(g: Any) -> Dict[str, Any]:
    return getattr(g, "nodes", {}) or {}


def _node(g: Any, nid: str) -> Any:
    return _nodes(g).get(nid)


def _ntype(g: Any, nid: str) -> str:
    n = _node(g, nid)
    return str(getattr(n, "type", "") or "") if n else ""


def _label(g: Any, nid: str) -> str:
    n = _node(g, nid)
    if not n:
        return nid
    return str(getattr(n, "label", "") or
               (getattr(n, "attrs", {}) or {}).get("name") or nid)


def _attrs(g: Any, nid: str) -> Dict[str, Any]:
    n = _node(g, nid)
    return dict(getattr(n, "attrs", {}) or {}) if n else {}


def _as_list(v: Any) -> List[str]:
    """把 ``inputs`` / ``outputs`` 等字段安全转成词元列表。

    真实图里这些字段有时是 list，有时是**字符串**（如 ``"分子片段"``）。
    若直接 ``set(map(str, ...))`` 会把中文字符串拆成单字，导致
    ``数据流 ['分','子']`` 这种虚假顺序依赖。这里统一按分隔符切词，
    单个字符串作为整体词元，绝不逐字符拆分。
    """
    if v is None:
        return []
    if isinstance(v, (list, tuple, set, frozenset)):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        import re
        s = v.strip()
        if not s:
            return []
        parts = [p.strip() for p in re.split(r"[,，;；、|/]+", s) if p.strip()]
        return parts or [s]
    return [str(v)]


def _out(g: Any, nid: str, rel: str = "") -> List[Any]:
    """取某节点的出边（Assertion 列表）。"""
    if rel:
        try:
            return list(g.outgoing(nid, rel))
        except Exception:  # noqa: BLE001
            pass
    return [a for a in getattr(g, "assertions", []) or []
            if a.source == nid and (not rel or a.relation == rel)]


def _in(g: Any, nid: str, rel: str) -> List[Any]:
    """取某节点的入边（用于 CodeFunction --BELONGS_TO_MODULE--> Module 反向）。"""
    try:
        return list(g.incoming(nid, rel))
    except Exception:  # noqa: BLE001
        return [a for a in getattr(g, "assertions", []) or []
                if a.target == nid and a.relation == rel]


def _targets(g: Any, nid: str, rel: str, typ: str = "") -> List[str]:
    out: List[str] = []
    for a in _out(g, nid, rel):
        t = a.target
        if t not in _nodes(g):
            continue
        if typ and _ntype(g, t) != typ:
            continue
        if t not in out:
            out.append(t)
    return out


def _find_paper(g: Any, paper_id: Optional[str],
                arxiv_id: Optional[str]) -> Tuple[str, str]:
    """返回 (paper_id, 失败原因)。"""
    nodes = _nodes(g)
    if paper_id and paper_id in nodes and _ntype(g, paper_id) == "Paper":
        return paper_id, ""
    if paper_id and paper_id in nodes:
        return "", f"node_not_paper:{paper_id}"
    aid = (arxiv_id or "").strip().lower().replace("arxiv:", "")
    if not aid:
        return "", "no_paper_id_and_no_arxiv_id"
    for nid, n in nodes.items():
        if getattr(n, "type", "") != "Paper":
            continue
        a = _attrs(g, nid)
        if str(a.get("arxiv_id", "")).lower() == aid or \
                nid.lower().endswith(aid) or aid in str(a.get("title", "")).lower():
            return nid, ""
    return "", f"paper_not_found:{aid}"


def _norm_id(s: str) -> str:
    """把 arxiv id 变成 id 片段（去掉点、斜杠）。"""
    return "".join(c if c.isalnum() or c in "-_" else "" for c in str(s))


# ---------------------------------------------------------------------------
# 五类 SAU 编译
# ---------------------------------------------------------------------------
def _sau_method(g: Any, aid: str, algo: str, mod: str,
                idx: int) -> SAU:
    ma = _attrs(g, mod)
    algo_label = _label(g, algo)
    mod_label = _label(g, mod)
    mechanism = str(ma.get("mechanism") or ma.get("name") or mod_label)
    inputs = _as_list(ma.get("inputs"))
    outputs = _as_list(ma.get("outputs"))
    statement = (f"{algo_label} 的模块「{mod_label}」实现 {mechanism}"
                 f"（inputs={list(inputs) or '未标注'} → "
                 f"outputs={list(outputs) or '未标注'}）")
    return SAU(
        id=f"sau:{aid}:method:{idx:03d}", kind="method",
        statement=statement,
        source_node_ids=[algo, mod],
        evidence_ids=list(ma.get("evidence_ids") or []),
        check={"op": "module_implemented", "target": mod,
               "algorithm": algo, "mechanism": mechanism,
               "inputs": list(inputs), "outputs": list(outputs),
               "formula": str(ma.get("formula") or "")},
        required=True, provenance="derived",
        relation_hint=f"{_REL['method']}|{_REL['module']}")


def _impl_targets(g: Any, mod: str) -> List[str]:
    """模块的 CodeFunction 落地：正向 MODULE_IMPLEMENTED_BY + 反向 BELONGS_TO_MODULE。"""
    hits = _targets(g, mod, _REL["impl"], "CodeFunction")
    for a in _in(g, mod, _REL["impl_rev"]):
        if a.source in _nodes(g) and _ntype(g, a.source) == "CodeFunction" \
                and a.source not in hits:
            hits.append(a.source)
    return hits


def _sau_code(g: Any, aid: str, mod: str, fn: str, idx: int) -> SAU:
    fa = _attrs(g, fn)
    statement = (f"「{_label(g, mod)}」由代码符号 "
                 f"{_label(g, fn)} 实现"
                 f"（{fa.get('file') or fa.get('path') or '未标注文件'}）")
    return SAU(
        id=f"sau:{aid}:code_grounding:{idx:03d}", kind="code_grounding",
        statement=statement,
        source_node_ids=[mod, fn],
        evidence_ids=list(fa.get("evidence_ids") or []),
        check={"op": "symbol_exists", "target": fn,
               "signature": fa.get("signature") or fa.get("name") or "",
               "file": fa.get("file") or fa.get("path") or "",
               "lineno": fa.get("lineno"),
               "stub_allowed": False},
        required=True, provenance="extracted",   # AST 是客观事实
        relation_hint=_REL["impl"])


def _sau_protocol(g: Any, aid: str, bench: str,
                  contract: str, idx: int) -> SAU:
    ba = _attrs(g, bench)
    ca = _attrs(g, contract) if contract else {}
    inp = ca.get("input_form") or ba.get("input_form") or "未标注"
    out = ca.get("output_form") or ba.get("output_form") or "未标注"
    n = ca.get("n_samples") or ba.get("n_samples") or "未标注"
    is_eval = bool(ba.get("is_evaluation", True))
    statement = (f"{_label(g, bench)} 的数据契约为 "
                 f"{inp} → {out}，样本量 {n}，评测基准={is_eval}")
    return SAU(
        id=f"sau:{aid}:protocol:{idx:03d}", kind="protocol",
        statement=statement,
        source_node_ids=[bench] + ([contract] if contract else []),
        evidence_ids=list((ca or ba).get("evidence_ids") or []),
        check={"op": "data_contract", "target": bench,
               "input_form": inp, "output_form": out, "n_samples": n,
               "is_evaluation": is_eval,
               "shape_probe": None},   # 由 R3.5 填实测值，编译期不编造
        required=is_eval, provenance="derived",
        relation_hint=f"{_REL['bench']}|{_REL['contract']}")


_DIRECTION_MAP = {"higher": "max", "max": "max", "maximize": "max",
                  "lower": "min", "min": "min", "minimize": "min"}


def _sau_numeric(g: Any, aid: str, bench: str, entry: str,
                 metric: str, idx: int) -> SAU:
    ea = _attrs(g, entry)
    mta = _attrs(g, metric) if metric else {}
    name = str(ea.get("metric") or mta.get("name") or "未标注指标")
    value = ea.get("value")
    unit = str(ea.get("unit") or mta.get("unit") or "")
    direction_raw = str(mta.get("direction") or ea.get("direction") or "")
    direction = _DIRECTION_MAP.get(direction_raw.lower(), direction_raw)
    try:
        value_num = (float(value) if value is not None
                     and str(value).strip() != "" else None)
    except (TypeError, ValueError):
        value_num = None
    model = str(ea.get("model") or "未标注模型")
    statement = (f"{_label(g, bench)} 上 {model} 的 {name} = "
                 f"{value if value is not None else '缺失'}{unit}"
                 f"（方向={direction or '未标注'}）")
    evidence: List[str] = []
    for a in _out(g, entry, _REL["evidence"]):
        if a.target in _nodes(g):
            evidence.append(a.target)
    return SAU(
        id=f"sau:{aid}:numeric:{idx:03d}", kind="numeric",
        statement=statement,
        source_node_ids=[bench, entry] + ([metric] if metric else []),
        evidence_ids=evidence + list(ea.get("evidence_ids") or []),
        check={"op": "numeric_compare", "target": entry,
               "metric": name, "value": value, "value_num": value_num,
               "unit": unit, "direction": direction,
               "direction_raw": direction_raw,
               "direction_source": mta.get("direction_source") or "",
               "tolerance": DEFAULT_BUDGETS["deviation_tolerance"]},
        required=bool(ea.get("is_sota") or ea.get("is_ours")),
        provenance="extracted",
        relation_hint=f"{_REL['entry']}|{_REL['entry_metric']}")


def _sau_ordering(g: Any, aid: str, mods: Sequence[str],
                  observed: List[Tuple[str, str]], idx: int,
                  declared: bool = False) -> SAU:
    before, after = observed[idx] if idx < len(observed) else ("", "")
    if declared:
        statement = (f"声明顺序：{_label(g, before)} 应在 "
                     f"{_label(g, after)} 之前（图上无 inputs/outputs 依赖证据）")
        op, required, prov = "declared_order", False, "inferred"
    else:
        ba = _attrs(g, before)
        aa = _attrs(g, after)
        shared = sorted(set(_as_list(ba.get("outputs"))) &
                        set(_as_list(aa.get("inputs"))))
        statement = (f"执行顺序：{_label(g, before)} 必须早于 "
                     f"{_label(g, after)}（数据流 {shared}）")
        op, required, prov = "ordering", True, "derived"
    return SAU(
        id=f"sau:{aid}:ordering:{idx:03d}", kind="ordering",
        statement=statement,
        source_node_ids=[before, after],
        check={"op": op, "before": before, "after": after},
        required=required, provenance=prov,
        relation_hint=_REL["module"])


def _find_cycle_edges(pairs: Sequence[Tuple[str, str]]) -> set:
    """找出依赖闭包里构成环的边（DFS 三色标记）。

    真实图里 ``inputs/outputs`` 词元可能同名复用（如两个模块都输出
    「潜在向量 z」），从而生成互相矛盾的顺序约束。这类 SAU 不能作为
    required 门，必须降级并告警 —— 对齐 SciForge/GrOIL 的环消解原则。
    """
    adj: Dict[str, List[str]] = {}
    for b, a in pairs:
        adj.setdefault(b, []).append(a)
    color: Dict[str, int] = {}
    stack: List[str] = []
    cycles: set = set()

    def dfs(u: str) -> None:
        color[u] = 1
        stack.append(u)
        for v in adj.get(u, []):
            c = color.get(v, 0)
            if c == 1:
                i = stack.index(v)
                for k in range(i, len(stack) - 1):
                    cycles.add((stack[k], stack[k + 1]))
                cycles.add((u, v))
            elif c == 0:
                dfs(v)
        stack.pop()
        color[u] = 2

    for n in list(adj):
        if color.get(n, 0) == 0:
            dfs(n)
    return cycles


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def compile_reprospec(
        graph: Any = None, *,
        paper_id: Optional[str] = None,
        arxiv_id: Optional[str] = None,
        graph_path: Optional[str | Path] = None,
        out_dir: Optional[str | Path] = None,
        budgets: Optional[Dict[str, Any]] = None,
        max_lineage: int = 3) -> ReproSpec:
    """把应用层/语义层图编译成 ReproSpec（确定性、只读、零 LLM）。

    参数
        graph      : POGraph 或 duck-typed 图；None 时从 ``graph_path`` 加载
        paper_id   : 图中 Paper 节点 id；与 arxiv_id 二选一
        arxiv_id   : 按 ``attrs.arxiv_id`` 查找论文
        graph_path : 默认 ``storage_cf/sciforge/app_reproduction.json``
        out_dir    : 给出则写 REPRO_SPEC.json / SAU_LIST.json
        budgets    : 覆盖 DEFAULT_BUDGETS
        max_lineage: Paper Lineage 条数上限（AutoReproduce 默认 3）
    """
    path = Path(graph_path) if graph_path else DEFAULT_APP_GRAPH
    g = graph
    if g is None:
        if not path.exists():
            return ReproSpec.empty(paper_id or "", arxiv_id or "",
                                  f"graph_not_found:{path}")
        from capfactory.po import POGraph
        g = POGraph.load(str(path))

    pid, reason = _find_paper(g, paper_id, arxiv_id)
    if not pid:
        return ReproSpec.empty(paper_id or "", arxiv_id or "", reason)

    pa = _attrs(g, pid)
    aid = _norm_id(pa.get("arxiv_id") or arxiv_id or pid.split(":")[-1])
    spec = ReproSpec(
        paper_id=pid,
        arxiv_id=str(pa.get("arxiv_id") or arxiv_id or ""),
        graph_path=str(path),
        graph_stats={"n_nodes": len(_nodes(g)),
                     "n_assertions": len(getattr(g, "assertions", []) or [])},
        budgets=dict(DEFAULT_BUDGETS, **(budgets or {})),
    )

    # ---- R1：方法规格 + 模块 + 代码落地 ---------------------------------
    algos = _targets(g, pid, _REL["method"], "Algorithm")
    modules: List[str] = []
    functions: List[str] = []
    for algo in algos:
        for mod in _targets(g, algo, _REL["module"], "AlgorithmModule"):
            if mod in modules:
                continue
            modules.append(mod)
            spec.sau.append(_sau_method(g, aid, algo, mod,
                                        len(spec.by_kind("method"))))
            for fn in _impl_targets(g, mod):
                if fn not in functions:
                    functions.append(fn)
                spec.sau.append(_sau_code(
                    g, aid, mod, fn, len(spec.by_kind("code_grounding"))))

    # ---- R3/R4：数据契约、榜单行、指标 -----------------------------------
    benches: List[str] = []
    for src in [pid] + algos:
        for b in _targets(g, src, _REL["bench"], "Benchmark"):
            if b not in benches:
                benches.append(b)

    for bench in benches:
        ba = _attrs(g, bench)
        contracts = _targets(g, bench, _REL["contract"], "DataContract")
        if not contracts:
            # 没有 DataContract 节点时用 Benchmark 自身属性（不编造）
            spec.sau.append(_sau_protocol(
                g, aid, bench, "", len(spec.by_kind("protocol"))))
            spec.warnings.append(f"benchmark {bench} 缺 DataContract，用属性回退")
        for c in contracts:
            spec.sau.append(_sau_protocol(
                g, aid, bench, c, len(spec.by_kind("protocol"))))
        ca = _attrs(g, contracts[0]) if contracts else {}
        spec.data_contract.append({
            "benchmark": bench, "label": _label(g, bench),
            "input_form": ca.get("input_form") or ba.get("input_form"),
            "output_form": ca.get("output_form") or ba.get("output_form"),
            "n_samples": ca.get("n_samples") or ba.get("n_samples"),
            "scale": ca.get("scale") or ba.get("scale"),
            "is_evaluation": bool(ba.get("is_evaluation", True)),
        })

        for entry in _targets(g, bench, _REL["entry"], "LeaderboardEntry"):
            mts = _targets(g, entry, _REL["entry_metric"], "MetricDefinition")
            mt = mts[0] if mts else ""
            spec.sau.append(_sau_numeric(
                g, aid, bench, entry, mt, len(spec.by_kind("numeric"))))

        for mt in _targets(g, bench, _REL["bench_metric"], "MetricDefinition"):
            ma = _attrs(g, mt)
            key = str(ma.get("name") or _label(g, mt))
            sota = (ba.get("sota_by_metric") or {}).get(key, {})
            spec.metric_plan.setdefault(key, {
                "name": key, "direction": ma.get("direction") or "",
                "direction_source": ma.get("direction_source") or "",
                "unit": ma.get("unit") or "", "target": mt,
                "sota_model": sota.get("model") if isinstance(sota, dict) else "",
                "sota_value": sota.get("value") if isinstance(sota, dict) else None,
                "benchmarks": [],
            })
            spec.metric_plan[key]["benchmarks"].append(bench)

    # ---- 顺序 SAU：inputs/outputs 依赖闭包 -------------------------------
    observed: List[Tuple[str, str]] = []
    for i, before in enumerate(modules):
        outs = set(_as_list(_attrs(g, before).get("outputs")))
        if not outs:
            continue
        for j, after in enumerate(modules):
            if i == j:
                continue
            ins = set(_as_list(_attrs(g, after).get("inputs")))
            if outs & ins:
                observed.append((before, after))
    if observed:
        # 每个 after 只保留**最靠近的一个直接前驱**，避免 O(n²) 组合爆炸
        # （14 模块曾产生 44 条 ordering SAU）；其余前驱记在 check 里备查。
        last: Dict[str, Tuple[str, str]] = {}
        all_pred: Dict[str, List[str]] = {}
        for b, a in observed:
            last[a] = (b, a)
            all_pred.setdefault(a, []).append(b)
        order_idx = {m: i for i, m in enumerate(modules)}
        direct = [last[a] for a in sorted(
            last, key=lambda x: order_idx.get(x, 10 ** 6))]
        cycles = _find_cycle_edges(direct)
        for i, (b, a) in enumerate(direct):
            s = _sau_ordering(g, aid, modules, direct, i)
            s.check["all_predecessors"] = [
                x for x in all_pred.get(a, []) if x != b]
            if (b, a) in cycles:
                s.check["cycle"] = True
                s.required = False
                s.provenance = "inferred"
                s.statement += "（⚠ 与其它依赖构成环，降级为待人工确认）"
            spec.sau.append(s)
        if cycles:
            spec.warnings.append(
                f"ordering 存在 {len(cycles)} 条环依赖，已降级为 required=False")
    elif len(modules) >= 2:
        declared = [(modules[i], modules[i + 1])
                    for i in range(len(modules) - 1)]
        for i in range(len(declared)):
            spec.sau.append(_sau_ordering(g, aid, modules, declared, i,
                                          declared=True))
        spec.warnings.append("模块无 inputs/outputs 依赖证据，ordering 降级为声明顺序")

    # ---- R1.5：Paper Lineage（离线，用已有科技树关系）--------------------
    lineage: List[Dict[str, Any]] = []
    for rel in (_REL["related"], _REL["source_paper"]):
        for a in _out(g, pid, rel):
            if a.target not in _nodes(g):
                continue
            lineage.append({
                "id": a.target, "label": _label(g, a.target),
                "type": _ntype(g, a.target), "relation": a.relation,
                "source": "paper_out",
                "kind": str(getattr(a, "properties", {}).get("kind") or ""),
            })
    for algo in algos:
        # SUBCLASS_OF 出边（本方法改进了谁）+ 入边（谁是本方法的前身）都要收，
        # 真实图里基线关系常以入边形式存在。
        for a in list(_out(g, algo, _REL["subclass"])) + \
                list(_in(g, algo, _REL["subclass"])):
            other = a.target if a.source == algo else a.source
            if other not in _nodes(g) or other == algo:
                continue
            lineage.append({
                "id": other, "label": _label(g, other),
                "type": _ntype(g, other), "relation": a.relation,
                "source": "algorithm_subclass",
                "direction": "out" if a.source == algo else "in",
                "kind": str(getattr(a, "properties", {}).get("kind") or ""),
            })
    # 优先「方法谱系」（SUBCLASS_OF），其次出处论文，再其次泛相关文献；
    # 对齐 AutoReproduce「优先主实验对比基线」的意图。
    rank = {"extends": 0, "improves": 0, "baseline": 0, "replaces": 1}
    src_rank = {"algorithm_subclass": 0, "paper_out": 1}
    lineage.sort(key=lambda x: (
        src_rank.get(x["source"], 2) +
        (0 if x["relation"] == _REL["source_paper"] else 0.5),
        rank.get(x["kind"].lower(), 2), x["id"]))
    seen: set = set()
    spec.lineage = [x for x in lineage
                    if not (x["id"] in seen or seen.add(x["id"]))][:max_lineage]

    # ---- R2：代码计划（依赖有序）-----------------------------------------
    repos = _targets(g, pid, _REL["repo"], "CodeRepository")
    repo_fns: List[str] = []
    for r in repos:
        for fn in _targets(g, r, _REL["repo_fn"], "CodeFunction"):
            if fn not in repo_fns:
                repo_fns.append(fn)
    order = [x["before"] for x in
             [s.check for s in spec.by_kind("ordering")]
             if x.get("before")]
    order = list(dict.fromkeys(order + [m for m in modules if m not in order]))
    spec.code_plan = {
        "strategy": "audit_repo" if repos else "generate_from_plan",
        "has_repo": bool(repos),
        "repositories": repos,
        "modules": modules,
        "functions": list(dict.fromkeys(functions + repo_fns)),
        "order": order,
    }

    # ---- MethodLock：冻结 method SAU --------------------------------------
    import hashlib
    method_payload = json.dumps(
        [s.stable_key() for s in sorted(spec.by_kind("method"),
                                        key=lambda x: x.id)],
        ensure_ascii=False, sort_keys=True, default=str)
    spec.method_lock = {
        "locked": True,
        "compiler_version": COMPILER_VERSION,
        "n_method_sau": len(spec.by_kind("method")),
        "method_sau_hash": "sha256:" + hashlib.sha256(
            method_payload.encode("utf-8")).hexdigest()[:16],
    }

    # ---- 缺口与告警（只报告，不编造）-------------------------------------
    for kind, phase, reason in (
            ("method", "R1", "no_method_sau"),
            ("code_grounding", "R2", "no_code_symbol_sau"),
            ("protocol", "R3", "no_protocol_sau"),
            ("numeric", "R4", "no_numeric_sau")):
        if not spec.by_kind(kind):
            spec.gaps.append({"phase": phase, "reason": reason})
    if not repos:
        spec.warnings.append("无 CodeRepository：R2 走 PaperCoder 生成路径")
    for mt in spec.metric_plan.values():
        if mt.get("direction_source") == "heuristic":
            spec.warnings.append(f"metric {mt['name']} 方向为启发式，需人工确认")
        if not mt.get("direction"):
            spec.warnings.append(f"metric {mt['name']} 缺 direction，R4 降级 PARTIAL")

    spec.spec_hash = spec.compute_hash()
    if out_dir is not None:
        spec.save(out_dir)
    return spec
