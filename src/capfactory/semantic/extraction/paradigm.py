"""标准范式层：NER → 槽位填充 → 关系抽取 → 算法模块追踪。

参考（2026-11-14 联网调研）：
  - Dagdelen et al., Nature Communications 2024, s41467-024-45563-x：
    LLM 联合 NER + 关系抽取，schema 约束、结构化输出；
  - SciERC / SciIE / DyGIE++：实体、关系、共指多任务联合，共享表示优于冻结流水线；
  - KG 构建工程实践：实体规范化（canonicalization）是最常被跳过但最关键的一步；
    逐字 char offset 把「编造边」变成机械失败；分阶段漏斗（确定性 → LLM → 验证）；
  - 方法节模块化抽取范式：先定输入/输出/训练信号，再拆模块
    （每个模块「接收什么、产生什么、为什么需要」），最后定位目标函数与信息流。

本模块不推翻现有 E1–E6（已验证可用），而是加一层**确定性范式化后处理**：
  1) recognize_entities  实体候选识别（零 LLM）
  2) canonicalize        槽位填充后的实体规范化 / 共指合并
  3) ground_relations    关系逐字定位，无依据的边标 ungrounded
  4) track_modules       模块信息流、顺序、代码符号对齐
  5) slot_audit          槽位与词表质量审计
"""
from __future__ import annotations
import re
from typing import Any, Dict, List, Tuple

TICK = re.compile(r"\btable\s*(\d+)\b", re.I)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s or "").lower())


def _sim(a: str, b: str) -> float:
    """字符 3-gram Dice，零依赖的轻量相似度。"""
    def grams(x):
        x = _norm(x)
        return {x[i:i + 3] for i in range(max(len(x) - 2, 1))} if x else set()
    A, B = grams(a), grams(b)
    return 2 * len(A & B) / max(len(A | B), 1)


def recognize_entities(slices: Dict[str, str], graph: Any
                       ) -> Dict[str, List[Dict[str, Any]]]:
    """阶段一 NER：确定性识别候选实体，供后续槽位填充复用。"""
    out: Dict[str, List[Dict[str, Any]]] = {
        "algorithms": [], "benchmarks": [], "code_symbols": [],
        "metrics": [], "tables": []}
    seen = {k: set() for k in out}
    # ① 已有图节点名字面命中（最可靠）
    if graph:
        for typ, key in (("Algorithm", "algorithms"),
                         ("Benchmark", "benchmarks"),
                         ("CodeFunction", "code_symbols")):
            for n in graph.by_type(typ):
                name = str(n.attrs.get("name") or n.label or "")
                if len(name) > 2 and _norm(name) not in seen[key]:
                    seen[key].add(_norm(name))
                    out[key].append({"text": name, "type": typ,
                                     "source": "graph_catalog",
                                     "node_id": n.id})
        for n in graph.by_type("Benchmark"):
            for m in (n.attrs.get("metrics") or []):
                mn = str(m.get("name") if isinstance(m, dict) else m or "")
                if mn and _norm(mn) not in seen["metrics"]:
                    seen["metrics"].add(_norm(mn))
                    out["metrics"].append({"text": mn, "type": "Metric",
                                          "source": "graph_catalog"})
    # ② 文本里的大写缩写/方法名（≥2 大写或驼峰，长度 3–24）
    for key, sl in slices.items():
        for m in re.finditer(r"\b([A-Z][A-Za-z0-9\-]{2,23})\b", sl or ""):
            w = m.group(1)
            if (w.lower() in ("the", "and", "for", "with", "table", "figure",
                              "section", "we", "our", "this", "that", "using")
                    or _norm(w) in seen["algorithms"]):
                continue
            has_upper = sum(c.isupper() for c in w)
            if has_upper >= 2 or re.search(r"[a-z][A-Z]", w):
                seen["algorithms"].add(_norm(w))
                out["algorithms"].append({
                    "text": w, "type": "MethodCandidate",
                    "source": "surface_pattern", "offset": m.start(),
                    "block": key})
        for m in TICK.finditer(sl or ""):
            t = "Table " + m.group(1)
            if t not in seen["tables"]:
                seen["tables"].add(t)
                out["tables"].append({"text": t, "type": "TableRef",
                                      "source": "surface_pattern",
                                      "offset": m.start(), "block": key})
    for k in out:
        out[k] = out[k][:80]
    return out


