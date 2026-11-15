"""Phase 0 intake：T-Box 编译 + A-Box 清点 + 推理就绪度 + 下游预算。

借鉴 GrOIL 与 zett，但按本项目的论文/代码图谱重做：

GrOIL ``stage7_serialize_tbox.py`` / ``abox_population.py``
  → T-Box 是**独立编译产物**（类/属性/domain-range/置信度），
    A-Box 按文档**独立填充**并带 ``sourceContractID/sourceContractSection``，
    验证是 TBox+ABox 一致性 / CQ 查空 / coverage。
zett ``templates.tsv`` + ``Extractor.__init__``
  → 静态类型表在初始化时装载，抽取只能从**封闭词表**选，
    ``[X]/[Y]`` 顺序约束关系方向。

本模块因此把 intake 从「数 6 类节点」升级为**契约建立点**：

    T-Box  ── 40 类 / 72 关系 / 形状 / 类型清单 / 封闭词表 / tbox_hash
    A-Box  ── 节点与断言的类型合规、溯源、悬空边、domain/range 违规
    切片    ── slice.GraphSlice（沿用，作为 A-Box 的任务视图）
    就绪度  ── 形状校验 + 关系覆盖 + 规则引擎实跑
    预算    ── 给 question / proposal / codegen / reproduce 的可用原料与缺口

门保持向后兼容：``PASS`` / ``BLOCKED`` 语义不变（无 Paper 才 BLOCKED）。
"""
from __future__ import annotations
import hashlib, json, re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ..po import POGraph
from ..ontology.library import OntologyLibrary, default_library, TYPE_REQUIREMENTS
from .slice import slice_for_task
from ..ontology.chains import (GROUPS, CHAINS, TENTACLE_SPECS, STAGES,
                               project_chains, render_chain_bundle,
                               chains_summary)
from .sources import CSV_PATHS as SOURCE_CSV_PATHS


@dataclass
class TBoxManifest:
    """T-Box 编译产物（与 A-Box 完全分离，只读）。"""
    n_classes: int = 0
    n_relations: int = 0
    classes: List[str] = field(default_factory=list)
    relations: Dict[str, List[str]] = field(default_factory=dict)
    shape_severities: Dict[str, int] = field(default_factory=dict)
    type_requirements: Dict[str, List[str]] = field(default_factory=dict)
    tbox_hash: str = ""
    issues: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"n_classes": self.n_classes, "n_relations": self.n_relations,
                "classes": self.classes, "relations": self.relations,
                "shape_severities": self.shape_severities,
                "type_requirements": self.type_requirements,
                "tbox_hash": self.tbox_hash, "issues": self.issues,
                "notes": self.notes, "conforms": not self.issues}

# T-Box 别名 / 遗留名：A-Box 里真实存在，但不能算 T-Box 定义缺陷。
CLASS_ALIASES = {"CodeBlock": "CodeModule", "Task": "ResearchQuestion",
                 "ExperimentalCondition": "EvaluationRun",
                 "MetricObservation": "Observation",
                 "ConceptAssertion": "CapabilityClaim"}
LEGACY_ABOX_RELATIONS = {"REPORTS", "RELATED_TO", "OF_METRIC",
                         "IMPLEMENTS_MODULE", "HAS_MODULE_DETAIL",
                         "HAS_LEADERBOARD", "FROM_OBSERVATION", "REPORTED_BY"}


@dataclass
class ABoxCensus:
    """A-Box 清点：实例是否遵守 T-Box、是否有溯源。"""
    n_nodes: int = 0
    n_assertions: int = 0
    type_counts: Dict[str, int] = field(default_factory=dict)
    relation_counts: Dict[str, int] = field(default_factory=dict)
    undeclared_types: List[str] = field(default_factory=list)
    undeclared_relations: List[str] = field(default_factory=list)
    dangling_edges: List[str] = field(default_factory=list)
    domain_range_violations: List[str] = field(default_factory=list)
    provenance_coverage: float = 0.0
    per_paper: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {k: getattr(self, k) for k in
                ("n_nodes", "n_assertions", "type_counts", "relation_counts",
                 "undeclared_types", "undeclared_relations", "dangling_edges",
                 "domain_range_violations", "provenance_coverage", "per_paper")}


