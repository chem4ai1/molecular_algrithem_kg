"""CAD 双推理图与节点级 grounding（验证代码↔模块的**语义正确性**）。

依据 ``ref/code-anlysis.pdf`` §3.2–3.3：

* 每个算法拆成 **training / inference 两张耦合因果图**，节点 id 不相交；
* 节点取自 7 类本体 ``input/parameter/mechanism/state/aggregation/decision/output``；
* 三级抽象 ``micro(12–25)/meso(7–10)/macro(4–7)``；
* **Grounding**：以 code 推理图为 ground truth，逐节点匹配 paper 推理图，
  未匹配的分 ``conceptual_gap``（论文省略机制）或 ``implementation_gap``
  （dtype/alloc/并行等工程细节）；匹配对给 ``Agreement`` 与
  ``Paper-too-abstract`` 标签。

与 ``modules.py`` 的区别：那里只校验 ``code_symbols`` **是否存在于 AST 清单**；
这里校验该符号的 **causal_role / mechanism / IO 签名** 是否真的对应模块语义。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..po import POGraph
from ..utils import now_iso, parse_llm_json
from .layers import (CAUSAL_TYPES, PHASES, ABSTRACTIONS, CAD_LEVEL_BUDGET,
                     GAP_TYPES, AGREEMENT)
from .modules import code_structure, _symbol_index

# 论文模块 → 因果节点角色（CAD 七类）
ROLE_BY_MECHANISM: Dict[str, str] = {
    "message_compute": "mechanism", "coordinate_update": "mechanism",
    "feature_update": "mechanism", "aggregation": "aggregation",
    "edge_inference": "mechanism", "normalization": "state",
    "attention": "mechanism", "readout": "aggregation", "pooling": "aggregation",
    "encoding": "state", "decoding": "output", "sampling": "decision",
    "loss": "decision", "scoring": "decision", "filtering": "decision",
    "initialization": "parameter", "other": "state",
}

GROUNDING_PROMPT = """你是 SCM（结构因果模型）专家，在做论文↔代码的**节点级 grounding**。

左：论文推理图的因果节点（由方法模块分解而来，每个带 mechanism 与 inputs/outputs）。
右：代码推理图的因果节点（由 AST 得到，每个带 causal_role、mechanism、签名）。

规则：
1. 以**代码节点为 ground truth**，每个代码节点匹配至多一个论文节点；每个论文节点最多被消费一次。
2. 判断依据必须是 **mechanism 语义 + 输入输出签名**，不是名字相似。
   例如论文模块 "Edge Message Computation" 与代码符号 "EGNN_Sparse.message" 名字不同，
   但 mechanism=message_compute 且都吃 h_i/h_j/edge_attr，应判 High。
3. 未在论文侧找到对应机制的代码节点 → gap_type=implementation_gap；
   论文模块没有任何代码节点匹配 → 单独列在 conceptual_gap_nodes。
4. 每个匹配给 agreement: high|partial|low，paper_too_abstract: yes|partial|no，
   并用一句话 justification 说明机制与 IO 的对应关系。

输出严格 JSON（不要代码块）：
{
  "alignments": [
    {"code_node":"", "paper_node":"", "agreement":"high|partial|low",
     "paper_too_abstract":"yes|partial|no", "gap_type":"none|conceptual|implementation",
     "mechanism_match": true, "io_match": true, "justification":""}
  ],
  "conceptual_gap_nodes": ["论文节点 id"],
  "implementation_gap_nodes": ["代码节点 id"],
  "semantic_validity": 0.0
}

## 论文推理图节点
{paper}

## 代码推理图节点
{code}