def _catalog(graph, typ):
    if not graph:
        return []
    return [{"name": str(n.attrs.get("name") or n.label or ""),
             "id": n.id} for n in graph.by_type(typ)
            if (n.attrs.get("name") or n.label)]


def canonicalize(report, graph, *, threshold=0.62):
    """阶段二：槽位填充后的实体规范化 / 共指合并。"""
    alg_cat = _catalog(graph, "Algorithm")
    bm_cat = _catalog(graph, "Benchmark")
    code_cat = set(x["name"] for x in _catalog(graph, "CodeFunction"))
    cmap, aliases = {}, {}
    e2 = ((report.get("stages") or {}).get("E2_algorithm") or {}).get("data") or {}
    e3 = ((report.get("stages") or {}).get("E3_benchmark") or {}).get("data") or {}

    def resolve(name, cat, typ):
        if not name:
            return None
        for x in cat:
            if _norm(x["name"]) == _norm(name):
                return {"canonical": x["name"], "node_id": x["id"],
                        "match": "exact", "score": 1.0}
        best, score = None, 0.0
        for x in cat:
            sc = _sim(name, x["name"])
            if sc > score:
                best, score = x, sc
        if best and score >= threshold:
            return {"canonical": best["name"], "node_id": best["id"],
                    "match": "fuzzy", "score": round(score, 3)}
        return {"canonical": name, "node_id": "", "match": "new",
                "score": 0.0, "type": typ}

    for a in e2.get("algorithms") or []:
        nm = a.get("name")
        if nm:
            r = resolve(nm, alg_cat, "Algorithm")
            cmap["algorithm:" + nm] = r
            if r["match"] == "fuzzy":
                aliases[nm] = r["canonical"]
        for m in a.get("modules") or []:
            for sym in m.get("code_symbols") or []:
                hit = next((c for c in code_cat
                            if _norm(c) == _norm(sym)), None)
                cmap["code:" + str(sym)] = {
                    "canonical": hit or sym,
                    "match": "grounded" if hit else "ungrounded",
                    "node_id": "", "score": 1.0 if hit else 0.0}
    for b in e3.get("benchmarks") or []:
        nm = b.get("name")
        if nm:
            r = resolve(nm, bm_cat, "Benchmark")
            cmap["benchmark:" + nm] = r
            if r["match"] == "fuzzy":
                aliases[nm] = r["canonical"]
    return {"canonical_map": cmap, "alias_groups": aliases,
            "n_exact": sum(1 for v in cmap.values()
                           if v.get("match") == "exact"),
            "n_fuzzy": len(aliases),
            "n_new": sum(1 for v in cmap.values()
                         if v.get("match") == "new"),
            "n_ungrounded_code": sum(1 for v in cmap.values()
                                     if v.get("match") == "ungrounded")}


def ground_relations(report, slices, full_text=None):
    """阶段三：每条关系要求逐字定位，无依据标 ungrounded。
    优先用全文（证据可能落在切片之外）。
    """
    from .validator import _norm_evidence
    text = _norm_evidence(full_text or "\n".join(slices.values() or ""))
    out = {"grounded": [], "ungrounded": [], "n": 0}
    rels = list((report.get("lineage") or {}).get("all") or [])
    rels += [{"from": x.get("module"), "to": x.get("target"),
              "kind": x.get("kind"), "evidence": x.get("evidence")}
             for x in (report.get("application_hints") or {})
             .get("tools_formulas") or []]
    for r in rels:
        ev = str(r.get("evidence") or "")
        src, dst = str(r.get("from") or ""), str(r.get("to") or "")
        pos = text.find(_norm_evidence(ev)) if _norm_evidence(ev) else -1
        if pos < 0 and len(ev) > 24:
            # 长引文允许前半段命中（尾注/换行常被截断）
            pos = text.find(_norm_evidence(ev[:40]))
        row = {"from": src, "to": dst, "kind": r.get("kind"),
               "char_offset": pos, "evidence": ev[:120]}
        if pos >= 0 and src and dst:
            out["grounded"].append(row)
        else:
            row["reason"] = ("no_verbatim_evidence" if not ev
                             else "evidence_not_in_source")
            out["ungrounded"].append(row)
        out["n"] += 1
    return out


