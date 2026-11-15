"""P1-7：mini-batch shape 探针 + Paper Lineage 证据补全。

shape probe（AutoReproduce 的 mini-batch sampling 思路，但确定性、零执行风险）：
  从 ``DataContract.input_form / output_form`` 的**封闭词表**推断
  shape 与 dtype。这里不编造实测值 —— 词表推断的结果标
  ``method="vocab_inference"``，真正的运行期实测留到执行脚本里。

lineage：给 ``ReproSpec.lineage`` 补 SourcePaper 的逐字证据与谱系类型。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# 封闭词表：形式 → (shape 模板, dtype, 说明)
FORM_SHAPE: Dict[str, Dict[str, str]] = {
    "SMILES": {"shape": "(n,)", "dtype": "str", "note": "变长分子串"},
    "smiles": {"shape": "(n,)", "dtype": "str", "note": "变长分子串"},
    "3D坐标": {"shape": "(n, 3)", "dtype": "float32", "note": "原子三维坐标"},
    "坐标": {"shape": "(n, 3)", "dtype": "float32", "note": "原子三维坐标"},
    "向量": {"shape": "(n, d)", "dtype": "float32", "note": "定长嵌入"},
    "图": {"shape": "(n, e, 2) + (n, d)", "dtype": "int64/float32",
           "note": "边索引 + 节点特征"},
    "分子图": {"shape": "(n, d) + (e, 2)", "dtype": "float32/int64",
             "note": "节点特征 + 边索引"},
    "序列": {"shape": "(n, L)", "dtype": "int64", "note": "变长序列已 padding"},
    "分布": {"shape": "(n_bins,)", "dtype": "float32", "note": "直方图/经验分布"},
    "标量": {"shape": "()", "dtype": "float32", "note": "单值指标"},
    "": {"shape": "unknown", "dtype": "unknown", "note": "未标注"},
}


def _shape_of(form: Any) -> Dict[str, str]:
    key = str(form or "").strip()
    return FORM_SHAPE.get(key, {"shape": "unknown", "dtype": "unknown",
                                "note": f"未登记形式 {key!r}"})


def shape_probe(spec: Any) -> List[Dict[str, Any]]:
    """为每个 DataContract 生成 shape/dtype 契约（确定性、可复算）。"""
    out: List[Dict[str, Any]] = []
    for dc in (spec.data_contract or []):
        inp = _shape_of(dc.get("input_form"))
        outp = _shape_of(dc.get("output_form"))
        unknown = [k for k, v in (("input_form", inp), ("output_form", outp))
                   if v["shape"] == "unknown"]
        out.append({
            "benchmark": dc.get("benchmark"),
            "label": dc.get("label"),
            "input_form": dc.get("input_form"),
            "output_form": dc.get("output_form"),
            "input_shape": inp["shape"], "input_dtype": inp["dtype"],
            "output_shape": outp["shape"], "output_dtype": outp["dtype"],
            "n_samples": dc.get("n_samples"),
            "scale": dc.get("scale"),
            "is_evaluation": bool(dc.get("is_evaluation", True)),
            "method": "vocab_inference",
            "unknown_forms": unknown,
            "runtime_verified": False,   # 执行器回填
        })
    return out


def lineage_enrich(spec: Any, graph: Any,
                   max_items: int = 3) -> List[Dict[str, Any]]:
    """给 lineage 补逐字证据、节点类型与谱系类别。"""
    nodes = getattr(graph, "nodes", {}) or {}
    out: List[Dict[str, Any]] = []
    for item in (spec.lineage or [])[:max_items]:
        n = nodes.get(item.get("id"))
        a = dict(getattr(n, "attrs", {}) or {}) if n else {}
        kind = (item.get("kind") or a.get("relation") or "").lower()
        category = ("baseline" if any(k in kind for k in
                    ("baseline", "extends", "improves", "compare")) else
                    "context")
        out.append({**item,
                    "node_type": getattr(n, "type", "") if n else "",
                    "category": category,
                    "quote": str(a.get("quote") or a.get("cited_title") or ""),
                    "arxiv_id": a.get("arxiv_id") or a.get("target_paper_id") or "",
                    "evidence_available": bool(a.get("quote") or
                                               a.get("cited_title"))})
    return out


def write_probes(spec: Any, graph: Any,
                 out_dir: str | Path) -> Dict[str, Any]:
    """写 ``SHAPE_PROBE.json`` / ``LINEAGE.json``；返回汇总。"""
    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)
    shapes = shape_probe(spec)
    lineage = lineage_enrich(spec, graph)
    (p / "SHAPE_PROBE.json").write_text(
        json.dumps({"paper_id": spec.paper_id, "spec_hash": spec.spec_hash,
                    "probes": shapes}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    (p / "LINEAGE.json").write_text(
        json.dumps({"paper_id": spec.paper_id, "lineage": lineage},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "n_probes": len(shapes),
        "n_unknown_forms": sum(len(x["unknown_forms"]) for x in shapes),
        "n_lineage": len(lineage),
        "lineage_with_evidence": sum(1 for x in lineage
                                     if x["evidence_available"]),
        "files": ["SHAPE_PROBE.json", "LINEAGE.json"],
    }


# ---------------------------------------------------------------------------
# P3-3：lineage 逐字证据（不把引用标题冒充 quote）
# ---------------------------------------------------------------------------
def lineage_evidence(spec: Any, graph: Any,
                     max_items: int = 3) -> List[Dict[str, Any]]:
    """区分「逐字引文」与「书目证据」。

    ``SourcePaper`` 节点只有 ``title``（引用的论文标题），那是**书目证据**，
    不是「本论文正文里引用该工作的原句」。只有当节点自身或它经
    ``SUPPORTED_BY`` 连到的 ``Evidence`` 带 ``quote`` 时才算逐字证据。
    这也是 P1-7 报告里 ``0/3`` 的真实原因。
    """
    nodes = getattr(graph, "nodes", {}) or {}
    out: List[Dict[str, Any]] = []
    for item in (spec.lineage or [])[:max_items]:
        nid = item.get("id")
        n = nodes.get(nid)
        a = dict(getattr(n, "attrs", {}) or {}) if n else {}
        quotes: List[Dict[str, str]] = []
        for key in ("quote", "cited_sentence", "source_text"):
            q = str(a.get(key) or "").strip()
            if q:
                quotes.append({"text": q, "source": nid,
                               "kind": str(a.get("kind") or "node_quote")})
        try:
            ev_edges = list(graph.outgoing(nid, "SUPPORTED_BY"))
        except Exception:  # noqa: BLE001
            ev_edges = [e for e in getattr(graph, "assertions", []) or []
                        if e.source == nid and e.relation == "SUPPORTED_BY"]
        for e in ev_edges:
            ev = nodes.get(e.target)
            if ev is None:
                continue
            ea = dict(getattr(ev, "attrs", {}) or {})
            q = str(ea.get("quote") or "").strip()
            if q:
                quotes.append({"text": q, "source": e.target,
                               "kind": str(ea.get("kind") or "evidence_quote")})
        title = str(a.get("title") or "").strip()
        grade = ("verbatim_quote" if quotes else
                 "bibliographic" if title else "none")
        out.append({**item, "evidence_type": grade,
                    "verbatim_available": bool(quotes),
                    "quotes": quotes,
                    "bibliography": {
                        "title": title,
                        "ref_paper": str(a.get("ref_paper") or ""),
                        "resolved": str(a.get("resolved") or ""),
                        "miner": str(a.get("miner") or "")},
                    "note": "" if quotes else (
                        "引用标题是书目证据，不是论文正文中引用该工作的逐字句子；"
                        "需回到 PDF 原文把 Evidence.quote 挂到 SourcePaper "
                        "的 SUPPORTED_BY 上")})
    return out


def write_lineage_evidence(spec: Any, graph: Any,
                           out_dir: str | Path) -> Dict[str, Any]:
    """写 ``LINEAGE_EVIDENCE.json``；返回汇总供报告使用。"""
    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)
    rows = lineage_evidence(spec, graph)
    payload = {
        "paper_id": spec.paper_id, "n_lineage": len(rows),
        "n_verbatim": sum(1 for x in rows if x["verbatim_available"]),
        "n_bibliographic": sum(1 for x in rows
                               if x["evidence_type"] == "bibliographic"),
        "n_none": sum(1 for x in rows if x["evidence_type"] == "none"),
        "lineage": rows,
        "remedy": ("Stage2/Stage3 抽取 related_work 段落时保存引文原句，"
                   "建成 Evidence(kind='citation', quote=...) 并以 SUPPORTED_BY "
                   "连到 SourcePaper；本模块会自动升级为 verbatim_quote。"),
    }
    (p / "LINEAGE_EVIDENCE.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {k: payload[k] for k in
            ("n_lineage", "n_verbatim", "n_bibliographic", "n_none")}
