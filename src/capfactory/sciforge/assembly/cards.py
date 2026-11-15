"""P1-8 算法卡片：恢复族专属字段为二级结构（Stage3 内不调 LLM）。

蓝图 §5.3 的 1/4/7 步落点：
  步1 候选来自 Stage2 产物（code_symbols / methods / baselines），不从全图取；
  步2/3/6 规则判族 + 原论文反查 + 任务类型；
  步4 族专属字段 → `family_fields` 二级卡片；
  步5 问题/机理复用图内已有 v2 核心属性，不重复推断；
  步7 规则校验 + build_index 重建检索索引。
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..algorithm_fill import KNOWN
from ..algorithm_schema import classify_rule, schema_for, FAMILIES
from ..algorithm_problem import TASK_TYPES, FAMILY_TASK


_GENERIC_CODE = {"forward", "sample", "train", "init", "call", "run",
                 "main", "backward", "step", "loss", "compute", "get", "set"}


def _candidates(norm: Any) -> List[str]:
    """候选只取方法名/基线；代码符号另放 code_symbols，不冒充算法。"""
    out: List[str] = []
    for x in (list(norm.methods) + list(norm.baselines)):
        x = str(x or "").strip()
        if not x or x in out or x.startswith("_") or x.lower() in _GENERIC_CODE:
            continue
        if len(x) > 40:
            continue
        out.append(x)
    return out


def _family_fields(name: str, family: str) -> Dict[str, Any]:
    """族专属二级字段：优先认知表，否则按族 schema 生成显式占位。"""
    known = KNOWN.get(name) or {}
    alias = ""
    if not known.get("fields"):
        key = name.split("-")[0].strip()
        for k, v in KNOWN.items():
            if v.get("fields") and k.lower() == key.lower():
                known, alias = v, k
                break
    if known.get("fields"):
        return {**known["fields"],
                "field_source": "domain_knowledge",
                "family_mismatch": known.get("family", "") != family,
                "name_alias": alias}
    sch = schema_for(family).get("fields") or {}
    return {**{k: "unknown" for k in sch},
            "field_source": "needs_extraction"}


def _core_from_graph(name: str, graph: Any) -> Dict[str, Any]:
    key = name.strip().lower().split("-")[0]
    for n in graph.by_type("Algorithm"):
        if n.label.strip().lower() == key:
            a = n.attrs
            return {"task_type": a.get("task_type"),
                    "task_type_label": a.get("task_type_label"),
                    "problems_solved": a.get("problems_solved") or [],
                    "mechanism": a.get("mechanism"),
                    "why_it_works": a.get("why_it_works"),
                    "filled_by": a.get("filled_by")}
    return {}


def build_algorithm_cards(inp: Any, norm: Any, plan: Any, *,
                          graph: Any, use_llm: bool = False
                          ) -> Dict[str, Any]:
    from .link import resolve_source_ref
    cards: List[Dict[str, Any]] = []
    by_label = {n.label.strip().lower(): n.id
                for n in graph.by_type("Algorithm")}
    for name in _candidates(norm):
        node_id = by_label.get(name.strip().lower())
        fam = ((graph.nodes[node_id].attrs.get("schema_family")
                if node_id else "") or
               (KNOWN.get(name) or {}).get("family") or
               classify_rule(name) or "autoregressive")
        src = resolve_source_ref(name, inp.md)
        ff = _family_fields(name, fam)
        task = (graph.nodes[node_id].attrs.get("task_type")
                if node_id else "") or FAMILY_TASK.get(fam, ("", ""))[0]
        card = {
            "name": name,
            "node_id": node_id or "",
            "family": fam,
            "family_label": schema_for(fam).get("label", fam),
            "task_type": task if task in TASK_TYPES else "unknown",
            "source_ref": {"ref_no": src.get("ref_no", ""),
                           "status": src.get("status", ""),
                           "title": src.get("title", "")},
            "family_fields": ff,          # ← 二级卡片（修 algrithem.md 建议 P0）
            "core": _core_from_graph(name, graph),
            "code_symbols": [s for s in plan.ast_hits
                             if name.lower() in s.lower()][:8],
            "inference_basis": ("domain_knowledge"
                                if ff.get("field_source") == "domain_knowledge"
                                else "由算法族推断"),
            "use_llm": use_llm,
        }
        cards.append(card)
    # 步7：规则校验（封闭族 id / task_type）+ 重建检索索引
    issues = []
    for c in cards:
        if c["family"] not in FAMILIES:
            issues.append(f"unknown_family:{c['name']}")
        if c["task_type"] not in TASK_TYPES and c["task_type"] != "unknown":
            issues.append(f"bad_task_type:{c['name']}")
    rebuilt = False
    try:
        from ..algorithm_problem import build_index
        build_index(graph)
        rebuilt = True
    except Exception:  # noqa: BLE001
        issues.append("build_index_failed")
    rep = {"n_candidates": len(cards),
           "n_with_family_fields": sum(
               1 for c in cards
               if c["family_fields"].get("field_source") ==
               "domain_knowledge"),
           "n_with_graph_core": sum(1 for c in cards if c["core"]),
           "n_with_source_ref": sum(
               1 for c in cards if c["source_ref"]["status"] == "resolved"),
           "index_rebuilt": rebuilt, "issues": issues,
           "cards": cards}
    p = Path(inp.out_dir) / "algorithm_cards.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, ensure_ascii=False, indent=2),
                 encoding="utf-8")
    return rep
