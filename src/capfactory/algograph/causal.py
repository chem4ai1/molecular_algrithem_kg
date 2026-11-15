"""L2 语义层：Causal Algorithm Design 七类本体 + 构造式多分辨率层级.

对应 ``ref/code-anlysis.pdf``：
* 七类受控词表 input/parameter/mechanism/state/aggregation/decision/output；
* training / inference 双阶段（无训练时 init / operational）；
* micro(12–25) → meso(7–10) → macro(4–7) **构造式**层级
  （§5.3：12 胜 2 平 0 负，覆盖率 93.7%→99.8%，离群 70→2）；
* Mermaid ``flowchart TB`` 作为可解析表面形式，解析器容忍
  ``Table N header:`` 标记与丢表头（§5.2 报告的两个真实格式风险）。

与论文不同的是：P0 用**确定性规则标注器**而不是 LLM，规避 §6 的
LLM-as-judge 偏差与单模型依赖；LLM 仅作为可选增强且必须留痕。
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .schema import (
    ABSTRACTIONS, CAUSAL_TYPES, CAUSAL_PRIORITY, PHASES, make_qn, stable_hash,
)
from .store import AlgoGraph

CAUSAL_RULES: Tuple[Tuple[str, str, float], ...] = (
    ("decision", r"(^|_)(apply[_-]?threshold|gate|filter|select|decide|threshold|judge|route|check)(_|$)|"
                 r"\bthreshold\b|\bgating\b", 1.15),
    ("input", r"(^|_)(load|read|parse|ingest|fetch|open|import|collect|get)(_|$)|"
              r"\bfasta\b|\bread_csv\b|\bdataset\b", 1.0),
    ("output", r"(^|_)(format|write|save|dump|export|emit|render|serialize|report)(_|$)", 0.95),
    ("aggregation", r"(^|_)(aggregate|mean|sum|stack|ensemble|vote|concat|merge|pool|reduce|fuse)(_|$)|"
                    r"\baverage\b", 1.0),
    ("mechanism", r"(^|_)(encode|featurize|train|fit|forward|predict|dock|align|embed|transform|"
                  r"compute|build[_-]?model|score|classify|infer)(_|$)|\bmodel\b|\bembedding\b", 1.0),
    ("state", r"(^|_)(state|cache|buffer|update|accumulate|running|history|memory|hidden)(_|$)", 0.9),
    ("parameter", r"(^|_)(config|hyper|param|setup|init|configure|hyperparameter)(_|$)|"
                  r"\bkwargs\b|\balpha\b", 0.9),
)
TRAIN_RE = re.compile(r"(^|_)(fit|train|learn|fit_transform|optimize|backprop)(_|$)", re.I)
INIT_RE = re.compile(r"(^|_)(init|setup|prepare|build|configure|load|read|parse)(_|$)", re.I)
COMPARE_RE = re.compile(r"(>=|<=|==|!=|>|<|\bis\b|\bin\b|\bnot\b)")
DECISION_BRANCH_RE = re.compile(r"\b(return|append|raise|break|continue|pass)\b")

CAUSAL_COLORS = {
    "input": "#dae8fc", "parameter": "#ffe6cc", "mechanism": "#d5e8d4",
    "state": "#fff2cc", "aggregation": "#e1d5e7", "decision": "#f8cecc",
    "output": "#f5f5f5",
}

CAUSAL_ORDER = {"input": 0, "parameter": 1, "mechanism": 2, "state": 3,
                "aggregation": 4, "decision": 5, "output": 6}
MACRO_SEGMENTS = (
    ("upstream", ("input", "parameter")),
    ("core", ("mechanism", "state", "aggregation")),
    ("downstream", ("decision", "output")),
)


def classify(name: str, docstring: str = "", content: str = "") -> Tuple[str, float, str]:
    """确定性语义标注：返回 ``(causal_type, confidence, matched_rule)``。"""
    scores: Dict[str, float] = defaultdict(float)
    matched: Dict[str, str] = {}
    for ctype, pattern, weight in CAUSAL_RULES:
        rx = re.compile(pattern, re.I)
        if rx.search(name or ""):
            scores[ctype] += weight
            matched.setdefault(ctype, f"name:{pattern[:32]}")
        if docstring and rx.search(docstring[:300]):
            scores[ctype] += weight * 0.25
            matched.setdefault(ctype, f"doc:{pattern[:32]}")
    low = (content or "")[:2500].lower()
    if low:
        if COMPARE_RE.search(low) and DECISION_BRANCH_RE.search(low):
            scores["decision"] += 0.45
            matched.setdefault("decision", "content:compare+branch")
        if re.search(r"\bfor\b|\bwhile\b", low) and re.search(r"\+=|sum\(|mean\(|append\(", low):
            scores["aggregation"] += 0.30
        if re.search(r"\bself\.|\bcache\b|\bbuffer\b", low):
            scores["state"] += 0.25
    if not scores:
        return "mechanism", 0.35, "default:mechanism"
    best = max(scores, key=lambda k: (scores[k], -CAUSAL_ORDER[k]))
    confidence = min(0.98, 0.45 + 0.25 * scores[best])
    return best, round(confidence, 3), matched.get(best, "content-heuristic")


def infer_phase(name: str, *, has_training: bool = True) -> str:
    if TRAIN_RE.search(name or ""):
        return "training"
    if not has_training:
        return "init" if INIT_RE.search(name or "") else "operational"
    return "inference"


def _causal_qn(modality: str, phase: str, level: str, key: str) -> str:
    return make_qn("causal", modality, phase, level, f"{key}_{stable_hash(key, length=6)}")


class CausalAnnotator:
    """把结构层单元标注为七类因果节点，并构造式生成 meso/macro。"""

    def __init__(self, *, max_block_nodes_per_function: int = 2):
        self.max_block_nodes = max_block_nodes_per_function

    # -- 代码侧 -----------------------------------------------------------
    def annotate_code(self, g: AlgoGraph, *, include_blocks: bool = True) -> List[str]:
        """返回新建 micro 节点 qn 列表。"""
        names = g.by_type("func_name")
        has_training = any(TRAIN_RE.search(n.get("name", "")) for n in names)
        micro: List[str] = []
        impl_by_func = {n.get("function_id"): n.qn for n in g.by_type("implementation")
                        if n.get("function_id")}

        for fn in names:
            fqn = fn.qn
            ctype, conf, rule = classify(fn.get("name", ""), fn.get("docstring", ""),
                                         (g.nodes.get(impl_by_func.get(fqn, "")) or fn).get("content", ""))
            phase = infer_phase(fn.get("name", ""), has_training=has_training)
            key = f"{fn.get('name','fn')}:{fqn}"
            qn = _causal_qn("code", phase, "micro", key)
            g.node(qn, "causal_node", f"{fn.label} [{ctype}]",
                   causal_type=ctype, phase=phase, abstraction="micro",
                   source_modality="code", mermaid_id=f"n{stable_hash(qn, length=8)}",
                   evidence=fqn, rule=rule, name=fn.get("name", ""),
                   granularity="causal")
            g.nodes[qn].confidence = conf
            g.nodes[qn].layer = "causal"
            g.add_edge(impl_by_func.get(fqn, fqn), qn, "REALIZES",
                       rule=rule, confidence=conf)
            micro.append(qn)

            # 关键决策块下钻：if/elif/case 且含比较与分支动作
            if include_blocks:
                n_blocks = 0
                for b in g.by_type("code_block"):
                    if b.get("function_id") != fqn or b.get("block_kind") not in ("if", "elif", "case"):
                        continue
                    content = b.get("content", "")
                    if not (COMPARE_RE.search(content) and DECISION_BRANCH_RE.search(content)):
                        continue
                    if n_blocks >= self.max_block_nodes:
                        break
                    bkey = f"{fn.get('name','fn')}:block:{b.qn}"
                    bqn = _causal_qn("code", phase, "micro", bkey)
                    g.node(bqn, "causal_node", f"{b.label} [decision]",
                           causal_type="decision", phase=phase, abstraction="micro",
                           source_modality="code", mermaid_id=f"n{stable_hash(bqn, length=8)}",
                           evidence=b.qn, rule="block:compare+branch", name=fn.get("name", ""),
                           block_kind=b.get("block_kind"), granularity="causal")
                    g.nodes[bqn].confidence = 0.82
                    g.nodes[bqn].layer = "causal"
                    g.add_edge(b.qn, bqn, "REALIZES", rule="block:compare+branch")
                    micro.append(bqn)
                    n_blocks += 1
        return micro

    # -- 论文侧 -----------------------------------------------------------
    def annotate_paper(self, g: AlgoGraph,
                       modules: Sequence[Dict[str, Any]]) -> List[str]:
        """``modules: [{id,title,text,locator,quote,source_id,source_text?}]``。"""
        micro: List[str] = []
        phase = "inference"
        for i, m in enumerate(modules):
            source_id = str(m.get("source_id") or "paper")
            pq = make_qn("paper", source_id, f"m{i}")
            text = str(m.get("text") or m.get("title") or "")
            quote = str(m.get("quote") or "")
            anchored = bool(m.get("anchored"))
            src = str(m.get("source_text") or "")
            if not anchored and quote and src:
                anchored = re.sub(r"\s+", " ", quote).strip() in re.sub(r"\s+", " ", src)
            g.node(pq, "paper_module", str(m.get("title") or f"module {i}")[:120],
                   section=str(m.get("locator") or ""), quote=quote[:500],
                   anchored=anchored, method_text=text[:2000], source_id=source_id,
                   granularity="paper")
            g.nodes[pq].layer = "alignment"
            candidates = re.split(r"(?<=[.;])\s+|\n+", text)
            chosen: List[Tuple[str, float, str]] = []
            for sent in candidates:
                if len(sent.strip()) < 12:
                    continue
                slug = re.sub(r"[^A-Za-z0-9]+", "_", sent.strip().lower())[:28].strip("_")
                ct, conf, rule = classify(slug, "", sent)
                chosen.append((ct, conf, rule))
                if len(chosen) >= 3:
                    break
            if not chosen:
                chosen = [("mechanism", 0.4, "fallback")]
            for j, (ct, conf, rule) in enumerate(chosen):
                key = f"{source_id}:m{i}:{j}:{ct}"
                qn = _causal_qn("paper", phase, "micro", key)
                g.node(qn, "causal_node", f"{m.get('title','module')[:40]} [{ct}]",
                       causal_type=ct, phase=phase, abstraction="micro",
                       source_modality="paper", mermaid_id=f"n{stable_hash(qn, length=8)}",
                       evidence=pq, rule=rule, name=str(m.get("title") or "")[:80],
                       granularity="causal")
                g.nodes[qn].confidence = round(conf * (1.0 if anchored else 0.7), 3)
                g.nodes[qn].layer = "causal"
                g.add_edge(pq, qn, "SPECIFIES", locator=str(m.get("locator") or ""),
                           anchored=anchored)
                micro.append(qn)
        return micro

    # -- 因果边 + 构造式层级 -----------------------------------------------
    def build_causal_edges(self, g: AlgoGraph) -> int:
        """micro 节点间 CAUSES 边：优先按调用图，再补因果流水线顺序。"""
        micro = [n for n in g.by_type("causal_node") if n.get("abstraction") == "micro"]
        by_evidence: Dict[str, List[Any]] = defaultdict(list)
        for n in micro:
            by_evidence[str(n.get("evidence", ""))].append(n)
        added = 0
        for e in g.edges:
            if e.type != "CALLS" or e.attrs.get("resolution") == "unresolved":
                continue
            for a in by_evidence.get(e.source, []) + by_evidence.get(f"{e.source}#impl", []):
                for b in by_evidence.get(e.target, []):
                    if a.qn != b.qn and g.add_edge(a.qn, b.qn, "CAUSES", via="calls"):
                        added += 1
        # 按 (phase, modality, causal_order) 补链：论文侧与代码侧都形成因果流水线，
        # 使 Grounding 的结构位置相似度与 Mermaid 渲染都有边可用。
        for modality in ("code", "paper"):
            for phase in PHASES:
                group = sorted([n for n in micro if n.get("phase") == phase
                                and n.get("source_modality") == modality],
                               key=lambda n: (CAUSAL_ORDER.get(str(n.get("causal_type")), 9), n.qn))
                for a, b in zip(group, group[1:]):
                    if g.add_edge(a.qn, b.qn, "CAUSES", via="pipeline_order"):
                        added += 1
        return added

    def build_hierarchy(self, g: AlgoGraph) -> Dict[str, List[str]]:
        """构造式：meso 由 micro 按七类聚合，macro 由 meso 按三段聚合。"""
        out: Dict[str, List[str]] = {"meso": [], "macro": [], "orphans": []}
        micro = [n for n in g.by_type("causal_node") if n.get("abstraction") == "micro"]
        groups: Dict[Tuple[str, str], List[Any]] = defaultdict(list)
        for n in micro:
            groups[(str(n.get("source_modality")), str(n.get("phase")))].append(n)

        for (modality, phase), members in groups.items():
            by_type: Dict[str, List[Any]] = defaultdict(list)
            for n in members:
                by_type[str(n.get("causal_type"))].append(n)
            meso_segments: Dict[str, List[str]] = defaultdict(list)
            for ctype in CAUSAL_TYPES:
                if not by_type.get(ctype):
                    continue
                key = f"{modality}:{phase}:meso:{ctype}"
                mqn = _causal_qn(modality, phase, "meso", key)
                g.node(mqn, "causal_node", f"{phase} · {ctype}",
                       causal_type=ctype, phase=phase, abstraction="meso",
                       source_modality=modality, mermaid_id=f"n{stable_hash(mqn, length=8)}",
                       member_ids=[n.qn for n in by_type[ctype]],
                       construction="aggregate_micro_by_causal_type", granularity="causal")
                g.nodes[mqn].layer = "causal"
                for n in by_type[ctype]:
                    g.add_edge(mqn, n.qn, "DERIVES_FROM", mapping="full",
                               member_ids=[n.qn])
                out["meso"].append(mqn)
                seg = next((s for s, ts in MACRO_SEGMENTS if ctype in ts), "core")
                meso_segments[seg].append(mqn)

            for seg, _types in MACRO_SEGMENTS:
                seg_members = meso_segments.get(seg, [])
                if not seg_members:
                    continue
                key = f"{modality}:{phase}:macro:{seg}"
                qn = _causal_qn(modality, phase, "macro", key)
                g.node(qn, "causal_node", f"{phase} · {seg}",
                       causal_type="mechanism" if seg == "core" else "output",
                       phase=phase, abstraction="macro", source_modality=modality,
                       mermaid_id=f"n{stable_hash(qn, length=8)}",
                       member_ids=seg_members, construction="aggregate_meso_by_segment",
                       granularity="causal")
                g.nodes[qn].layer = "causal"
                for m in seg_members:
                    g.add_edge(qn, m, "DERIVES_FROM", mapping="full", member_ids=[m])
                out["macro"].append(qn)

        # orphan：没有被任何 meso 覆盖的 micro（CAD §5.2 的 orphan 概念）
        covered = {e.target for e in g.edges if e.type == "DERIVES_FROM"}
        out["orphans"] = [n.qn for n in micro if n.qn not in covered]
        g.meta["hierarchy"] = {"n_meso": len(out["meso"]), "n_macro": len(out["macro"]),
                               "orphans": out["orphans"][:20]}
        return out


# ---------------------------------------------------------------------------
# Mermaid 表面形式（CAD §3.2 / C4）：导出 + 容错解析
# ---------------------------------------------------------------------------
_NODE_RE = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\["?([^"\]]*)"?\]\s*:::([A-Za-z_]+)')
_EDGE_RE = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*-->\s*([A-Za-z_][A-Za-z0-9_]*)\s*$')


def to_mermaid(g: AlgoGraph, *, level: str = "meso",
               modality: str = "code", phase: str = "") -> str:
    """导出 Mermaid flowchart TB（七类 classDef 颜色 + 因果边）。"""
    nodes = [n for n in g.by_type("causal_node")
             if n.get("abstraction") == level and n.get("source_modality") == modality
             and (not phase or n.get("phase") == phase)]
    ids = {n.qn: n.get("mermaid_id") or f"n{stable_hash(n.qn, length=8)}" for n in nodes}
    lines = ["flowchart TB"]
    for ctype, color in CAUSAL_COLORS.items():
        lines.append(f"  classDef {ctype} fill:{color},stroke:#333,color:#111;")
    for n in nodes:
        label = str(n.label).replace('"', "'").replace("[", "(").replace("]", ")")
        lines.append(f'  {ids[n.qn]}["{label}"]:::{n.get("causal_type", "mechanism")}')
    for e in g.edges:
        if e.type == "CAUSES" and e.source in ids and e.target in ids:
            lines.append(f"  {ids[e.source]} --> {ids[e.target]}")
    return "\n".join(lines) + "\n"


def mermaid_to_graph(text: str, *, modality: str = "paper",
                     phase: str = "inference", level: str = "micro") -> Tuple[AlgoGraph, List[str]]:
    """把 Mermaid 文本解析回图；容忍 ``Table N header:`` 与缺失表头。"""
    g = AlgoGraph(make_qn("mermaid", modality, phase, level))
    warnings: List[str] = []
    id_to_qn: Dict[str, str] = {}
    seen_header = False
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.match(r"^Table\s+\d+\s+header:", line, re.I):
            warnings.append("容忍 Table N header 标记")
            continue
        if line.startswith(("flowchart", "graph ", "classDef", "%%", "|")):
            seen_header = seen_header or line.startswith(("flowchart", "graph "))
            continue
        m = _NODE_RE.match(line)
        if m:
            mid, label, ctype = m.group(1), m.group(2).strip(), m.group(3)
            if ctype not in CAUSAL_TYPES:
                warnings.append(f"未知 causal_type {ctype!r}，回退 mechanism")
                ctype = "mechanism"
            qn = _causal_qn(modality, phase, level, f"mermaid:{mid}:{label}")
            g.node(qn, "causal_node", label or mid,
                   causal_type=ctype, phase=phase, abstraction=level,
                   source_modality=modality, mermaid_id=mid,
                   evidence="mermaid", rule="parsed", granularity="causal")
            g.nodes[qn].layer = "causal"
            id_to_qn[mid] = qn
            continue
        e = _EDGE_RE.match(line)
        if e:
            a, b = e.group(1), e.group(2)
            if a not in id_to_qn:
                qn = _causal_qn(modality, phase, level, f"mermaid:{a}")
                g.node(qn, "causal_node", a, causal_type="mechanism", phase=phase,
                       abstraction=level, source_modality=modality, mermaid_id=a,
                       evidence="mermaid", rule="edge-only", granularity="causal")
                g.nodes[qn].layer = "causal"
                id_to_qn[a] = qn
                warnings.append(f"边引用了未声明节点 {a}，已补建")
            if b not in id_to_qn:
                qn = _causal_qn(modality, phase, level, f"mermaid:{b}")
                g.node(qn, "causal_node", b, causal_type="mechanism", phase=phase,
                       abstraction=level, source_modality=modality, mermaid_id=b,
                       evidence="mermaid", rule="edge-only", granularity="causal")
                g.nodes[qn].layer = "causal"
                id_to_qn[b] = qn
            g.add_edge(id_to_qn[a], id_to_qn[b], "CAUSES", via="mermaid")
    if not seen_header and id_to_qn:
        warnings.append("输入未包含 flowchart 头（容忍丢表头）")
    g.meta["mermaid_warnings"] = warnings
    return g, warnings