def compile_tbox(lib: Optional[OntologyLibrary] = None) -> TBoxManifest:
    """编译 T-Box：封闭词表 + domain/range + 形状 + 类型清单 + 指纹 + 环检测。"""
    lib = lib or default_library()
    m = TBoxManifest(n_classes=len(lib.classes),
                     n_relations=len(lib.relations),
                     classes=sorted(lib.classes),
                     relations={r: list(v[:2]) for r, v in sorted(lib.relations.items())},
                     shape_severities=dict(Counter(
                         p.severity for s in lib.shapes.values()
                         for p in s.props.values())),
                     type_requirements={k: v["classes"] for k, v in
                                        TYPE_REQUIREMENTS.items()})
    payload = json.dumps({"classes": m.classes, "relations": m.relations,
                          "shapes": {c: sorted(s.props) for c, s in
                                     sorted(lib.shapes.items())},
                          "requirements": m.type_requirements},
                         sort_keys=True, ensure_ascii=False)
    m.tbox_hash = hashlib.sha256(payload.encode()).hexdigest()
    # ① domain/range 的类必须在封闭词表内（GrOIL reasoner 的 undeclared predicate）
    known = set(lib.classes)

    def legal(name: str) -> bool:
        # ``A|B|C`` 是 domain/range 的多类联合（V2_RELATIONS 的真实写法）
        return all((x.strip() in known or CLASS_ALIASES.get(x.strip()) in known)
                   for x in name.split("|"))

    for rel, (dom, rng, *_rest) in lib.relations.items():
        if not legal(dom):
            m.issues.append(f"{rel}: domain {dom} 不在 T-Box")
        elif "|" in dom:
            m.notes.append(f"{rel}: domain 为多类联合 {dom}")
        if not legal(rng):
            m.issues.append(f"{rel}: range {rng} 不在 T-Box")
        elif "|" in rng:
            m.notes.append(f"{rel}: range 为多类联合 {rng}")
    # ② 形状继承 parent 链环检测（DFS + rec_stack，GrOIL stage5 同思路）
    parents = {c: s.parent for c, s in lib.shapes.items() if s.parent}
    visited: Set[str] = set()
    for c in parents:
        if c in visited:
            continue
        stack, cur = set(), c
        while cur in parents:
            if cur in stack:
                m.issues.append(f"形状继承环: {cur}")
                break
            stack.add(cur); visited.add(cur)
            cur = parents[cur]
    # ③ 每个类型清单引用的类/关系必须已声明（zett 封闭词表的等价检查）
    for tname, req in TYPE_REQUIREMENTS.items():
        for c in req["classes"]:
            if c not in known:
                m.issues.append(f"TYPE_REQUIREMENTS[{tname}] 未声明类 {c}")
        for r in req["relations"]:
            if r not in lib.relations:
                if r in LEGACY_ABOX_RELATIONS:
                    m.notes.append(f"TYPE_REQUIREMENTS[{tname}] 用 A-Box 遗留关系 {r}")
                else:
                    m.issues.append(f"TYPE_REQUIREMENTS[{tname}] 未声明关系 {r}")
    return m


