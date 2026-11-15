"""验证绑定与失败修复定位：把 gate 指标断言映射到精确代码块.

需求要点：拆解出的关键单元（如 ``apply_threshold`` 这个 decision 节点）应能
直接映射到 TestCase 断言；gate 指标不达标时，修复 Agent 应优先检查 decision
类型节点的阈值/参数，而不是盲目修改整个文件。

输出同时提供两个粒度（PKG 的「上下文广度 vs 精确性」权衡）：
* ``precise_blocks``     块级源码片段，用于精确修改；
* ``function_context``   父函数完整实现，用于保持上下文自包含。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .schema import CAUSAL_PRIORITY, make_qn
from .store import AlgoGraph


def _graph_of(version_or_graph: Any) -> AlgoGraph:
    if isinstance(version_or_graph, AlgoGraph):
        return version_or_graph
    g = getattr(version_or_graph, "graph", None)
    if not isinstance(g, AlgoGraph):
        raise TypeError("需要 CapabilityVersion 或 AlgoGraph")
    return g


class RepairLocator:
    """根据失败信息给出排序后的修复候选与双粒度上下文。"""

    def locate(self, version_or_graph: Any, failure: Dict[str, Any],
               *, top_k: int = 5) -> Dict[str, Any]:
        """``failure = {metric, value, threshold, direction, line, traceback, role}``。"""
        g = _graph_of(version_or_graph)
        version_id = str(getattr(version_or_graph, "version_id", "") or "")
        metric = str(failure.get("metric") or "")
        line = failure.get("line")
        traceback = str(failure.get("traceback") or "")
        if line is None and traceback:
            m = re.search(r"(?:line|:)\s*(\d+)", traceback)
            line = int(m.group(1)) if m else None

        # 1) 该 gate 指标绑定的语义节点
        bound: List[str] = []
        if metric:
            mqn = make_qn("metric", version_id, metric) if version_id else ""
            for n in g.by_type("metric_binding"):
                if n.get("metric_name") != metric:
                    continue
                bound += [e.target for e in g.outgoing(n.qn, "ASSERTS")]
            if mqn in g.nodes:
                bound += [e.target for e in g.outgoing(mqn, "ASSERTS")]

        # 2) 候选排序：绑定 > 语义优先级 > 行号命中
        gate_hint = re.compile(r"threshold|gate|filter|select|decide|cutoff", re.I)

        def priority(n: Any) -> Tuple[int, int, int, int]:
            ct = str(n.get("causal_type"))
            rank = CAUSAL_PRIORITY.index(ct) if ct in CAUSAL_PRIORITY else 9
            is_bound = 0 if n.qn in bound else 1
            # 名称显式带 threshold/gate 的 decision 节点优先于泛化的 if 块
            name_hint = 0 if gate_hint.search(f"{n.label} {n.get('name', '')}") else 1
            ev = g.nodes.get(str(n.get("evidence", "")))
            hit = 0
            if line and ev:
                s, e = int(ev.get("start_line") or 0), int(ev.get("end_line") or 0)
                hit = 0 if s <= int(line) <= e else 1
            return (is_bound, name_hint, rank, hit)

        candidates = [n for n in g.by_type("causal_node")
                      if n.get("abstraction") == "micro"
                      and n.get("source_modality") == "code"]
        candidates.sort(key=priority)

        precise: List[Dict[str, Any]] = []
        contexts: List[Dict[str, Any]] = []
        ranked: List[Dict[str, Any]] = []
        seen_blocks: set = set()
        seen_funcs: set = set()
        for n in candidates[: max(top_k * 2, top_k)]:
            evidence = str(n.get("evidence", ""))
            ev = g.nodes.get(evidence)
            ranked.append({"qn": n.qn, "label": n.label,
                           "causal_type": n.get("causal_type"),
                           "bound_to_metric": n.qn in bound,
                           "evidence": evidence})
            if not ev:
                continue
            if ev.type == "code_block" and ev.qn not in seen_blocks:
                seen_blocks.add(ev.qn)
                precise.append({
                    "qn": ev.qn, "label": ev.label,
                    "block_kind": ev.get("block_kind"),
                    "content": ev.get("content", ""),
                    "start_line": ev.get("start_line"), "end_line": ev.get("end_line"),
                    "function_id": ev.get("function_id"),
                })
            elif ev.type == "implementation":
                # 下钻该函数内所有 decision 类块
                for b in g.by_type("code_block"):
                    if b.get("function_id") != ev.get("function_id") or b.qn in seen_blocks:
                        continue
                    if b.get("block_kind") not in ("if", "elif", "case"):
                        continue
                    seen_blocks.add(b.qn)
                    precise.append({
                        "qn": b.qn, "label": b.label, "block_kind": b.get("block_kind"),
                        "content": b.get("content", ""),
                        "start_line": b.get("start_line"), "end_line": b.get("end_line"),
                        "function_id": b.get("function_id"),
                    })
            fid = ev.get("function_id") or (evidence if evidence.endswith("#name") else "")
            if fid and fid not in seen_funcs:
                seen_funcs.add(fid)
                ctx = g.function_context(fid)
                if ctx.get("implementation"):
                    contexts.append(ctx)

        if line:
            for b in g.by_type("code_block"):
                if int(b.get("start_line") or 0) <= int(line) <= int(b.get("end_line") or 0):
                    if b.qn not in seen_blocks:
                        precise.insert(0, {
                            "qn": b.qn, "label": b.label, "block_kind": b.get("block_kind"),
                            "content": b.get("content", ""),
                            "start_line": b.get("start_line"), "end_line": b.get("end_line"),
                            "function_id": b.get("function_id"),
                            "reason": "traceback/失败行直接命中",
                        })
                        seen_blocks.add(b.qn)
                    break

        decision_first = any(r["causal_type"] == "decision" for r in ranked[:3])
        rationale = (
            f"指标 {metric or '(未指定)'} 未达 gate 阈值时，按 Causal 语义优先级"
            f"（decision > parameter > mechanism > …）定位；"
            f"{'已找到 decision 节点，优先检查阈值/比较条件' if decision_first else '本图未标注 decision 节点，退化为参数与机制检查'}。"
            f" 返回 {len(precise)} 个块级精确片段 + {len(contexts)} 份父函数完整实现，"
            f"兼顾精确性与上下文广度（PKG 粒度权衡）。"
        )
        return {
            "failure": failure,
            "bound_nodes": bound,
            "ranked_candidates": ranked[:top_k],
            "precise_blocks": precise[:top_k],
            "function_context": contexts[:top_k],
            "granularity_plan": {
                "default": "function",
                "drill_down": "block",
                "reason": "常规复刻用函数级上下文；失败修复下钻到块级精确索引",
            },
            "rationale": rationale,
            "rationale_sources": [
                "PKG docs/Implementation.md:18（函数/块两级检索 + 投影回父函数）",
                "Causal Algorithm Design §3.2（decision/parameter 门控语义）",
                "需求：gate 指标断言应映射到 decision 节点",
            ],
        }
