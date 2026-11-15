"""CapabilityVersion：把一份代码工件、三层细粒度图、对齐结果与验证断言绑成一体.

对应需求中的「一个 CapabilityVersion 中的代码文件」：
一个能力可以有多个版本，每个版本持有独立的
L1 结构图 / L2 因果图 / L3 grounding / TestCase·MetricBinding，
并可投影进主能力知识图谱。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from ..utils import now_iso
from .callgraph import CallGraphBuilder
from .causal import CausalAnnotator
from .linker import GroundingEngine
from .parser import CodeGraphBuilder
from .schema import CAUSAL_PRIORITY, make_qn, stable_hash
from .store import AlgoGraph


@dataclass
class MetricBinding:
    """指标 ↔ 语义节点的绑定；``role=gate`` 必须绑 decision/parameter。"""

    metric_name: str
    role: str = "gate"                 # gate | advisory
    threshold: float = 0.0
    direction: str = "higher"
    description: str = ""
    target_causal_types: List[str] = field(default_factory=lambda: ["decision", "parameter"])

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MetricBinding":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (d or {}).items() if k in known})


@dataclass
class TestCase:
    """一条可映射到代码单元的断言（需求：拆解出的关键单元能直接映射到 TestCase）。"""

    id: str
    assertion: str
    metric_name: str = ""
    role: str = "gate"
    line: Optional[int] = None
    target_qn: str = ""
    description: str = ""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TestCase":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (d or {}).items() if k in known})


@dataclass
class CapabilityVersion:
    """一个可复现的能力版本。"""

    version_id: str
    capability_id: str
    code_path: str = ""
    source_hash: str = ""
    parent_version: str = ""
    graph: AlgoGraph = field(default_factory=AlgoGraph)
    grounding: Dict[str, Any] = field(default_factory=dict)
    verification: Dict[str, Any] = field(default_factory=dict)
    metric_bindings: List[MetricBinding] = field(default_factory=list)
    test_cases: List[TestCase] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    notes: List[str] = field(default_factory=list)

    # -- 视图 -------------------------------------------------------------
    def stats(self) -> Dict[str, Any]:
        s = self.graph.stats()
        s.update({
            "version_id": self.version_id, "capability_id": self.capability_id,
            "grounding_coverage": (self.grounding.get("summary") or {}).get(
                "grounding_coverage", 0.0),
            "gate_metrics": [m.metric_name for m in self.metric_bindings if m.role == "gate"],
            "n_test_cases": len(self.test_cases),
            "verified": bool(self.verification.get("passed")),
        })
        return s

    def to_dict(self, *, include_graph: bool = True) -> Dict[str, Any]:
        return {
            "version_id": self.version_id, "capability_id": self.capability_id,
            "code_path": self.code_path, "source_hash": self.source_hash,
            "parent_version": self.parent_version,
            "graph": self.graph.to_dict() if include_graph else {"meta": self.graph.meta,
                                                                "node_count": len(self.graph.nodes)},
            "grounding": self.grounding, "verification": self.verification,
            "metric_bindings": [asdict(m) for m in self.metric_bindings],
            "test_cases": [asdict(t) for t in self.test_cases],
            "created_at": self.created_at, "notes": self.notes,
            "stats": self.stats(),
        }

    def save(self, path: Union[str, Path]) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                     encoding="utf-8")
        self.graph.save(p.with_suffix(".graph.json"))
        return p

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CapabilityVersion":
        raw_graph = d.get("graph") or {}
        graph = (AlgoGraph.from_dict(raw_graph) if isinstance(raw_graph, dict)
                 and "nodes" in raw_graph else AlgoGraph())
        known = {f.name for f in fields(cls)}
        data = {k: v for k, v in d.items() if k in known and k not in
                ("graph", "metric_bindings", "test_cases")}
        return cls(
            graph=graph,
            metric_bindings=[MetricBinding.from_dict(m) for m in d.get("metric_bindings") or []],
            test_cases=[TestCase.from_dict(t) for t in d.get("test_cases") or []],
            **data,
        )

    # -- 查询 -------------------------------------------------------------
    def modules_and_gaps(self) -> Dict[str, Any]:
        """复现任务清单：论文宣称但代码缺失的模块（最高优先）+ 代码侧概念缺口。"""
        summary = self.grounding.get("summary") or {}
        return {
            "unmatched_paper_modules": summary.get("unmatched_paper_nodes", []),
            "conceptual_gaps": summary.get("conceptual_gaps", []),
            "implementation_gaps": summary.get("implementation_gaps", []),
            "grounding_coverage": summary.get("grounding_coverage", 0.0),
            "next_actions": [
                {"action": "reproduce_paper_module", "target": x["label"],
                 "priority": 1, "reason": "论文声明该机制但代码中无对应节点"}
                for x in summary.get("unmatched_paper_nodes", [])[:10]
            ],
        }

    def gate_bindings(self) -> List[Dict[str, Any]]:
        out = []
        for m in self.metric_bindings:
            if m.role != "gate":
                continue
            targets = [e.target for e in self.graph.outgoing(
                make_qn("metric", self.version_id, m.metric_name), "ASSERTS")]
            out.append({"metric": m.metric_name, "threshold": m.threshold,
                        "direction": m.direction, "bound_nodes": targets})
        return out


# ---------------------------------------------------------------------------
# 一站式构建
# ---------------------------------------------------------------------------
def build_capability_version(
    capability_id: str,
    sources: Union[str, Dict[str, str]],
    *,
    code_path: str = "",
    version_id: str = "",
    paper_modules: Optional[Sequence[Dict[str, Any]]] = None,
    metric_bindings: Sequence[Union[Dict[str, Any], MetricBinding]] = (),
    test_cases: Sequence[Union[Dict[str, Any], TestCase]] = (),
    include_blocks: bool = True,
    parent_version: str = "",
) -> CapabilityVersion:
    """从 Python 源码 + 论文方法模块构建完整 CapabilityVersion。

    流程：PKG 结构拆解 → 两阶段调用图 → 七类语义标注 → 构造式层级
    → 论文/代码 Grounding → gate 断言绑定 → 版本容器。
    """
    if isinstance(sources, str):
        first = Path(code_path).stem if code_path else capability_id
        sources = {first: sources}
    sources = {str(k): str(v) for k, v in sources.items()}
    source_hash = stable_hash(*[f"{k}:{stable_hash(v)}" for k, v in sources.items()])
    vid = version_id or make_qn("cv", capability_id, source_hash)

    graph = AlgoGraph(make_qn("algograph", vid))
    builder = CodeGraphBuilder(include_blocks=include_blocks)
    for mod_qn, src in sources.items():
        try:
            builder.build(src, mod_qn, path=code_path, graph=graph)
        except SyntaxError as exc:
            graph.meta.setdefault("parse_errors", []).append(f"{mod_qn}: {exc}")
    CallGraphBuilder().enrich(graph, sources)

    annotator = CausalAnnotator()
    annotator.annotate_code(graph, include_blocks=include_blocks)
    if paper_modules:
        annotator.annotate_paper(graph, paper_modules)
    annotator.build_causal_edges(graph)
    hierarchy = annotator.build_hierarchy(graph)

    grounding = GroundingEngine().ground(graph) if paper_modules else {
        "rows": [], "tsv": "", "summary": {"grounding_coverage": 0.0,
                                           "reason": "未提供论文方法模块"}}

    cv = CapabilityVersion(
        version_id=vid, capability_id=capability_id, code_path=code_path,
        source_hash=source_hash, parent_version=parent_version, graph=graph,
        grounding=grounding,
        metric_bindings=[m if isinstance(m, MetricBinding) else MetricBinding.from_dict(m)
                         for m in metric_bindings],
        test_cases=[t if isinstance(t, TestCase) else TestCase.from_dict(t)
                    for t in test_cases],
    )
    cv.notes.append(f"hierarchy: meso={len(hierarchy['meso'])} macro={len(hierarchy['macro'])} "
                    f"orphans={len(hierarchy['orphans'])}")

    # 版本节点与归属
    vqn = make_qn("capability_version", vid)
    graph.node(vqn, "capability_version", capability_id,
               version_id=vid, source_hash=source_hash, capability_id=capability_id,
               code_path=code_path, granularity="version")
    graph.nodes[vqn].layer = "container"
    for n in graph.by_type("func_name") + graph.by_type("paper_module"):
        graph.add_edge(n.qn, vqn, "PART_OF")

    _bind_assertions(cv)
    problems = graph.validate()
    cv.notes.extend(problems[:20])
    graph.meta["validation_problems"] = problems
    return cv


def _bind_assertions(cv: CapabilityVersion) -> None:
    """把 gate 指标绑定到 decision/parameter 节点；TestCase 绑定到具体代码单元。"""
    g = cv.graph
    micro = [n for n in g.by_type("causal_node")
             if n.get("abstraction") == "micro" and n.get("source_modality") == "code"]
    ordered = sorted(micro, key=lambda n: (
        CAUSAL_PRIORITY.index(str(n.get("causal_type")))
        if n.get("causal_type") in CAUSAL_PRIORITY else 9, n.qn))

    for m in cv.metric_bindings:
        mqn = make_qn("metric", cv.version_id, m.metric_name)
        g.node(mqn, "metric_binding", m.metric_name,
               metric_name=m.metric_name, role=m.role, threshold=m.threshold,
               direction=m.direction, description=m.description, granularity="assertion")
        g.nodes[mqn].layer = "verification"
        targets = [n for n in ordered if n.get("causal_type") in m.target_causal_types][:3]
        if not targets:
            if m.role == "gate":
                # 不创建误导性绑定：不变量 7 会明确报出「gate 未绑定 decision/parameter」
                cv.notes.append(f"gate 指标 {m.metric_name} 无 decision/parameter 节点可绑定")
                continue
            targets = ordered[:1]
        for t in targets:
            g.add_edge(mqn, t.qn, "ASSERTS", role=m.role, threshold=m.threshold)
        # 指标节点也指向版本，便于从版本反查所有 gate
        g.add_edge(mqn, make_qn("capability_version", cv.version_id), "PART_OF")

    for t in cv.test_cases:
        tqn = make_qn("testcase", cv.version_id, t.id)
        g.node(tqn, "test_case", t.id, assertion=t.assertion,
               metric_name=t.metric_name, role=t.role, line=t.line,
               description=t.description, granularity="assertion")
        g.nodes[tqn].layer = "verification"
        target = t.target_qn if t.target_qn in g.nodes else ""
        if not target and t.line:
            for b in g.by_type("code_block"):
                if int(b.get("start_line") or 0) <= t.line <= int(b.get("end_line") or 0):
                    target = b.qn
                    break
        if not target:
            for n in ordered:
                if n.get("causal_type") in ("decision", "parameter"):
                    target = n.qn
                    break
        if target:
            g.add_edge(tqn, target, "ASSERTS", role=t.role, assertion=t.assertion)