def census_abox(graph: POGraph, tbox: TBoxManifest,
                lib: Optional[OntologyLibrary] = None) -> ABoxCensus:
    """A-Box 清点：类型合规、悬空边、domain/range、溯源、按论文分组。"""
    lib = lib or default_library()
    known_cls = set(tbox.classes)
    known_rel = set(tbox.relations) | LEGACY_ABOX_RELATIONS
    c = ABoxCensus(n_nodes=len(graph.nodes), n_assertions=len(graph.assertions))
    c.type_counts = dict(Counter(n.type for n in graph.nodes.values()))
    c.relation_counts = dict(Counter(a.relation for a in graph.assertions))
    c.undeclared_types = sorted(set(c.type_counts) - known_cls
                                - set(CLASS_ALIASES))
    c.undeclared_relations = sorted(set(c.relation_counts) - known_rel)
    ids = set(graph.nodes)
    c.dangling_edges = [f"{a.relation}:{a.source}->{a.target}"
                        for a in graph.assertions
                        if a.source not in ids or a.target not in ids][:20]
    # domain/range：按 T-Box 声明检查（GrOIL reasoner_report 的等价检查）
    for a in graph.assertions:
        spec = tbox.relations.get(a.relation)
        if not spec:
            continue
        dom, rng = spec[0], spec[1]
        st = graph.nodes.get(a.source)
        tt = graph.nodes.get(a.target)
        if st and not any(st.type == x.strip() or CLASS_ALIASES.get(st.type) == x.strip()
                          for x in dom.split("|")):
            c.domain_range_violations.append(
                f"{a.relation}: source {st.type} 不在 domain {dom}")
        if tt and not any(tt.type == x.strip() or CLASS_ALIASES.get(tt.type) == x.strip()
                          for x in rng.split("|")):
            c.domain_range_violations.append(
                f"{a.relation}: target {tt.type} 不在 range {rng}")
    c.domain_range_violations = c.domain_range_violations[:30]
    prov_keys = ("provenance", "source_paper", "paper_id", "merged_from")
    n_prov = sum(1 for n in graph.nodes.values()
                 if any(n.attrs.get(k) for k in prov_keys))
    c.provenance_coverage = round(n_prov / max(len(graph.nodes), 1), 3)
    # 按论文分组（GrOIL sourceContractID 的等价物）
    for p in graph.by_type("Paper"):
        aid = str(p.attrs.get("arxiv_id") or p.id.split(":")[-1])
        hit = lambda x: aid in x                       # noqa: E731
        nodes = [n for n in graph.nodes.values()
                 if hit(n.id) or aid in str(n.attrs.get("paper_id", ""))]
        edges = [a for a in graph.assertions
                 if hit(a.source) or hit(a.target)]
        types = {n.type for n in nodes}
        rels = {a.relation for a in edges}
        pt = str(p.attrs.get("paper_type") or "method")
        req = TYPE_REQUIREMENTS.get(pt, TYPE_REQUIREMENTS["method"])
        c.per_paper[aid] = {
            "paper_type": pt, "n_nodes": len(nodes), "n_edges": len(edges),
            "classes": len(types), "relations": len(rels),
            "missing_classes": [x for x in req["classes"] if x not in types],
            "missing_relations": [x for x in req["relations"] if x not in rels],
            "rate": round((len([x for x in req["classes"] if x in types]) +
                           len([x for x in req["relations"] if x in rels])) /
                          max(len(req["classes"]) + len(req["relations"]), 1), 3),
        }
    return c


def reasoning_readiness(graph: POGraph, tbox: TBoxManifest,
                        abox: ABoxCensus,
                        lib: Optional[OntologyLibrary] = None) -> Dict[str, Any]:
    """推理就绪度：形状校验 + 关系覆盖 + **真实跑一遍规则引擎**。"""
    lib = lib or default_library()
    shape = lib.validate(graph, scope="must_have")
    inv = lib.inventory(graph)
    derived, iterations, fixpoint, engine_error = 0, 0, False, ""
    try:
        from ..reasoning import ReasoningEngine, default_rules
        e = ReasoningEngine(graph)
        e.add_rules(default_rules())
        r = e.derive_all(max_iterations=12)
        derived, iterations, fixpoint = r["derived"], r["iterations"], r["reached_fixpoint"]
    except Exception as exc:                            # noqa: BLE001
        engine_error = f"{type(exc).__name__}: {exc}"
    n_viol = len(shape["violations"])
    score = round(
        0.3 * (1.0 if not tbox.issues else 0.0) +
        0.25 * inv["relation_coverage"] +
        0.25 * inv["class_coverage"] +
        0.2 * (1.0 if fixpoint and derived > 0 else 0.0), 3)
    return {"tbox_conforms": not tbox.issues,
            "shape_violations": n_viol, "shape_warnings": len(shape["warnings"]),
            "class_coverage": inv["class_coverage"],
            "relation_coverage": inv["relation_coverage"],
            "abox_violations": (len(abox.undeclared_types) +
                                len(abox.undeclared_relations) +
                                len(abox.dangling_edges) +
                                len(abox.domain_range_violations)),
            "provenance_coverage": abox.provenance_coverage,
            "rule_derived": derived, "rule_iterations": iterations,
            "fixpoint": fixpoint, "engine_error": engine_error,
            "readiness_score": score,
            "ready": not tbox.issues and n_viol == 0 and fixpoint and derived > 0}


