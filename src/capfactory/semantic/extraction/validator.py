"""语义层抽取校验器：封闭词表 + 类型归一 + 逐字证据 + 辅助字段不阻断核心。

沿用 paper_core 的教训：关系线索是辅助产物，类型不符一律归一为空，
不阻断核心属性（旧版曾因此只有 1/10 成功）。
"""
from __future__ import annotations
import re
from typing import Any, Dict, List, Tuple

from .contracts import (E_CONTRACTS, FORM_VOCAB, DOMAIN_CODES,
                        _task_types, _families)

NUM_PAT = re.compile(r"^[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?$")
BAD_VALUE_WORDS = ("epoch", "learning rate", "dropout", "table", "year",
                   "arxiv", "et al", "ref", "[", "]")


def _list(v: Any) -> List[Any]:
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v.strip():
        return [v.strip()]
    return []


def _str(v: Any) -> str:
    if v is None or isinstance(v, (dict, list)):
        return ""
    return str(v).strip()


def _norm_evidence(s: str) -> str:
    """归一空白/弯引号/断词连字符，避免 blocks 拼接造成的假阴性。"""
    s = (s or "").replace("\u2019", "'").replace("\u2018", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    s = re.sub(r"-\s*\n\s*", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def _vocab_or_other(name: str, value: Any, data: Dict[str, Any],
                    issues: List[str]) -> str:
    """词表内原样保留；词表外归为 other 并收集 proposed_new 候选。"""
    from .vocab import values, observe
    v = _str(value)
    if not v:
        return ""
    if v.lower() == "other":
        prop = data.get("proposed_new") or data.get("proposed") or ""
        if isinstance(prop, (list, tuple)):
            prop = prop[0] if prop else ""
        if prop:
            observe(name, _str(prop))
            issues.append("other:proposed_new:" + _str(prop)[:40])
        return "other"
    if v in values(name):
        return v
    r = observe(name, v)
    issues.append("other:out_of_vocab:" + name + ":" + v[:40])
    if r.get("promoted"):
        issues.append("other:promoted:" + v[:40])
    return "other"


def _evidence_ok(q: str, text: str) -> bool:
    q = _str(q)
    if not q or len(q) > 200:
        return False
    return _norm_evidence(q) in _norm_evidence(text or "")


def _e1(data, source_text, issues):
    out = {"research_question": _str(data.get("research_question"))[:220],
           "problem_category": _str(data.get("problem_category")),
           "domain_code": _str(data.get("domain_code")),
           "why_hard": _str(data.get("why_hard"))[:220]}
    hints = data.get("relation_hints")
    hints = hints if isinstance(hints, dict) else {}
    out["relation_hints"] = {k: _list(hints.get(k))[:6] for k in
                             ("related_papers", "algorithms", "benchmarks")}
    ev = data.get("evidence") if isinstance(data.get("evidence"), dict) else {}
    out["evidence"] = {k: _str(ev.get(k))[:140] for k in
                       ("research_question", "why_hard")}
    # 可复用输入 / 写作方法论字段（供阶段02-12 检索）
    out["paradigm"] = _str(data.get("paradigm"))
    out["evidence_type"] = _str(data.get("evidence_type"))
    out["evidence_norm"] = _list(data.get("evidence_norm"))[:8]
    out["authors"] = _list(data.get("authors"))[:12]
    out["abstract"] = _str(data.get("abstract"))[:2000]
    out["claims"] = [{"statement": _str(c.get("statement"))[:80],
                      "evidence": _str(c.get("evidence"))[:120]}
                     for c in _list(data.get("claims"))[:6]
                     if isinstance(c, dict)]
    out["references"] = _list(data.get("references"))[:20]
    out["figures"] = [{"label": _str(f.get("label"))[:20],
                       "caption": _str(f.get("caption"))[:160],
                       "kind": _str(f.get("kind")),
                       "for_contribution": _str(f.get("for_contribution"))[:40]}
                      for f in _list(data.get("figures"))[:12]
                      if isinstance(f, dict)]
    out["section_map"] = [{"section": _str(x.get("section"))[:40],
                           "claims": _list(x.get("claims"))[:6]}
                          for x in _list(data.get("section_map"))[:20]
                          if isinstance(x, dict)]
    out["gaps"] = [{"gap_type": _str(g.get("gap_type")),
                    "statement": _str(g.get("statement"))[:80],
                    "evidence": _str(g.get("evidence"))[:120]}
                   for g in _list(data.get("gaps"))[:6]
                   if isinstance(g, dict)]
    # 前沿/失败/协议/写作惯例：别人的客观事实，供后续阶段检索
    out["open_problems"] = [{"statement": _str(x.get("statement"))[:80],
                             "evidence": _str(x.get("evidence"))[:120]}
                            for x in _list(data.get("open_problems"))[:6]
                            if isinstance(x, dict)]
    out["delta_claims"] = [{"statement": _str(x.get("statement"))[:80],
                            "baseline": _str(x.get("baseline"))[:40],
                            "evidence": _str(x.get("evidence"))[:120]}
                           for x in _list(data.get("delta_claims"))[:6]
                           if isinstance(x, dict)]
    out["negative_results"] = _list(data.get("negative_results"))[:8]
    out["protocol_disclosure"] = _list(data.get("protocol_disclosure"))[:8]
    out["citation_style"] = _str(data.get("citation_style"))
    out["writing_style"] = _str(data.get("writing_style"))[:200]
    # P2/P4/P6 支撑字段（规则可抽，也允许 LLM 补）
    out["data_sources"] = _list(data.get("data_sources"))[:8]
    out["dedup_rule"] = _str(data.get("dedup_rule"))[:120]
    out["split_spec"] = _str(data.get("split_spec"))[:80]
    out["hyperparams"] = [{"param": _str(x.get("param"))[:40],
                           "value": _str(x.get("value"))[:40],
                           "context": _str(x.get("context"))[:100]}
                          for x in _list(data.get("hyperparams"))[:8]
                          if isinstance(x, dict)]
    out["formal_def"] = _str(data.get("formal_def"))[:200]
    out["old_forms"] = _list(data.get("old_forms"))[:4]
    out["method_limits"] = _list(data.get("method_limits"))[:6]
    out["result_tables"] = [{"label": _str(x.get("label"))[:40],
                             "columns": _list(x.get("columns"))[:12],
                             "rows": _list(x.get("rows"))[:30]}
                            for x in _list(data.get("result_tables"))[:3]
                            if isinstance(x, dict)]
    if not out["research_question"]:
        issues.append("missing:research_question")
    out["problem_category"] = _vocab_or_other(
        "problem_category", out["problem_category"], data, issues)
    out["domain_code"] = _vocab_or_other(
        "domain_code", out["domain_code"], data, issues)
    for k, v in list(out["evidence"].items()):
        if v and not _evidence_ok(v, source_text):
            out["evidence"][k] = ""
            issues.append(f"warn:evidence_not_verbatim:{k}")
    return out


def _e2(data, issues):
    clean = []
    for a in _list(data.get("algorithms"))[:3]:
        if not isinstance(a, dict):
            continue
        item = {"name": _str(a.get("name"))[:60],
                "task_type": _str(a.get("task_type")),
                "problems_solved": _list(a.get("problems_solved"))[:3],
                "mechanism": _str(a.get("mechanism"))[:300],
                "why_it_works": _str(a.get("why_it_works"))[:220],
                "applicable_to": _list(a.get("applicable_to"))[:6],
                "limitations": _list(a.get("limitations"))[:6],
                # P1 架构要素
                "arch_modules": [{"name": _str(m.get("name"))[:40],
                                  "role": _str(m.get("role"))[:100],
                                  "input": _str(m.get("input"))[:60],
                                  "output": _str(m.get("output"))[:60]}
                                 for m in _list(a.get("arch_modules"))[:6]
                                 if isinstance(m, dict)],
                "why_not_other": _str(a.get("why_not_other"))[:200],
                "key_challenge": _str(a.get("key_challenge"))[:160],
                "modules": []}
        item["task_type"] = _vocab_or_other(
            "task_type", item["task_type"], a, issues)
        for m in _list(a.get("modules"))[:6]:
            if not isinstance(m, dict):
                continue
            item["modules"].append({
                "name": _str(m.get("name"))[:60],
                "mechanism": _str(m.get("mechanism"))[:160],
                "formula": _str(m.get("formula"))[:160],
                "inputs": _str(m.get("inputs"))[:120],
                "outputs": _str(m.get("outputs"))[:120],
                "code_symbols": _list(m.get("code_symbols"))[:8],
                "tools": _list(m.get("tools"))[:6],
                "is_novel_component": bool(m.get("is_novel_component", False)),
                "component_role": _str(m.get("component_role"))})
        if item["name"] and item["mechanism"]:
            clean.append(item)
    if not clean:
        issues.append("missing:algorithm_core")
    for a in clean:
        a["assumptions"] = _list(data.get("assumptions"))[:6] \
            if not a.get("assumptions") else _list(a.get("assumptions"))[:6]
        a["novelty_basis"] = _list(data.get("novelty_basis"))[:6] \
            if not a.get("novelty_basis") else _list(a.get("novelty_basis"))[:6]
    return {"algorithms": clean}


def _e3(data, issues):
    clean = []
    for b in _list(data.get("benchmarks"))[:3]:
        if not isinstance(b, dict):
            continue
        item = {"name": _str(b.get("name"))[:60],
                "input_form": _str(b.get("input_form")),
                "output_form": _str(b.get("output_form")),
                "n_samples": _str(b.get("n_samples"))[:60],
                "scale": _str(b.get("scale"))[:60],
                "modality": _str(b.get("modality"))[:60],
                "research_object": _str(b.get("research_object"))[:60],
                "protocol": {k: (int(v) if k == "seeds" and str(v).isdigit()
                                 else _str(v)[:80])
                             for k, v in (b.get("protocol") or {}).items()
                             if k in ("seeds", "split", "eval_script", "epochs", "hardware")},
                "failure_modes": _list(b.get("failure_modes"))[:10],
                "metrics": []}
        for k in ("input_form", "output_form"):
            item[k] = _vocab_or_other("form", item[k], b, issues)
        for m in _list(b.get("metrics"))[:4]:
            md = {"name": "", "unit": "", "direction": ""}
            if isinstance(m, dict):
                md = {"name": _str(m.get("name"))[:40],
                      "unit": _str(m.get("unit"))[:20],
                      "direction": _str(m.get("direction")),
                      "contribution_link": _str(m.get("contribution_link"))[:20]}
            elif isinstance(m, str):
                md["name"] = m[:40]
            if md["direction"] not in ("min", "max"):
                md["direction"] = ""
            if md["name"]:
                item["metrics"].append(md)
        if item["name"]:
            clean.append(item)
    if not clean:
        # 没有明确评测基准是合法情况（理论/方法论文），不阻断整篇
        issues.append("warn:no_benchmark")
    return {"benchmarks": clean}


def _e4(data, source_text, issues):
    rows = []
    for r in _list(data.get("model_results"))[:8]:
        if not isinstance(r, dict):
            continue
        val = r.get("value")
        if isinstance(val, str) and not NUM_PAT.match(val.strip()):
            continue
        if any(w in str(r.get("metric", "")).lower()
               for w in BAD_VALUE_WORDS):
            continue
        ev = _str(r.get("evidence"))[:140]
        if ev and not _evidence_ok(ev, source_text):
            ev = ""
            issues.append("warn:evidence_not_verbatim")
        rows.append({"model": _str(r.get("model"))[:60],
                     "metric": _str(r.get("metric"))[:40],
                     "value": val, "unit": _str(r.get("unit"))[:20],
                     "benchmark": _str(r.get("benchmark"))[:60],
                     "source": _str(r.get("source"))[:60],
                     "evidence": ev})
    return {"model_results": rows}


def _e5(data, issues):
    rels = []
    for r in _list(data.get("relations"))[:12]:
        if not isinstance(r, dict):
            continue
        kind = _str(r.get("kind"))
        if kind not in ("tool", "formula"):
            issues.append("warn:bad_relation_kind")
            continue
        rels.append({"module": _str(r.get("module"))[:60],
                     "kind": kind,
                     "target": _str(r.get("target"))[:80],
                     "evidence": _str(r.get("evidence"))[:140]})
    return {"relations": rels}


def _e6(data, source_text, issues):
    kinds = {"extends", "replaces", "improves", "compared_with"}
    rows = []
    for r in _list(data.get("lineage"))[:6]:
        if not isinstance(r, dict):
            continue
        kind = _str(r.get("kind"))
        if kind not in kinds:
            issues.append("warn:bad_lineage_kind")
            continue
        ev = _str(r.get("evidence"))[:140]
        if ev and not _evidence_ok(ev, source_text):
            ev = ""
            issues.append("warn:evidence_not_verbatim")
        src, dst = _str(r.get("from"))[:60], _str(r.get("to"))[:60]
        if not src or not dst or src == dst:
            continue
        rows.append({"from": src, "to": dst, "kind": kind,
                     "evidence": ev})
    return {"lineage": rows}


def validate(stage: str, data: Any, *, source_text: str = ""
             ) -> Tuple[Dict[str, Any], List[str]]:
    """返回 (归一化数据, 问题列表)。只有核心字段缺失才算致命。"""
    if not isinstance(data, dict):
        return {}, [f"{stage}:not_a_dict"]
    issues: List[str] = []
    if stage == "E1_paper":
        out = _e1(data, source_text, issues)
    elif stage == "E2_algorithm":
        out = _e2(data, issues)
    elif stage == "E3_benchmark":
        out = _e3(data, issues)
    elif stage == "E4_values":
        out = _e4(data, source_text, issues)
    elif stage == "E5_relations":
        out = _e5(data, issues)
    elif stage == "E6_lineage":
        out = _e6(data, source_text, issues)
    else:
        return {}, [f"unknown_stage:{stage}"]
    return out, issues


def fatal(issues: List[str]) -> List[str]:
    return [x for x in issues
            if not x.startswith("warn:") and not x.startswith("other:")]


def retry_contract(stage: str) -> str:
    """第 2+ 次重试时的收窄契约（沿用 paper_core 成功经验）。"""
    c = E_CONTRACTS[stage]
    return ("【收窄重试】只输出必填字段，其余一律省略：\n"
            + "\n".join(f"- {k}" for k in c["required"])
            + "\n不要输出可选字段、不要解释、不要代码块。")


def cross_check(stage: str, out: Dict[str, Any], *,
                ast_symbols: set | None = None,
                module_names: set | None = None) -> List[str]:
    """跨阶段一致性：代码符号必须真实存在、关系模块必须是抽出的模块名。"""
    warns: List[str] = []
    if stage == "E2_algorithm" and ast_symbols:
        for a in out.get("algorithms") or []:
            for m in a.get("modules") or []:
                for s in m.get("code_symbols") or []:
                    if s not in ast_symbols:
                        warns.append(f"unknown_code_symbol:{s}")
    if stage == "E5_relations" and module_names:
        for r in out.get("relations") or []:
            if r["module"] not in module_names:
                warns.append(f"unknown_module:{r['module']}")
    return warns
