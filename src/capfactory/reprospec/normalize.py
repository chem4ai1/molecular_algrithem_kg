"""P3-1：复现范围归一化视图（只读源图、可审计、可对照）。

蓝图 §7 的 P3-1 写的是「补齐 4 个模块的代码落地边」，但直接给图补边是
错的。实测 ``app_reproduction.json`` 后，4 条 ``method mismatch`` 是：

* ``fragment_coarse_graining`` / ``fragment_predictor`` /
  ``conditional_sampling`` —— 确属 MolMiner，只是抽取时没把仓库函数挂上去；
* ``identity_pullback`` —— id 前缀是 ``2608.06956``，属于**另一篇论文**。

同一批跨论文节点（``graph_encoder`` / ``hierarchical_decoder`` /
``autoregressive_decoder``）还制造了 2 条 ordering 环。给它们补边会伪造
跨论文事实，并把自编码器反馈闭环塞进线性 ``code_plan.order``。

因此本模块做两件事，且**只作用于内存视图**（源图文件一个字节不改）：

1. **scope 归一化**：删除「本篇 Algorithm --HAS_MODULE--> 其它论文模块」的边。
   其它论文自身的边保持原样，多篇回归互不干扰。
2. **证据化补边**：对仍缺 ``MODULE_IMPLEMENTED_BY`` 的本篇模块，只在
   本篇 ``CodeRepository`` 下的 ``CodeFunction`` 里按 ``name + purpose``
   的关键词命中建立映射。每条补边带 ``matched_terms / evidence_purpose /
   grounding_rule`` 与 ``attribution="analyst_inference"``，明确区分于
   AST 直接抽取的边。

所有增删改写入 ``NORMALIZATION.json``；``--scope legacy`` 可跑未归一化对照。

    from capfactory.reprospec.normalize import normalize_for_repro
    g2, audit = normalize_for_repro(graph, "paper:2411.06608")
    spec = compile_reprospec(g2, paper_id="paper:2411.06608")
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

from capfactory.po import POGraph, Assertion

_ARXIV_IN_ID = re.compile(r"\d{4}\.\d{4,5}")

# 模块后缀 → 证据规则。primary 必须命中至少一个才允许建边；
# 只用 purpose/name 里真实存在的词，不引入论文之外的知识。
GROUNDING_RULES: Dict[str, Dict[str, Any]] = {
    "fragment_coarse_graining": {
        "primary": ("grain", "attachment", "remap", "canonicalization"),
        "rationale": "片段粗粒化对应 grain 切分 / attachment 枚举 / 原子重映射规范化",
    },
    "fragment_predictor": {
        "primary": ("seed", "starter"),
        "rationale": "起始片段预测对应 FragmentStarter 的 seed selection",
    },
    "conditional_sampling": {
        "primary": ("gmm", "condition"),
        "rationale": "缺失目标性质补全对应 GMM 与 conditioned sampling",
    },
}


@dataclass
class NormalizationResult:
    paper_id: str
    arxiv_id: str
    scope: str = "strict"
    source_graph: str = ""
    n_assertions_before: int = 0
    n_assertions_after: int = 0
    removed_edges: List[Dict[str, str]] = field(default_factory=list)
    excluded_modules: List[Dict[str, Any]] = field(default_factory=list)
    excluded_algorithms: List[Dict[str, Any]] = field(default_factory=list)
    added_edges: List[Dict[str, Any]] = field(default_factory=list)
    unresolved_modules: List[str] = field(default_factory=list)
    candidate_functions: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    note: str = ("只作用于内存归一化视图；源图文件不变。"
                 "补边来自 CodeFunction.name/purpose 关键词证据，非 AST 直接落地。")

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["n_removed_edges"] = len(self.removed_edges)
        d["n_added_edges"] = len(self.added_edges)
        d["n_excluded_modules"] = len(self.excluded_modules)
        d["n_excluded_algorithms"] = len(self.excluded_algorithms)
        return d

    def save(self, out_dir: str | Path) -> str:
        p = Path(out_dir)
        p.mkdir(parents=True, exist_ok=True)
        f = p / "NORMALIZATION.json"
        f.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                     encoding="utf-8")
        return str(f)


# ---------------------------------------------------------------------------
# 图访问（POGraph 与 duck-typed 都支持）
# ---------------------------------------------------------------------------
def _nodes(g: Any) -> Dict[str, Any]:
    return getattr(g, "nodes", {}) or {}


def _attrs(g: Any, nid: str) -> Dict[str, Any]:
    n = _nodes(g).get(nid)
    return dict(getattr(n, "attrs", {}) or {}) if n else {}


def _out(g: Any, nid: str, rel: str) -> List[Any]:
    try:
        return list(g.outgoing(nid, rel))
    except Exception:  # noqa: BLE001
        return [a for a in getattr(g, "assertions", []) or []
                if a.source == nid and a.relation == rel]


def _in(g: Any, nid: str, rel: str) -> List[Any]:
    try:
        return list(g.incoming(nid, rel))
    except Exception:  # noqa: BLE001
        return [a for a in getattr(g, "assertions", []) or []
                if a.target == nid and a.relation == rel]


def _foreign_arxiv(node_id: str, paper_aid: str) -> List[str]:
    """节点 id 里出现本篇之外的 arxiv 号 → 判为跨论文节点。"""
    found = set(_ARXIV_IN_ID.findall(str(node_id)))
    return sorted(found - {str(paper_aid)})


def _paper_aid(g: Any, paper_id: str) -> str:
    return str(_attrs(g, paper_id).get("arxiv_id") or
               str(paper_id).split(":")[-1])


def _repo_functions(g: Any, paper_id: str) -> List[str]:
    """只取本篇 CodeRepository 下、id 前缀与仓库 slug 一致的真实函数。

    图里 ``coderepository:raulorteg_molminer`` 的 HAS_FUNCTION 还混进了
    其它仓库与 ``codefunction:ast:*`` 别名；前缀过滤避免把别人的实现
    算到本篇头上。
    """
    out: List[str] = []
    nodes = _nodes(g)
    for a in _out(g, paper_id, "HAS_CODE"):
        repo = a.target
        if repo not in nodes:
            continue
        slug = str(repo).split(":", 1)[-1]
        prefix = f"codefunction:{slug}:"
        for e in _out(g, repo, "HAS_FUNCTION"):
            fn = e.target
            if fn in nodes and str(fn).startswith(prefix) and fn not in out:
                out.append(fn)
    return out


def _has_impl(g: Any, mod: str) -> bool:
    nodes = _nodes(g)
    for a in _out(g, mod, "MODULE_IMPLEMENTED_BY"):
        if a.target in nodes:
            return True
    for a in _in(g, mod, "BELONGS_TO_MODULE"):
        if a.source in nodes:
            return True
    return False


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def normalize_for_repro(graph: Any, paper_id: str, *,
                        strict: bool = True,
                        source_graph: str = "") -> Tuple[Any, NormalizationResult]:
    """返回 ``(归一化图视图, 审计对象)``；``strict=False`` 时原图原样返回。

    归一化图是新的 ``POGraph``：节点字典与原图共享（只读），断言列表是
    过滤 + 补边后的新列表。因此 ``compile_reprospec`` 的「只读图」契约
    依然成立，且同一 run 内主流程与双跑复用同一视图，``spec_hash`` 一致。
    """
    aid = _paper_aid(graph, paper_id)
    res = NormalizationResult(
        paper_id=paper_id, arxiv_id=aid,
        scope="strict" if strict else "legacy",
        source_graph=source_graph,
        n_assertions_before=len(getattr(graph, "assertions", []) or []))
    if not strict:
        res.n_assertions_after = res.n_assertions_before
        res.warnings.append("legacy 模式：未做任何范围归一化与补边")
        return graph, res

    algos = [a.target for a in _out(graph, paper_id, "PROPOSES_METHOD")]
    algo_set = set(algos)
    nodes = _nodes(graph)

    # ---- 1) scope：剔除挂在本篇算法下的跨论文模块 -------------------------
    foreign: Dict[str, List[str]] = {}
    kept: List[Any] = []
    for a in (getattr(graph, "assertions", []) or []):
        if (a.relation == "HAS_MODULE" and a.source in algo_set and
                a.target in nodes):
            fids = _foreign_arxiv(a.target, aid)
            if fids:
                foreign[a.target] = fids
                res.removed_edges.append({
                    "assertion_id": getattr(a, "id", ""),
                    "source": a.source, "relation": a.relation,
                    "target": a.target, "reason": "cross_paper_module"})
                continue
        kept.append(a)
    res.excluded_modules = [
        {"id": m, "foreign_arxiv": fids, "label": str(
            getattr(nodes[m], "label", m)) if m in nodes else m,
         "reason": "模块 id 含本篇之外的 arxiv 号，不属于本论文复现范围"}
        for m, fids in sorted(foreign.items())]
    if foreign:
        res.warnings.append(
            f"剔除 {len(foreign)} 个跨论文模块；跨论文模块造成的 "
            "inputs/outputs 双向依赖环随之消失")

    # ---- 1b) 剔除被误挂成 PROPOSES_METHOD 的基线算法 ----------------------
    # planner.build_plan 的 plan.methods 同时收 PROPOSES_METHOD 与 RELATED_TO
    # 的 Algorithm；R1 门会因基线算法（JTNN / MoLeR）缺 mechanism 而 PARTIAL。
    # 判据：归一化后该 Algorithm 没有任何本篇 HAS_MODULE 边，说明它只是
    # related work，不是本篇提出的方法。
    algo_with_modules = {
        a.source for a in kept
        if a.relation == "HAS_MODULE" and a.source in algo_set
        and a.target in nodes}
    kept2: List[Any] = []
    for a in kept:
        if (a.relation == "PROPOSES_METHOD" and a.source == paper_id
                and a.target in algo_set
                and a.target not in algo_with_modules):
            res.excluded_algorithms.append({
                "id": a.target,
                "label": str(getattr(nodes[a.target], "label", a.target)),
                "reason": "归一化后无本篇 HAS_MODULE 边，属基线/相关工作误挂"})
            res.removed_edges.append({
                "assertion_id": getattr(a, "id", ""), "source": a.source,
                "relation": a.relation, "target": a.target,
                "reason": "baseline_algorithm_without_in_scope_module"})
            continue
        kept2.append(a)
    kept = kept2
    if res.excluded_algorithms:
        res.warnings.append(
            f"剔除 {len(res.excluded_algorithms)} 个无本篇模块的基线算法，"
            "避免 R1 门把缺机理的 related work 算成本篇方法")

    # ---- 2) 证据化补边 ----------------------------------------------------
    in_scope: List[str] = []
    for algo in algos:
        for a in _out(graph, algo, "HAS_MODULE"):
            m = a.target
            if m in nodes and m not in foreign and m not in in_scope:
                in_scope.append(m)
    fns = _repo_functions(graph, paper_id)
    res.candidate_functions = list(fns)
    if not fns:
        res.warnings.append("本篇无可用 CodeFunction 候选，不补任何落地边")

    existing = {(a.source, a.target, a.relation) for a in kept}
    added: List[Assertion] = []
    for mod in in_scope:
        if _has_impl(graph, mod):
            continue
        suffix = str(mod).rsplit(":", 1)[-1]
        rule = GROUNDING_RULES.get(suffix)
        if not rule:
            res.unresolved_modules.append(mod)
            continue
        hits_for_mod = 0
        for fn in fns:
            fa = _attrs(graph, fn)
            text = " ".join(str(fa.get(k) or "") for k in
                            ("name", "purpose", "docstring", "signature")).lower()
            matched = [t for t in rule["primary"] if t in text]
            if not matched:
                continue
            key = (mod, fn, "MODULE_IMPLEMENTED_BY")
            if key in existing:
                continue
            existing.add(key)
            added.append(Assertion(
                id=f"assertion:norm:{len(added):04d}",
                source=mod, target=fn, relation="MODULE_IMPLEMENTED_BY",
                attribution="analyst_inference", evidence_ids=[],
                properties={
                    "grounding_rule": suffix,
                    "matched_terms": matched,
                    "evidence_purpose": str(fa.get("purpose") or ""),
                    "evidence_name": str(fa.get("name") or ""),
                    "provenance": "purpose_keyword_inference",
                    "rationale": str(rule.get("rationale") or ""),
                }))
            res.added_edges.append({
                "module": mod, "function": fn, "relation": key[2],
                "rule": suffix, "matched_terms": matched,
                "evidence_purpose": str(fa.get("purpose") or ""),
                "evidence_name": str(fa.get("name") or ""),
                "attribution": "analyst_inference",
                "grade": "purpose_keyword_inference (非 AST 直接落地)"})
            hits_for_mod += 1
        if not hits_for_mod:
            res.unresolved_modules.append(mod)
    if res.unresolved_modules:
        res.warnings.append(
            f"{len(res.unresolved_modules)} 个模块无可证据化映射，保持为真实缺口，"
            "不伪造落地边")

    # ---- 3) 组装内存视图 --------------------------------------------------
    g2 = POGraph(f"{getattr(graph, 'graph_id', 'po')}::scope:{aid}")
    g2.nodes = dict(nodes)
    g2.assertions = kept + added
    g2.meta = dict(getattr(graph, "meta", {}) or {})
    res.n_assertions_after = len(g2.assertions)
    return g2, res


def grounding_snapshot(graph: Any, paper_id: str) -> Dict[str, Any]:
    """只读诊断：列出本篇模块的代码落地缺口与可映射候选。"""
    aid = _paper_aid(graph, paper_id)
    algos = [a.target for a in _out(graph, paper_id, "PROPOSES_METHOD")]
    mods: List[str] = []
    for algo in algos:
        for a in _out(graph, algo, "HAS_MODULE"):
            if a.target not in mods:
                mods.append(a.target)
    return {
        "paper_id": paper_id, "arxiv_id": aid,
        "n_modules": len(mods),
        "foreign_modules": [m for m in mods if _foreign_arxiv(m, aid)],
        "modules_without_impl": [m for m in mods if not _has_impl(graph, m)],
        "candidate_functions": _repo_functions(graph, paper_id),
        "rules": sorted(GROUNDING_RULES),
    }