def downstream_budget(abox: ABoxCensus, tbox: TBoxManifest,
                      contract: Dict[str, Any]) -> Dict[str, Any]:
    """给后续相位的可用原料与缺口（GrOIL CQ 查空 / coverage 的等价物）。"""
    gaps = [{"paper": aid, "type": d["paper_type"], "rate": d["rate"],
             "missing_classes": d["missing_classes"][:6],
             "missing_relations": d["missing_relations"][:6]}
            for aid, d in abox.per_paper.items() if d["rate"] < 1.0]
    gaps.sort(key=lambda x: x["rate"])
    return {
        "question": {"n_gap_papers": len(gaps), "top_gaps": gaps[:5],
                     "source": "ABox per-paper coverage（不是凭空造缺口）"},
        "proposal": {"type_requirements": tbox.type_requirements,
                     "closed_class_vocab": len(tbox.classes),
                     "closed_relation_vocab": len(tbox.relations)},
        "codegen": {"code_classes": {k: abox.type_counts.get(k, 0) for k in
                                     ("CodeRepository", "CodeModule", "CodeFunction",
                                      "EvaluationTool", "GroundingAlignment")},
                    "code_relations": {k: abox.relation_counts.get(k, 0) for k in
                                       ("REALIZES", "IMPLEMENTS_STEP", "CONTAINS_MODULE",
                                        "DEFINES_FUNCTION", "GROUNDS_TO")}},
        "reproduce": {"metric_definitions": abox.type_counts.get("MetricDefinition", 0),
                      "benchmarks": abox.type_counts.get("Benchmark", 0),
                      "observations": abox.type_counts.get("Observation", 0) +
                                      abox.type_counts.get("MetricObservation", 0),
                      "eval_relations": {k: abox.relation_counts.get(k, 0) for k in
                                         ("EVALUATED_ON", "REPORTS", "OF_METRIC",
                                          "SCORED_BY")}},
        "slice_chains": {c["chain"]: c["state"] for c in contract.get("chains", [])},
    }


@dataclass
class IntakeReport:
    """intake 的正式产物：T-Box + A-Box + 切片 + 就绪度 + 预算。"""
    tbox: TBoxManifest
    abox: ABoxCensus
    readiness: Dict[str, Any]
    budget: Dict[str, Any]
    contract: Dict[str, Any]
    slice_view: str = ""
    anchor: Optional[str] = None
    subgraph_nodes: int = 0
    subgraph_assertions: int = 0
    blockers: List[str] = field(default_factory=list)
    verdict: str = "PASS"

    def to_dict(self) -> Dict[str, Any]:
        return {"tbox": self.tbox.to_dict(), "abox": self.abox.to_dict(),
                "readiness": self.readiness, "budget": self.budget,
                "slice": {"view": self.slice_view, "anchor": self.anchor,
                          "nodes": self.subgraph_nodes,
                          "assertions": self.subgraph_assertions},
                "blockers": self.blockers, "verdict": self.verdict,
                "contract": self.contract}


