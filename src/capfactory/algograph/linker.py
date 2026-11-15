"""L3 对齐层：论文方法模块 ↔ 代码单元的 Grounding（CAD §3.3 / 附录 A）。

规则与论文一致：
* **代码推导的 inference 因果图是 ground truth**；
* 每个 code 节点找唯一最佳 paper 节点，每个 paper 节点最多被消费一次；
* 匹配对打 ``Agreement(High/Partial/Low)`` 与 ``Paper-too-abstract``；
* 未匹配 code 节点分 ``conceptual gap``（论文漏写核心机制）与
  ``implementation gap``（dtype / 并行 / API 等代码细节）；
* 输出 7 列 TSV 表。

与论文不同：P0 提供**确定性打分器**（causal_type + 名称 + 结构位置 + 证据锚定），
不依赖 LLM-as-judge，规避 §6 的自评偏差；LLM 可作为可选增强覆盖分数但必须留痕。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from ..kg.retrieval import tokenize
from .schema import CONCEPTUAL_GAP_TYPES, IMPLEMENTATION_HINTS, CAUSAL_PRIORITY
from .store import AlgoGraph

TSV_HEADER = ("Code Node", "Node Type", "Diagram", "Paper equivalent",
              "Agreement", "Gap Type", "Paper-too-abstract")


@dataclass
class GroundingRow:
    code_node: str
    node_type: str
    diagram: str = "inference"
    paper_equivalent: str = "Not present"
    agreement: str = ""
    gap_type: str = ""
    paper_too_abstract: str = ""
    score: float = 0.0
    code_qn: str = ""
    paper_qn: str = ""

    def tsv(self) -> str:
        return "\t".join((self.code_node, self.node_type, self.diagram,
                          self.paper_equivalent, self.agreement, self.gap_type,
                          self.paper_too_abstract))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _tokens(text: str) -> Set[str]:
    return set(tokenize(text or ""))


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class GroundingEngine:
    """一对一贪心对齐。``min_score`` 以下视为未匹配。"""

    def __init__(self, *, min_score: float = 0.42):
        self.min_score = min_score

    def ground(self, g: AlgoGraph, *, phase: str = "inference",
               level: str = "micro", code_phases: Optional[Sequence[str]] = None) -> Dict[str, Any]:
        # CAD 取 inference 子图；但无训练过程的算法会被标成 init/operational，
        # 二者同属「执行图」，默认全部纳入，避免漏掉数据加载与初始化机制。
        allowed = set(code_phases) if code_phases else None
        code_nodes = [n for n in g.by_type("causal_node")
                      if n.get("source_modality") == "code"
                      and n.get("abstraction") == level
                      and (allowed is None or n.get("phase") in allowed)]
        paper_nodes = [n for n in g.by_type("causal_node")
                       if n.get("source_modality") == "paper"
                       and n.get("abstraction") == level and n.get("phase") == phase]
        if not code_nodes:
            return {"rows": [], "summary": {"grounding_coverage": 0.0,
                                            "reason": "code 侧无 inference micro 节点"}}

        predecessors = self._context_types(g, incoming=True)
        successors = self._context_types(g, incoming=False)

        scored: List[Tuple[float, Any, Any, Dict[str, float]]] = []
        for c in code_nodes:
            ct = str(c.get("causal_type"))
            cname = _tokens(f"{c.get('name','')} {c.label}")
            for p in paper_nodes:
                same_type = 1.0 if ct == str(p.get("causal_type")) else 0.0
                name_sim = _jaccard(cname, _tokens(f"{p.get('name','')} {p.label}"))
                ctx_sim = max(
                    _jaccard(predecessors.get(c.qn, set()), predecessors.get(p.qn, set())),
                    _jaccard(successors.get(c.qn, set()), successors.get(p.qn, set())))
                anchored = 1.0 if self._anchored(g, p) else 0.0
                parts = {"same_type": 0.40 * same_type, "name": 0.35 * name_sim,
                         "context": 0.15 * ctx_sim, "evidence": 0.10 * anchored}
                score = sum(parts.values())
                # 硬约束：仅「类型相同 + 已锚定」不足以证明是同一个因果概念，
                # 必须还有名称或结构位置的实际重合，避免把 RAPiDock 误配给任意 mechanism。
                if name_sim <= 0 and ctx_sim <= 0:
                    continue
                if score >= self.min_score:
                    scored.append((score, c, p, parts))
        scored.sort(key=lambda x: -x[0])

        used_paper: Set[str] = set()
        matches: Dict[str, Tuple[Any, float, Dict[str, float]]] = {}
        for score, c, p, parts in scored:
            if c.qn in matches or p.qn in used_paper:
                continue
            matches[c.qn] = (p, score, parts)
            used_paper.add(p.qn)

        rows: List[GroundingRow] = []
        for c in sorted(code_nodes, key=lambda n: (CAUSAL_PRIORITY.index(str(n.get("causal_type")))
                                                   if n.get("causal_type") in CAUSAL_PRIORITY else 9,
                                                   n.qn)):
            ct = str(c.get("causal_type"))
            if c.qn in matches:
                p, score, parts = matches[c.qn]
                agreement = "High" if score >= 0.70 else ("Partial" if score >= 0.45 else "Low")
                too_abstract = self._too_abstract(g, p)
                row = GroundingRow(
                    code_node=c.label, node_type=ct, diagram=str(c.get("phase")),
                    paper_equivalent=p.label, agreement=agreement, gap_type="No gap",
                    paper_too_abstract=too_abstract, score=round(score, 4),
                    code_qn=c.qn, paper_qn=p.qn)
                g.add_edge(c.qn, p.qn, "GROUNDS_TO", agreement=agreement,
                           paper_too_abstract=too_abstract, score=round(score, 4),
                           components={k: round(v, 4) for k, v in parts.items()})
            else:
                gap = self._gap_type(c, g)
                row = GroundingRow(
                    code_node=c.label, node_type=ct, diagram=str(c.get("phase")),
                    paper_equivalent="Not present", agreement="", gap_type=gap,
                    paper_too_abstract="", score=0.0, code_qn=c.qn)
            rows.append(row)

        unmatched_paper = [{"qn": p.qn, "label": p.label,
                            "causal_type": p.get("causal_type"),
                            "priority": (CAUSAL_PRIORITY.index(str(p.get("causal_type")))
                                         if p.get("causal_type") in CAUSAL_PRIORITY else 9)}
                           for p in paper_nodes if p.qn not in used_paper]
        unmatched_paper.sort(key=lambda x: x["priority"])
        summary = {
            "n_code_nodes": len(code_nodes), "n_paper_nodes": len(paper_nodes),
            "matched": len(matches),
            "grounding_coverage": round(len(matches) / len(code_nodes), 4),
            "gap_distribution": {
                "conceptual": sum(1 for r in rows if r.gap_type == "conceptual gap"),
                "implementation": sum(1 for r in rows if r.gap_type == "implementation gap"),
                "no_gap": sum(1 for r in rows if r.gap_type == "No gap"),
            },
            "unmatched_paper_nodes": unmatched_paper,
            "conceptual_gaps": [r.code_node for r in rows if r.gap_type == "conceptual gap"],
            "implementation_gaps": [r.code_node for r in rows if r.gap_type == "implementation gap"],
            "min_score": self.min_score,
            "note": "论文宣称但代码缺失的节点（unmatched_paper_nodes）是最高优先复现缺口",
        }
        g.meta["grounding"] = {k: v for k, v in summary.items()
                               if k not in ("unmatched_paper_nodes", "conceptual_gaps",
                                            "implementation_gaps")}
        return {
            "rows": [r.to_dict() for r in rows],
            "tsv": "\t".join(TSV_HEADER) + "\n" + "\n".join(r.tsv() for r in rows),
            "summary": summary,
        }

    # -- 内部 -------------------------------------------------------------
    @staticmethod
    def _context_types(g: AlgoGraph, *, incoming: bool) -> Dict[str, Set[str]]:
        out: Dict[str, Set[str]] = {}
        for e in g.edges:
            if e.type != "CAUSES":
                continue
            src = g.nodes.get(e.source)
            tgt = g.nodes.get(e.target)
            if not src or not tgt:
                continue
            if incoming:
                out.setdefault(e.target, set()).add(str(src.get("causal_type")))
            else:
                out.setdefault(e.source, set()).add(str(tgt.get("causal_type")))
        return out

    @staticmethod
    def _anchored(g: AlgoGraph, paper_node: Any) -> bool:
        pm = g.nodes.get(str(paper_node.get("evidence", "")))
        return bool(pm and pm.get("anchored"))

    @staticmethod
    def _too_abstract(g: AlgoGraph, paper_node: Any) -> str:
        pm = g.nodes.get(str(paper_node.get("evidence", "")))
        text = f"{pm.get('method_text','') if pm else ''} {pm.get('quote','') if pm else ''}"
        concrete = bool(re.search(r"\d+\.\d+|\b=\b|alpha|threshold|layer|epoch|learning rate",
                                  text, re.I))
        if concrete:
            return "No"
        return "Yes" if float(paper_node.confidence) < 0.6 else "Partial"

    @staticmethod
    def _gap_type(code_node: Any, g: AlgoGraph) -> str:
        ct = str(code_node.get("causal_type"))
        label = f"{code_node.label} {code_node.get('name','')}".lower()
        evidence = str(code_node.get("evidence", ""))
        impl = g.nodes.get(evidence)
        content = str(impl.get("content", ""))[:1200].lower() if impl else ""
        for hint in IMPLEMENTATION_HINTS:
            # 带下划线后缀的 hint 用子串匹配；其余用词边界，
            # 避免 "io" 命中 "decision"、"eps" 命中 "steps" 这类误判
            if hint.endswith("_") or hint.startswith("."):
                hit = hint in label or hint in content
            else:
                rx = re.compile(r"(?<![a-z])" + re.escape(hint) + r"(?![a-z])", re.I)
                hit = bool(rx.search(label) or rx.search(content))
            if hit:
                return "implementation gap"
        return "conceptual gap" if ct in CONCEPTUAL_GAP_TYPES else "implementation gap"