def track_modules(report, *, ast_symbols=None):
    """阶段四：算法模块追踪（顺序/依赖/信息流/代码对齐）。"""
    e2 = ((report.get("stages") or {}).get("E2_algorithm") or {}).get("data") or {}
    chains = []
    for a in e2.get("algorithms") or []:
        chain = []
        for i, m in enumerate(a.get("modules") or []):
            ins = str(m.get("inputs") or "")
            outs = str(m.get("outputs") or "")
            syms = list(m.get("code_symbols") or [])
            aligned = [s for s in syms
                       if not ast_symbols or s in ast_symbols]
            chain.append({
                "step_order": i + 1,
                "name": m.get("name") or "",
                "depends_on": chain[i - 1]["name"] if i else "",
                "data_flow": (chain[i - 1]["outputs"] + " -> " + ins)
                if i else ins,
                "inputs": ins, "outputs": outs,
                "goal": str(m.get("mechanism") or "")[:80],
                "formula": m.get("formula") or "",
                "code_symbols": syms, "code_aligned": aligned,
                "code_alignment_rate": round(
                    len(aligned) / max(len(syms), 1), 3)})
        chains.append({"algorithm": a.get("name"), "modules": chain,
                       "n_modules": len(chain),
                       "pipeline": " -> ".join(
                           x["name"] for x in chain if x["name"])})
    return {"chains": chains, "n_algorithms": len(chains),
            "n_modules": sum(c["n_modules"] for c in chains)}


def slot_audit(report, graph):
    """槽位质量审计：必填覆盖、类型、词表、质量分。"""
    stages = report.get("stages") or {}
    checks = []
    def add(name, ok, detail=""):
        checks.append({"slot": name, "ok": bool(ok), "detail": str(detail)[:40]})
    e1 = (stages.get("E1_paper") or {}).get("data") or {}
    add("Paper.research_question", e1.get("research_question"))
    add("Paper.problem_category", e1.get("problem_category"),
        e1.get("problem_category") or "")
    if "E2_algorithm" in stages:
        e2 = (stages.get("E2_algorithm") or {}).get("data") or {}
        algs = e2.get("algorithms") or []
        add("Algorithm.mechanism", bool(algs) and all(a.get("mechanism") for a in algs))
        mods = [m for a in algs for m in (a.get("modules") or [])]
        add("AlgorithmModule.inputs", bool(mods) and all(m.get("inputs") for m in mods))
        add("AlgorithmModule.outputs", bool(mods) and all(m.get("outputs") for m in mods))
    if "E3_benchmark" in stages:
        e3 = (stages.get("E3_benchmark") or {}).get("data") or {}
        bms = e3.get("benchmarks") or []
        add("Benchmark.input_form", bool(bms) and all(b.get("input_form") for b in bms))
        add("Benchmark.output_form", bool(bms) and all(b.get("output_form") for b in bms))
    if "E4_values" in stages:
        add("Benchmark.model_results", bool((report.get("model_results") or {})
                                            .get("deduplicated")))
    ok = sum(1 for c in checks if c["ok"])
    return {"checks": checks, "n_ok": ok, "n_total": len(checks),
            "score": round(ok / max(len(checks), 1), 3)}


def apply_paradigm(report, *, graph=None, slices=None, ast_symbols=None,
                   full_text=None):
    """对一份 run_extraction 结果做范式化，写入 report["paradigm"]。"""
    sl = slices or {}
    rep = {
        "ner": recognize_entities(sl, graph),
        "canonicalization": canonicalize(report, graph),
        "relations": ground_relations(report, sl, full_text=full_text),
        "modules": track_modules(report, ast_symbols=ast_symbols),
        "slot_audit": slot_audit(report, graph)}
    rep["summary"] = {
        "n_entity_candidates": sum(len(v) for v in rep["ner"].values()),
        "n_grounded_relations": len(rep["relations"]["grounded"]),
        "n_ungrounded_relations": len(rep["relations"]["ungrounded"]),
        "n_modules_tracked": rep["modules"]["n_modules"],
        "slot_score": rep["slot_audit"]["score"]}
    report["paradigm"] = rep
    return report