def render_intake(report: IntakeReport) -> str:
    """给 LLM 的可读契约（零解释性幻觉，全部来自编译/清点结果）。"""
    t, a, r, b = report.tbox, report.abox, report.readiness, report.budget
    lines = ["# Intake Contract — T-Box / A-Box", "",
             "## T-Box（只读，编译产物）",
             f"- classes {t.n_classes} / relations {t.n_relations} / hash `{t.tbox_hash[:16]}`",
             f"- conforms: {not bool(t.issues)} | issues {len(t.issues)} | notes {len(t.notes)}",
             f"- must_have shapes: {t.shape_severities.get('Violation', 0)}",
             f"- 类型清单: {', '.join(sorted(t.type_requirements))}", "",
             "## A-Box（实例）",
             f"- nodes {a.n_nodes} / assertions {a.n_assertions}",
             f"- 溯源覆盖 {a.provenance_coverage}",
             f"- 未声明类型 {len(a.undeclared_types)} / 未声明关系 {len(a.undeclared_relations)}",
             f"- 悬空边 {len(a.dangling_edges)} / domain-range 违规 {len(a.domain_range_violations)}",
             f"- 按论文清点 {len(a.per_paper)} 篇", "",
             "## 推理就绪度",
             f"- score {r['readiness_score']} | ready {r['ready']}",
             f"- class {r['class_coverage']} / relation {r['relation_coverage']}",
             f"- 规则实跑: derived {r['rule_derived']} in {r['rule_iterations']} 轮, "
             f"fixpoint {r['fixpoint']}",
             f"- shape violations {r['shape_violations']} (must_have)", "",
             "## 下游预算",
             f"- question: {b['question']['n_gap_papers']} 篇有按类型缺口",
             f"- proposal: 封闭词表 {b['proposal']['closed_class_vocab']} 类 / "
             f"{b['proposal']['closed_relation_vocab']} 关系",
             f"- codegen: {b['codegen']['code_classes']}",
             f"- reproduce: {b['reproduce']['metric_definitions']} 指标 / "
             f"{b['reproduce']['benchmarks']} 基准", "",
             "## 组合链（三类根族，抽取上下文）",
             f"- {chains_summary()['groups']} 大类 / {chains_summary()['chains']} 条链 / "
             f"根族 {', '.join(chains_summary()['root_families'])} / "
             f"可抽取类 {chains_summary()['extractable_classes']}",
             "- 给 LLM 的是 `PAPER_CHAINS/<arxiv_id>.md`（该论文的链 + 缺环 + 抽取线索），",
             "  **不是** `TBOX_MANIFEST.json`（那是给程序与门用的全量编译产物）",
             f"- 步骤2 触手结果：{report.budget.get('tentacles', {}).get('summary', {})}",
             "",
             "## 任务切片",
             f"- view {report.slice_view} | anchor {report.anchor}",
             f"- subgraph {report.subgraph_nodes} 节点 / {report.subgraph_assertions} 断言",
             f"- 链状态: {b['slice_chains']}", "",
             "## 门",
             f"- verdict {report.verdict} | blockers {report.blockers}", ""]
    return "\n".join(lines)


