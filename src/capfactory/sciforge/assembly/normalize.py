"""A2 Normalize：纯函数规范化（零 IO、零 LLM）。"""
from __future__ import annotations
import re
from typing import Any, Dict

from .contract import NormalizedInput, FORM_VOCAB, TREE_RELS

_FORM_ALIASES = {
    "smiles": "SMILES", "selfies": "SMILES", "sequence": "序列",
    "向量": "向量", "vector": "向量", "3d": "3D坐标", "3d坐标": "3D坐标",
    "coordinates": "3D坐标", "graph": "图", "图": "图",
    "distribution": "分布", "scalar": "标量", "text": "文本",
}


def norm_form(v: Any) -> str:
    s = str(v or "").strip().lower()
    if s in FORM_VOCAB:
        return s
    for k, val in _FORM_ALIASES.items():
        if k in s:
            return val
    return ""


def norm_metric(v: Any) -> str:
    s = str(v or "").strip()
    try:
        from ...ontology.metrics import canonicalize_metric
        return canonicalize_metric(s) or s
    except Exception:  # noqa: BLE001
        return s


def norm_method(v: Any) -> str:
    try:
        from ..leaderboard import normalize_model_name
        return normalize_model_name(str(v or ""))
    except Exception:  # noqa: BLE001
        return re.sub(r"\s*\(ours\)\s*$", "", str(v or ""), flags=re.I).strip()


def norm_formula_ref(v: Any) -> str:
    s = str(v or "").strip()
    return s if re.fullmatch(r"\([1-9]|1[0-2]\)", s) else ""


def norm_unit(v: Any) -> str:
    s = str(v or "").strip()
    return "%" if s in ("percent", "%", "％") else s


def normalize(inp: Any) -> NormalizedInput:
    out = NormalizedInput()
    bm, mt, rw = inp.benchmark or {}, inp.method or {}, inp.related_work or {}
    for b in bm.get("benchmarks") or []:
        nb = dict(b)
        for k in ("input_form", "output_form"):
            f = norm_form(nb.get(k))
            if not f and nb.get(k):
                out.problems.append(f"form_out_of_vocab:{k}={nb[k]}")
            nb[k] = f
        nb["metrics"] = [norm_metric(x) for x in (nb.get("metrics") or [])]
        nb["baselines"] = [norm_method(x) for x in (nb.get("baselines") or [])]
        out.benchmarks.append(nb)
        out.methods += nb["baselines"]
    for i, s in enumerate(mt.get("steps") or []):
        ns = dict(s)
        ns["formula_ref"] = norm_formula_ref(ns.get("formula_ref") or
                                             ns.get("formula"))
        ns["tools"] = [str(x) for x in (ns.get("tools") or [])]
        ns["code_symbols"] = [str(x) for x in (ns.get("code_symbols") or [])]
        out.code_symbols += ns["code_symbols"]
        out.steps.append(ns)
    for o in bm.get("observations") or []:
        no = dict(o)
        no["unit"] = norm_unit(no.get("unit"))
        no["metric"] = norm_metric(no.get("metric"))
        out.observations.append(no)
    for c in rw.get("chains") or []:
        out.methods += [norm_method(x) for x in (c.get("methods") or [])]
        for e in c.get("edges") or []:
            rel = str(e.get("rel") or "")
            if rel == "REPLACED_BY":
                rel = "REPLACES"          # 蓝图 §5.1 别名
            if rel in TREE_RELS:
                out.tree_edges.append({**e, "rel": rel,
                                       "style": c.get("style")})
    out.methods = [x for x in dict.fromkeys(out.methods) if x]
    out.baselines = [x for x in dict.fromkeys(
        sum((b["baselines"] for b in out.benchmarks), [])) if x]
    out.code_symbols = [x for x in dict.fromkeys(out.code_symbols) if x]
    out.metrics = [x for x in dict.fromkeys(
        sum((b["metrics"] for b in out.benchmarks), [])) if x]
    return out
