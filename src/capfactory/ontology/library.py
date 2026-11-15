"""标准本体库：类/关系形状、按论文类型的抽取清单、覆盖率验证。

借鉴 semantica/ontology 的三个机制（纯 dict 复刻，无 rdflib/pyshacl）：
A ``ontology_generator.py:1109-1197`` 属性 domain 决定挂载、required → min_count；
B ``:1199-1219`` 形状继承有界迭代到稳定（20 轮 + path 去重）；
C ``ontology_validator.py:25-145`` 结构化违规报告 + 模板解释。

不借鉴其空壳：``OntologyValidator.validate`` / ``methods.py`` /
``ontology_provenance.py``（坏 import）/ pyshacl 强依赖路径。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .model import V2_CLASSES, V2_RELATIONS
from .layers import LAYER_CLASSES, relation_matrix as layer_relations
from .generation import GENERATION_CLASSES, relation_matrix as gen_relations
from .schema_v3 import V3_CLASSES, V3_RELATIONS, ROOT_FAMILIES

SEVERITY = {"must_have": "Violation", "should_have": "Warning",
            "optional": "Info"}


@dataclass
class PropertyShape:
    path: str
    min_count: int = 0
    max_count: Optional[int] = None
    target_class: str = ""
    severity: str = "Info"
    source: str = "extracted"          # extracted | derived | inherited
    origin: str = "field"              # field | relation


@dataclass
class NodeShape:
    target_class: str
    parent: str = ""
    props: Dict[str, PropertyShape] = field(default_factory=dict)
    closed: bool = False


@dataclass
class Violation:
    focus_node: str
    result_path: str
    constraint: str
    severity: str
    expected: str = ""
    actual: str = ""
    explanation: str = ""


def _all_relations() -> Dict[str, Tuple[str, str, str]]:
    out: Dict[str, Tuple[str, str, str]] = {}
    for name, v in V2_RELATIONS.items():
        out[name] = (v[0], v[1], "V2")
    for group in (layer_relations().values()):
        for name, v in group.items():
            out[name] = (v[0], v[1], v[2] if len(v) > 2 else "")
    for group in (gen_relations().values()):
        for name, v in group.items():
            out[name] = (v[0], v[1], v[2] if len(v) > 2 else "")
    for name, v in V3_RELATIONS.items():
        out[name] = (v[0], v[1], v[2])
    return out


# 按论文类型声明「应该抽到什么」。来自 paper_types.TYPE_FOCUS 的工程化映射。
TYPE_REQUIREMENTS: Dict[str, Dict[str, Any]] = {
    "method": {
        "classes": ["Paper", "Section", "ResearchQuestion", "Algorithm",
                    "MethodApplication", "DataForm", "AlgorithmComposition",
                    "AlgorithmStep", "Benchmark", "MetricDefinition",
                    "Observation", "CapabilityClaim", "Evidence",
                    "CodeRepository", "CodeModule", "CodeFunction",
                    "CausalGraph", "CausalNode", "ResearchObject"],
        "relations": ["HAS_SECTION", "ADDRESSES", "PARTICIPATES_IN", "CONSUMES",
                      "PRODUCES", "SCORED_BY", "HAS_COMPOSITION", "HAS_STEP",
                      "FLOWS_TO", "EVALUATED_ON", "REPORTS", "HAS_CODE",
                      "DECLARES_HYPOTHESIS", "HAS_FORMULA", "USES_TOOL",
                      "HAS_DATA_CONTRACT", "REPORTS_VALUE",
                      "IMPLEMENTS_STEP", "HAS_CAUSAL_GRAPH", "GROUNDS_TO"],
    },
    "dataset_benchmark": {
        "classes": ["Paper", "Section", "ResearchQuestion", "Benchmark",
                    "DataForm", "MetricDefinition", "Observation",
                    "ResearchObject", "Evidence"],
        "relations": ["HAS_SECTION", "ADDRESSES", "APPLIED_ON", "HAS_DATA_CONTRACT",
                      "HAS_INPUT_FORM", "HAS_OUTPUT_FORM", "REPORTS_VALUE", "HAS_INPUT_SCHEMA",
                      "HAS_OUTPUT_SCHEMA", "USES_METRIC", "REPORTS"],
    },
    "theory": {
        "classes": ["Paper", "Section", "ResearchQuestion", "CapabilityClaim",
                    "Evidence", "CausalGraph", "CausalNode"],
        "relations": ["HAS_SECTION", "ADDRESSES", "HAS_CAUSAL_GRAPH",
                      "HAS_CAUSAL_NODE", "SUPPORTED_BY"],
    },
    "system_tool": {
        "classes": ["Paper", "Section", "CodeRepository", "CodeModule",
                    "CodeFunction", "EvaluationTool", "Benchmark"],
        "relations": ["HAS_SECTION", "HAS_CODE", "CONTAINS_MODULE",
                      "DEFINES_FUNCTION", "BINDS_TOOL", "RUNS_ON"],
    },
    "survey": {
        "classes": ["Paper", "Section", "ResearchQuestion", "ProblemCategory",
                    "Algorithm", "Evidence"],
        "relations": ["HAS_SECTION", "ADDRESSES", "BROADER", "RELATED_TO"],
    },
}


class OntologyLibrary:
    """V3：44 类 / 90 关系（三类根族）+ 形状 + 覆盖率验证。"""

    def __init__(self) -> None:
        self.classes: Dict[str, Any] = {}
        for src in (V2_CLASSES, LAYER_CLASSES, GENERATION_CLASSES, V3_CLASSES):
            self.classes.update(src)
        self.relations = _all_relations()
        self.shapes = self._build_shapes()

    # -- A：字段三态 + 关系 domain → PropertyShape --------------------------
    def _build_shapes(self) -> Dict[str, NodeShape]:
        shapes = {c: NodeShape(target_class=c) for c in self.classes}
        for c, spec in self.classes.items():
            for f in spec.fields:
                shapes[c].props[f.name] = PropertyShape(
                    path=f.name, min_count=1 if f.level == "must_have" else 0,
                    severity=SEVERITY.get(f.level, "Info"),
                    source=f.source, origin="field")
        for rel, (dom, rng, note) in self.relations.items():
            if dom in shapes:
                shapes[dom].props.setdefault(rel, PropertyShape(
                    path=rel, min_count=0, target_class=rng,
                    severity="Info", source="extracted", origin="relation"))
        # 类层次：生成侧类继承核心层（简化的 parent 映射，用于形状继承演示）
        parents = {"ManuscriptSection": "Paper", "ClaimAnchor": "Evidence",
                   "Figure": "Evidence", "ReviewVerdict": "Evidence",
                   "ExperimentNode": "EvaluationRun",
                   "ReproductionResult": "Observation",
                   "CodeGenerationTask": "CodeRepository",
                   "RunPhase": "Paper"}
        for c, p in parents.items():
            if c in shapes and p in shapes:
                shapes[c].parent = p
        # -- B：有界迭代继承到稳定（20 轮上限 + path 去重）
        for _ in range(20):
            changed = False
            for c, s in shapes.items():
                if not s.parent or s.parent not in shapes:
                    continue
                for k, ps in shapes[s.parent].props.items():
                    if k not in s.props:
                        s.props[k] = PropertyShape(**{**ps.__dict__,
                                                     "source": "inherited"})
                        changed = True
            if not changed:
                break
        return shapes

    # -- C：结构化违规报告 -------------------------------------------------
    def validate(self, graph: Any, *, scope: str = "must_have"
                 ) -> Dict[str, Any]:
        allowed = {"must_have": ["Violation"],
                   "should_have": ["Violation", "Warning"],
                   "all": ["Violation", "Warning", "Info"]}[scope]
        out_edges: Dict[str, Set[str]] = {}
        for a in graph.assertions:
            out_edges.setdefault(a.source, set()).add(a.relation)
        issues: List[Violation] = []
        for n in graph.nodes.values():
            shape = self.shapes.get(n.type)
            if not shape:
                continue
            for path, ps in shape.props.items():
                if ps.severity not in allowed or ps.min_count <= 0:
                    continue
                val = n.attrs.get(path)
                has = val not in (None, "", [], {}) or path in out_edges.get(n.id, set())
                if not has:
                    issues.append(Violation(
                        focus_node=n.id, result_path=path,
                        constraint="MinCount", severity=ps.severity,
                        expected=f">= {ps.min_count}", actual="0",
                        explanation=f"{n.type} 的必填 {path}（{ps.source}）未填充"))
        by_sev: Dict[str, List[Dict[str, str]]] = {
            "violations": [], "warnings": [], "infos": []}
        key = {"Violation": "violations", "Warning": "warnings", "Info": "infos"}
        for i in issues:
            by_sev[key[i.severity]].append(i.__dict__)
        return {"conforms": not by_sev["violations"], **by_sev,
                "stats": {"nodes": len(graph.nodes), "issues": len(issues),
                          "classes": len(self.classes),
                          "relations": len(self.relations)}}

    # -- 按论文类型验证「填充完整度」 ---------------------------------------
    def coverage(self, graph: Any, *, paper_type: str,
                 paper_id: str = "") -> Dict[str, Any]:
        req = TYPE_REQUIREMENTS.get(paper_type, TYPE_REQUIREMENTS["method"])
        # 类按全图判定（共享概念如 Domain/DataForm 不归属单篇）；
        # 关系按该论文可达的断言判定，避免把全局实例误算成每篇都有。
        present_cls = {n.type for n in graph.nodes.values()}
        present_rel = {a.relation for a in graph.assertions
                       if not paper_id or paper_id in a.source or
                       paper_id in a.target}
        scoped_cls = {n.type for n in graph.nodes.values()
                      if paper_id and (paper_id in n.id or
                                       paper_id in str(n.attrs.get("paper_id", "")))}
        have_c = [c for c in req["classes"] if c in present_cls]
        missing_c = [c for c in req["classes"] if c not in present_cls]
        have_r = [r for r in req["relations"] if r in present_rel]
        missing_r = [r for r in req["relations"] if r not in present_rel]
        total = len(req["classes"]) + len(req["relations"])
        return {"paper_id": paper_id, "paper_type": paper_type,
                "scoped_classes": len(scoped_cls),
                "classes_required": len(req["classes"]),
                "classes_present": len(have_c), "classes_missing": missing_c,
                "relations_required": len(req["relations"]),
                "relations_present": len(have_r), "relations_missing": missing_r,
                "complete": not missing_c and not missing_r,
                "rate": round((len(have_c) + len(have_r)) / max(total, 1), 3)}

    def inventory(self, graph: Any) -> Dict[str, Any]:
        used_c = {n.type for n in graph.nodes.values()}
        used_r = {a.relation for a in graph.assertions}
        return {"classes": len(self.classes), "relations": len(self.relations),
                "unused_classes": sorted(set(self.classes) - used_c),
                "unused_relations": sorted(set(self.relations) - used_r),
                "class_coverage": round(len(used_c & set(self.classes)) /
                                        max(len(self.classes), 1), 3),
                "relation_coverage": round(len(used_r & set(self.relations)) /
                                           max(len(self.relations), 1), 3)}

    def to_dict(self) -> Dict[str, Any]:
        return {"classes": {c: {"fields": [f.name for f in s.fields],
                                "layer": s.layer}
                            for c, s in self.classes.items()},
                "relations": {r: list(v[:2]) for r, v in self.relations.items()},
                "type_requirements": TYPE_REQUIREMENTS,
                "shapes": {c: {k: v.severity for k, v in s.props.items()}
                           for c, s in self.shapes.items()}}


def default_library() -> OntologyLibrary:
    return OntologyLibrary()