def run_intake(graph: POGraph, *, view: str = "de_novo",
               anchor: Optional[str] = None,
               out_dir: Optional[str | Path] = None,
               lib: Optional[OntologyLibrary] = None,
               enable_tentacles: bool = True) -> IntakeReport:
    """Phase 0 两步：Step1 编译/清点/切片/推理；Step2 链束投影 + 触手抽取。"""
    lib = lib or default_library()
    tbox = compile_tbox(lib)
    abox = census_abox(graph, tbox, lib)
    sl = slice_for_task(graph, view, anchor=anchor)
    readiness = reasoning_readiness(graph, tbox, abox, lib)
    budget = downstream_budget(abox, tbox, sl.contract)

    # ---- Step 2：按论文投影组合链 + 三类触手抽取（不把 40 类全给模型）----
    from .tentacle import run_tentacles
    papers = [(str(n.attrs.get("arxiv_id") or n.id.split(":")[-1]), n.id)
              for n in graph.by_type("Paper")]
    repo_by_aid: Dict[str, str] = {}
    import pathlib as _pl
    sp = _pl.Path("storage_cf/sciforge/batch10_report.json")
    if sp.exists():
        with open(sp, encoding="utf-8") as fh:
            repo_by_aid = {x["arxiv_id"]: x.get("repo", "")
                           for x in json.load(fh).get("selected", [])}
    bundles = {aid: project_chains(graph, pid) for aid, pid in papers}
    budget["chains"] = {"groups": len(GROUPS), "chains": len(CHAINS),
                        "extractable_types": chains_summary()["extractable_classes"],
                        "per_paper": {aid: {"n_types": b["n_types"],
                                            "missing": len(b["missing_required"])}
                                      for aid, b in bundles.items()}}
    # 出处层不再在 intake 里建 Citation 条目（用户要求：参考文献不落图节点）。
    # 三类出处与三份 CSV 由独立的多阶段 pipeline 产出；这里只把产物挂进预算。
    from .sources import OUT_DIR as _SRC_OUT
    _src_index = _SRC_OUT / "SOURCE_INDEX.json"
    budget["sources"] = (
        json.load(open(_src_index, encoding="utf-8"))["by_kind"]
        if _src_index.exists() else
        {"status": "run_pipeline_required", "csv_paths":
         {k: str(v) for k, v in SOURCE_CSV_PATHS.items()}})
    budget["deep_dive_targets"] = []
    budget["stages"] = {k: {"root": v["root"],
                            "extensions": len(v["extensions"]),
                            "chains": len(v["chains"])}
                        for k, v in STAGES.items()}
    tent = (run_tentacles(graph, papers=papers, repo_by_aid=repo_by_aid,
                          out_dir=out_dir, write_back=True)
            if enable_tentacles else {"totals": {}, "papers": {}, "n_papers": 0})
    budget["tentacles"] = {"summary": tent.get("totals", {}),
                           "specs": TENTACLE_SPECS,
                           "papers_with_results": sum(
                               1 for v in tent.get("papers", {}).values()
                               if any(v.get(k) for k in
                                      ("algorithm", "metric_table", "algorithm_step")))}
    # 触手写回图后重新清点 + 重算预算，保证 budget/abox 数字一致
    abox = census_abox(graph, tbox, lib)
    readiness = reasoning_readiness(graph, tbox, abox, lib)
    # 重算时要保留 Step2 的两个附加段
    _extra = {k: budget[k] for k in ("chains", "tentacles", "sources",
                                     "deep_dive_targets", "stages")}
    budget = downstream_budget(abox, tbox, sl.contract)
    budget.update(_extra)
    has_paper = bool(graph.by_type("Paper"))
    ok = has_paper and len(sl.subgraph.nodes) > 0
    report = IntakeReport(
        tbox=tbox, abox=abox, readiness=readiness, budget=budget,
        contract=sl.contract, slice_view=sl.view, anchor=sl.anchor,
        subgraph_nodes=len(sl.subgraph.nodes),
        subgraph_assertions=len(sl.subgraph.assertions),
        blockers=list(sl.blockers),
        verdict="PASS" if ok else "BLOCKED")
    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "TBOX_MANIFEST.json").write_text(
            json.dumps(tbox.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "ABOX_CENSUS.json").write_text(
            json.dumps(abox.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "READINESS.json").write_text(
            json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "INTAKE_BUDGET.json").write_text(
            json.dumps(budget, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "INTAKE_CONTRACT.md").write_text(
            render_intake(report), encoding="utf-8")
        (out / "EXTRACTION_STAGES.json").write_text(json.dumps(
            {"stages": STAGES, "sources": budget.get("sources", {}),
             "deep_dive_targets": budget.get("deep_dive_targets", []),
             "source_csvs": {k: str(v) for k, v in SOURCE_CSV_PATHS.items()}},
            ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        (out / "TBOX_CHAINS.json").write_text(json.dumps(
            {"groups": GROUPS,
             "chains": {k: {"group": c.group, "root": c.root,
                            "purpose": c.purpose,
                            "steps": [st.__dict__ for st in c.steps]}
                        for k, c in CHAINS.items()},
             "tentacle_specs": TENTACLE_SPECS,
             "summary": chains_summary()},
            ensure_ascii=False, indent=2), encoding="utf-8")
        pc = out / "PAPER_CHAINS"
        pc.mkdir(parents=True, exist_ok=True)
        for aid, bundle in bundles.items():
            (pc / f"{aid}.md").write_text(render_chain_bundle(bundle),
                                          encoding="utf-8")
    return report