只输出 JSON，整体 <= 2000 token。"""


def paper_nodes(modules_raw: Dict[str, Any], *, phase: str = "inference"
                ) -> List[Dict[str, Any]]:
    """论文模块 → CAD 因果节点（每个模块一个主节点 + 输入/输出节点）。"""
    out: List[Dict[str, Any]] = []
    for i, m in enumerate(modules_raw.get("modules") or []):
        if not isinstance(m, dict):
            continue
        mid = f"p:{phase}:n{i}"
        mech = str(m.get("mechanism") or "other")
        out.append({
            "id": mid, "label": str(m.get("module_name") or f"module{i}"),
            "causal_type": ROLE_BY_MECHANISM.get(mech, "mechanism"),
            "mechanism": mech, "phase": phase, "abstraction": "meso",
            "inputs": [str(x) for x in (m.get("inputs") or [])],
            "outputs": [str(x) for x in (m.get("outputs") or [])],
            "code_symbols": list(m.get("code_symbols") or []),
            "grounding_status": m.get("grounding_status") or "unresolved",
        })
    return out


def code_nodes(struct: Dict[str, Any], modules_raw: Dict[str, Any], *,
               phase: str = "inference") -> List[Dict[str, Any]]:
    """只取**被论文模块引用**的代码符号 → CAD 因果节点（按 ① 收敛）。"""
    idx = _symbol_index(struct)
    used: List[str] = []
    for m in modules_raw.get("modules") or []:
        for sym in m.get("code_symbols") or []:
            if sym in idx and sym not in used:
                used.append(sym)
    out: List[Dict[str, Any]] = []
    for i, sym in enumerate(used):
        s = idx[sym]
        out.append({
            "id": f"c:{phase}:n{i}", "label": sym,
            "causal_type": s.get("causal_role") or "state",
            "mechanism": s.get("mechanism") or "other",
            "phase": phase, "abstraction": "micro",
            "signature": s.get("signature") or "",
            "file": s.get("file") or "",
            "qualified": s.get("qualified") or sym,
            "implementation_hint": _impl_hint(s.get("signature") or "", sym),
        })
    return out


def _impl_hint(signature: str, name: str) -> str:
    low = f"{name} {signature}".lower()
    hints = ("dtype", "cast", "reshape", "device", "cuda", "cache", "eps",
             "clamp", "parallel", "n_jobs", "sparse", "batch", "buffer")
    hit = [h for h in hints if h in low]
    return ",".join(hit) if hit else ""


def _compact(nodes: Sequence[Dict[str, Any]], kind: str) -> str:
    lines = []
    for n in nodes:
        if kind == "paper":
            lines.append(f"- {n['id']} | {n['label'][:44]} | "
                         f"type={n['causal_type']} mech={n['mechanism']} "
                         f"in={n['inputs'][:4]} out={n['outputs'][:4]}")
        else:
            lines.append(f"- {n['id']} | {n['label'][:44]} | "
                         f"type={n['causal_type']} mech={n['mechanism']} "
                         f"sig={n['signature'][:80]} hint={n['implementation_hint']}")
    return "\n".join(lines)


def grounding_prompt(pn: Sequence[Dict[str, Any]],
                     cn: Sequence[Dict[str, Any]]) -> str:
    return (GROUNDING_PROMPT.replace("{paper}", _compact(pn, "paper"))
                            .replace("{code}", _compact(cn, "code")))


def rule_grounding(pn: Sequence[Dict[str, Any]],
                   cn: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """确定性兜底：mechanism + causal_role + IO 关键词决定匹配与 agreement。"""
    alignments: List[Dict[str, Any]] = []
    used_p: set = set()
    for c in cn:
        best, best_score = None, 0.0
        for p in pn:
            if p["id"] in used_p:
                continue
            score = 0.0
            if p.get("mechanism") == c.get("mechanism"):
                score += 0.55
            if p.get("causal_type") == c.get("causal_type"):
                score += 0.25
            # 符号名出现在模块声明的 code_symbols 里（弱证据，不能单独定案）
            if c["label"] in (p.get("code_symbols") or []):
                score += 0.10
            io = " ".join(p.get("inputs", []) + p.get("outputs", [])).lower()
            sig = c.get("signature", "").lower()
            if any(t in sig for t in ("coord", "x") ) and "coord" in io:
                score += 0.05
            if score > best_score:
                best, best_score = p, score
        if best and best_score >= 0.55:
            used_p.add(best["id"])
            mech_ok = best.get("mechanism") == c.get("mechanism")
            alignments.append({
                "code_node": c["id"], "paper_node": best["id"],
                "agreement": "high" if best_score >= 0.8 else "partial",
                "paper_too_abstract": "no" if best_score >= 0.8 else "partial",
                "gap_type": "none", "mechanism_match": mech_ok,
                "io_match": bool(c.get("signature")),
                "justification": f"rule: mechanism+causal_role 得分 {best_score:.2f}",
                "score": round(best_score, 3),
            })
    conceptual = [p["id"] for p in pn if p["id"] not in used_p]
    matched_c = {a["code_node"] for a in alignments}
    impl = [c["id"] for c in cn if c["id"] not in matched_c]
    return {"alignments": alignments,
            "conceptual_gap_nodes": conceptual,
            "implementation_gap_nodes": impl,
            "semantic_validity": round(len(alignments) / max(len(cn), 1), 3),
            "source": "rule"}


def llm_grounding(pn: Sequence[Dict[str, Any]], cn: Sequence[Dict[str, Any]], *,
                  chat_fn: Any) -> Dict[str, Any]:
    """CAD §3.3 节点级对齐；模型失败时退回规则结果。"""
    out = parse_llm_json(chat_fn(grounding_prompt(pn, cn))) or {}
    if not out.get("alignments"):
        return rule_grounding(pn, cn)
    by_c = {n["id"]: n for n in cn}
    by_p = {n["id"]: n for n in pn}
    valid = []
    for a in out["alignments"]:
        if a.get("code_node") not in by_c:
            continue                       # 丢弃编造的代码节点 id
        if a.get("paper_node") and a["paper_node"] not in by_p:
            a["paper_node"] = ""
        a.setdefault("mechanism_match", False)
        a.setdefault("io_match", False)
        a.setdefault("gap_type", "none")
        a.setdefault("justification", "")
        valid.append(a)
    sem = sum(1 for a in valid if a.get("mechanism_match") and a.get("io_match"))
    return {"alignments": valid,
            "conceptual_gap_nodes": out.get("conceptual_gap_nodes") or [],
            "implementation_gap_nodes": out.get("implementation_gap_nodes") or [],
            "semantic_validity": round(sem / max(len(cn), 1), 3),
            "source": "llm"}


def build_grounding_graph(pn: Sequence[Dict[str, Any]], cn: Sequence[Dict[str, Any]],
                          result: Dict[str, Any], *, doc_id: str
                          ) -> Tuple[POGraph, Dict[str, Any]]:
    """把两张推理图 + 对齐结果落成 V2 图节点（``CausalGraph``/``CausalNode``/
    ``GroundingAlignment``），使 grounding 可回溯、可查询。"""
    g = POGraph(f"cad::{doc_id}")
    st: Dict[str, Any] = {"nodes": 0, "edges": 0, "alignments": 0,
                          "conceptual_gaps": 0, "implementation_gaps": 0}
    for phase, source, nodes in (("inference", "paper", pn),
                                 ("inference", "code", cn)):
        gid = f"causalgraph:{source}:{phase}"
        g.node(gid, "CausalGraph", f"{source}/{phase}",
               phase=phase, abstraction="meso" if source == "paper" else "micro",
               source=source, algorithm_id="",
               n_nodes=len(nodes))
        st["nodes"] += 1
        for n in nodes:
            nid = f"causalnode:{source}:{n['id']}"
            g.node(nid, "CausalNode", n["label"],
                   causal_type=n["causal_type"], label=n["label"],
                   graph_id=gid, mechanism=n.get("mechanism", ""),
                   implementation_hint=n.get("implementation_hint", ""))
            g.assert_rel(gid, nid, "HAS_CAUSAL_NODE")
            st["nodes"] += 1
            st["edges"] += 1
    for i, a in enumerate(result.get("alignments") or []):
        aid = f"groundingalignment:{doc_id}:{i}"
        g.node(aid, "GroundingAlignment", f"align{i}",
               code_node_id=a.get("code_node", ""),
               paper_node_id=a.get("paper_node", ""),
               agreement=a.get("agreement", "low"),
               paper_too_abstract=a.get("paper_too_abstract", "partial"),
               gap_type=a.get("gap_type", "none"))
        g.assert_rel(aid, f"causalnode:code:{a.get('code_node','')}", "ALIGNED_BY")
        if a.get("paper_node"):
            g.assert_rel(aid, f"causalnode:paper:{a['paper_node']}", "ALIGNED_BY")
        st["nodes"] += 1
        st["edges"] += 1 if a.get("paper_node") else 0
        st["alignments"] += 1
    st["conceptual_gaps"] = len(result.get("conceptual_gap_nodes") or [])
    st["implementation_gaps"] = len(result.get("implementation_gap_nodes") or [])
    g.meta["cad"] = {"doc_id": doc_id, "at": now_iso(),
                     "source": result.get("source"),
                     "semantic_validity": result.get("semantic_validity")}
    return g, st


def grounding_all(modules_raw: Dict[str, Any], struct: Dict[str, Any], *,
                  doc_id: str, chat_fn: Optional[Any] = None
                  ) -> Dict[str, Any]:
    pn = paper_nodes(modules_raw)
    cn = code_nodes(struct, modules_raw)
    result = (llm_grounding(pn, cn, chat_fn=chat_fn) if chat_fn is not None
              else rule_grounding(pn, cn))
    g, st = build_grounding_graph(pn, cn, result, doc_id=doc_id)
    return {"paper_nodes": len(pn), "code_nodes": len(cn),
            "semantic_validity": result.get("semantic_validity"),
            "source": result.get("source"),
            "agreement": dict(__import__("collections").Counter(
                a.get("agreement", "?") for a in result["alignments"])),
            "conceptual_gaps": result.get("conceptual_gap_nodes", []),
            "implementation_gaps": result.get("implementation_gap_nodes", []),
            "alignments": result["alignments"], "graph_stats": st,
            "graph": g}
