# DEPRECATED (2026-11-14): 旧抽取链路，仅保留给历史测试与旧 /extraction 页面。
# 新增抽取一律走 capfactory.semantic.extraction.runner.run_extraction；
# pipeline 与 sciforge.core 已统一到新链路。本文件计划后续迁入 backup/。
"""论文库重设计：只保留「研究什么问题 / 属于哪个领域 / 算法族」三核心。

参考算法库 v2 范式（问题/机理为核心），并按用户要求：
* 去掉研究对象、数据模态等分类维度；
* 论文抽取的核心 = 填充这三个关键属性 + 产出「关系线索」
  （相关文献 / 算法提及 / 数据提及），供后续论文、算法、数据库抽取复用；
* problem_type 复用算法库的 TASK_TYPES，使「论文的问题」与「算法的任务类型」
  直接对齐，便于找可比较方法与代码复现方向。
"""
from __future__ import annotations
import json, re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..po.vocab import DOMAIN_NAMES
from .algorithm_schema import FAMILIES as ALGO_FAMILIES, classify_rule
from .algorithm_problem import TASK_TYPES

CORE_FIELDS = ("title", "arxiv_id", "research_problem", "problem_type",
               "domain", "domain_code", "algorithm_family",
               "algorithm_family_id", "why_hard", "evidence",
               "relation_hints")
CORE_LABELS = {
    "title": "论文标题", "arxiv_id": "arXiv ID",
    "research_problem": "研究什么问题", "problem_type": "问题类型",
    "domain": "所属领域", "domain_code": "领域码",
    "algorithm_family": "算法族（和什么方向的方法比较）",
    "algorithm_family_id": "算法族 ID",
    "why_hard": "现有方法瓶颈", "evidence": "原文依据",
    "relation_hints": "关系线索（供后续抽取）"}
FACET_LABELS = {"domain": "所属领域", "problem_type": "研究问题",
                "algorithm_family": "算法族"}

DOMAIN_ALIASES = {
    "D0": ["通用", "cross domain", "benchmark", "survey"],
    "D1": ["分子生成", "de novo", "molecular generation", "fragment"],
    "D2": ["分子优化", "optimization", "multi-objective", "lead optimization"],
    "D3": ["反应", "retrosynthesis", "reaction", "synthesis planning"],
    "D4": ["性质预测", "admet", "property prediction", "qsar", "logp"],
    "D5": ["多肽", "peptide", "amp", "antimicrobial"],
    "D6": ["蛋白", "antibody", "protein", "pocket", "docking", "folding"],
    "D7": ["材料", "crystal", "material", "force field", "dynamics"],
    "D8": ["数据集", "instruction", "dataset", "corpus", "benchmark"],
    "D9": ["表征学习", "representation", "pretrain", "self-supervised"],
    "D10": ["力场", "mlip", "potential energy", "molecular dynamics"],
}

EXTRACT_PROMPT = """你是论文核心属性抽取器。只输出**三个关键属性**与关系线索，
不要复述全文，不要输出其它字段。

【论文标题】{title}
【摘要与引言片段】{text}

输出严格 JSON（纯 JSON，不要代码块）：
{
 "research_problem": "这篇论文研究的是什么问题（1-2 句，<=140字，说清输入、目标与约束）",
 "problem_type": 只能从 {task_types} 选一个 id,
 "domain_code": 只能从 {domain_codes} 选一个,
 "algorithm_family_id": 只能从 {family_ids} 选一个,
 "why_hard": "现有方法在该问题上的瓶颈（<=90字）",
 "evidence": "从片段里逐字复制、能支撑上述判断的短句（<=100字）",
 "related_paper_hints": ["相关文献的引用标号，如 [12]（最多 8 个）"],
 "algorithm_mentions": ["文中提到的算法/方法名（最多 8 个）"],
 "benchmark_mentions": ["文中提到的数据集/基准名（最多 8 个）"]
}
规则：
1. 四个封闭字段只能选给定 id；判断不了填 "unknown"。
2. research_problem 必须具体，不要写成「本文提出一个新方法」这类空话。
3. evidence 必须逐字来自片段；没有就填空字符串。
4. 关系线索只从片段里抽，禁止编造。
"""


def guess_domain(text: str, declared: str = "") -> str:
    if declared in DOMAIN_NAMES:
        return declared
    low = (text or "").lower()
    best, hits = "", 0
    for code, words in DOMAIN_ALIASES.items():
        n = sum(1 for w in words if w.lower() in low)
        if n > hits:
            best, hits = code, n
    return best or "D0"


def _validate(d: Dict[str, Any], text: str) -> List[str]:
    issues = []
    if d.get("problem_type") not in TASK_TYPES and \
            d.get("problem_type") != "unknown":
        issues.append("bad_problem_type")
    if d.get("domain_code") not in DOMAIN_NAMES and \
            d.get("domain_code") != "unknown":
        issues.append("bad_domain_code")
    if d.get("algorithm_family_id") not in ALGO_FAMILIES and \
            d.get("algorithm_family_id") != "unknown":
        issues.append("bad_algorithm_family_id")
    rp = str(d.get("research_problem") or "")
    if len(rp) < 20:
        issues.append("research_problem_too_short")
    # 关系线索是辅助产物，缺失/类型不符一律归一为空列表，不阻断核心属性
    ev = str(d.get("evidence") or "")
    if ev and ev not in text:
        issues.append("evidence_not_verbatim")
    return issues


def extract_paper(title: str, text: str, *, chat_fn: Any = None,
                  declared_domain: str = "") -> Dict[str, Any]:
    """论文抽取核心：判领域 → 判问题类型 → 判算法族 → 生成问题描述 + 关系线索。"""
    from ..llm.backends import chat as _chat
    from ..utils import parse_llm_json
    prompt = (EXTRACT_PROMPT
              .replace("{title}", title)
              .replace("{text}", (text or "")[:6000])
              .replace("{task_types}", ", ".join(TASK_TYPES))
              .replace("{domain_codes}", ", ".join(DOMAIN_NAMES))
              .replace("{family_ids}", ", ".join(ALGO_FAMILIES)))
    fn = chat_fn or (lambda p, **kw: _chat(p, backend="vllm", **kw))
    attempts, issues = [], []
    for i in range(3):
        try:
            raw = fn(prompt, max_tokens=1400, timeout=240)
            d = parse_llm_json(raw) or {}
            for k in ("related_paper_hints", "algorithm_mentions",
                      "benchmark_mentions"):
                v = d.get(k)
                if v is None:
                    d[k] = []
                elif isinstance(v, str):
                    d[k] = [x.strip() for x in re.split(r"[,;，；]", v)
                            if x.strip()][:8]
                elif not isinstance(v, list):
                    d[k] = []
            issues = _validate(d, text)
            # 领域/族的规则判定作为强先验，LLM 偏离时纠正
            rule_dom = guess_domain(title + " " + text[:1500], declared_domain)
            if d.get("domain_code") in DOMAIN_NAMES and \
                    d["domain_code"] != rule_dom:
                d["domain_code_recommended"] = rule_dom
            attempts.append({"i": i, "issues": issues[:6],
                             "out_chars": len(raw or "")})
            if not issues:
                return {"ok": True, "data": d, "attempts": attempts}
            if i == 1:
                prompt += ('\n【收窄契约】只输出 6 个字段：research_problem, '
                           'problem_type, domain_code, algorithm_family_id, '
                           'evidence, algorithm_mentions；evidence 留空字符串。')
            else:
                prompt += "\n【修正】" + "; ".join(issues[:4])
        except Exception as exc:  # noqa: BLE001
            attempts.append({"i": i, "error": str(exc)[:120]})
    return {"ok": False, "issues": issues, "attempts": attempts}


def core_of(p: Any, extracted: Dict[str, Any], *,
            declared_domain: str = "") -> Dict[str, Any]:
    d = extracted or {}
    dc = str(d.get("domain_code") or "")
    if dc not in DOMAIN_NAMES:
        dc = guess_domain(p.label + " " + str(p.attrs.get("title") or ""),
                          declared_domain)
    fam = str(d.get("algorithm_family_id") or "")
    if fam not in ALGO_FAMILIES:
        fam = classify_rule(str(p.attrs.get("title") or "")) or "unknown"
    hints = {
        "related_papers": d.get("related_paper_hints") or [],
        "algorithms": d.get("algorithm_mentions") or [],
        "benchmarks": d.get("benchmark_mentions") or [],
    }
    return {
        "title": str(p.attrs.get("title") or p.label),
        "arxiv_id": str(p.attrs.get("arxiv_id") or p.id.split(":")[-1]),
        "research_problem": d.get("research_problem") or "unknown",
        "problem_type": d.get("problem_type") or "unknown",
        "domain": DOMAIN_NAMES.get(dc, dc),
        "domain_code": dc,
        "algorithm_family": ALGO_FAMILIES.get(fam, {}).get("label", fam),
        "algorithm_family_id": fam,
        "why_hard": d.get("why_hard") or "unknown",
        "evidence": d.get("evidence") or "",
        "relation_hints": hints,
        "schema_version": "v3_paper_core",
        "filled_by": "llm_paper_core",
    }


def _front_text(aid: str) -> str:
    """摘要/引言片段：标题后前 6000 字符，够判领域/问题/族。"""
    p = Path("/home/zengshuxin/xKG-main/data/docx") / f"{aid}.md"
    if not p.exists():
        return ""
    md = p.read_text(encoding="utf-8", errors="replace")
    return md[:6000]


def fill_library(graph: Any, *, chat_fn: Any = None,
                 use_llm: bool = True, persist: bool = True,
                 limit: int = 0) -> Dict[str, Any]:
    """真跑重抽全部论文，写回三核心属性 + 关系线索。"""
    papers = list(graph.by_type("Paper"))
    if limit:
        papers = papers[:limit]
    rep: Dict[str, Any] = {"n_papers": len(papers), "n_ok": 0,
                           "n_failed": 0, "by_domain": {},
                           "by_problem_type": {}, "by_algorithm_family": {},
                           "per_paper": {}, "seconds": 0.0}
    import time
    t0 = time.time()
    for p in papers:
        aid = str(p.attrs.get("arxiv_id") or p.id.split(":")[-1])
        title = str(p.attrs.get("title") or p.label)
        declared = (p.attrs.get("domain_codes") or [""])[0]
        text = _front_text(aid)
        if use_llm and text:
            r = extract_paper(title, text, chat_fn=chat_fn,
                              declared_domain=str(declared or ""))
        else:
            r = {"ok": False, "issues": ["no_text_or_llm_disabled"]}
        core = core_of(p, r.get("data") or {}, declared_domain=str(declared or ""))
        label = p.label
        # 保留内部锚点元数据（下游 GenerationFlow 依赖，但不进卡片/facet）
        keep = {k: v for k, v in p.attrs.items()
                if k in ("domain_codes", "algo_codes", "paper_type",
                         "evidence_ids", "provenance")}
        p.attrs.clear()
        p.attrs.update({"label": label})
        p.attrs.update(keep)
        p.attrs.update(core)
        if r["ok"]:
            rep["n_ok"] += 1
        else:
            rep["n_failed"] += 1
            core["filled_by"] = "rule_fallback"
        rep["per_paper"][aid] = {
            "ok": r["ok"], "attempts": len(r.get("attempts") or []),
            "issues": r.get("issues"),
            "domain": core["domain"], "problem_type": core["problem_type"],
            "algorithm_family": core["algorithm_family"],
            "research_problem": core["research_problem"][:90],
            "n_hints": sum(len(v) for v in
                           core["relation_hints"].values())}
        for key, val in (("by_domain", core["domain"]),
                         ("by_problem_type", core["problem_type"]),
                         ("by_algorithm_family", core["algorithm_family"])):
            rep[key][val] = rep[key].get(val, 0) + 1
    rep["seconds"] = round(time.time() - t0, 1)
    if persist:
        out = Path("storage_cf/sciforge/paper_core_report.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rep, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        graph.save("storage_cf/sciforge/batch10_final_graph.json")
    return rep


PAPERS_CSV = Path("/home/zengshuxin/xKG-main/data/papers/papers.csv")


def csv_domain(aid: str) -> str:
    """领域权威来源：papers.csv 的 D 码（比 LLM 更稳）。"""
    import csv
    if not PAPERS_CSV.exists():
        return ""
    with PAPERS_CSV.open(encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if (r.get("arxiv_id") or "").strip() == aid:
                return (r.get("domain") or "").strip()
    return ""


FAMILY_BY_TASK = {
    "forcefield_simulation": "ml_potential",
    "sequence_design": "peptide_lm",
    "structure_docking": "inverse_folding",
    "molecule_generation": "fragment",
    "sampling_acceleration": "speculative_sampling",
    "instruction_multitask": "general_lm",
    "representation_pretrain": "general_lm",
    "classifier_screening": "classifier_guidance",
    "wetlab_baseline": "wetlab",
}


def apply_domain_rules(graph: Any, *, persist: bool = True) -> Dict[str, Any]:
    """复用已抽的 research_problem，按 CSV 与规则重算领域/算法族。"""
    rep: Dict[str, Any] = {"n_papers": 0, "changed_domain": [],
                           "changed_family": [], "by_domain": {},
                           "by_algorithm_family": {}}
    for p in graph.by_type("Paper"):
        aid = str(p.attrs.get("arxiv_id") or "")
        old_d = p.attrs.get("domain")
        old_f = p.attrs.get("algorithm_family_id")
        dc = csv_domain(aid) or guess_domain(p.label) or "D0"
        fam = old_f if old_f in ALGO_FAMILIES else ""
        task = p.attrs.get("problem_type")
        # 优先用「本论文提出的方法」的族：PROPOSES_METHOD → Algorithm.schema_family
        proposed = [a.target for a in graph.outgoing(p.id)
                    if a.relation == "PROPOSES_METHOD"
                    and a.target in graph.nodes]
        fam_from_method = ""
        for mid in proposed:
            mf = (graph.nodes[mid].attrs.get("schema_family") or "")
            if mf in ALGO_FAMILIES:
                fam_from_method = mf
                break
        fam_rule = fam_from_method or classify_rule(p.label) or \
            FAMILY_BY_TASK.get(task, "")
        # LLM 给通用族 / unknown 时，用规则族纠正
        if fam_from_method or (not fam or fam in (
                "general_lm", "unknown", "autoregressive")) \
                and fam_rule in ALGO_FAMILIES:
            fam = fam_rule
        if fam not in ALGO_FAMILIES:
            fam = FAMILY_BY_TASK.get(task, "autoregressive")
        p.attrs["domain_code"] = dc
        p.attrs["domain"] = DOMAIN_NAMES.get(dc, dc)
        p.attrs["algorithm_family_id"] = fam
        p.attrs["algorithm_family"] = ALGO_FAMILIES.get(
            fam, {}).get("label", fam)
        if old_d != p.attrs["domain"]:
            rep["changed_domain"].append({"arxiv_id": aid,
                                          "from": old_d,
                                          "to": p.attrs["domain"]})
        if old_f != fam:
            rep["changed_family"].append({"arxiv_id": aid,
                                          "from": old_f, "to": fam})
        rep["n_papers"] += 1
        rep["by_domain"][p.attrs["domain"]] = \
            rep["by_domain"].get(p.attrs["domain"], 0) + 1
        rep["by_algorithm_family"][p.attrs["algorithm_family"]] = \
            rep["by_algorithm_family"].get(
                p.attrs["algorithm_family"], 0) + 1
    if persist:
        graph.save("storage_cf/sciforge/batch10_final_graph.json")
        Path("storage_cf/sciforge/paper_core_report.json").write_text(
            json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    return rep


def apply_paper_core(graph: Any, arxiv_id: str, md: str, *,
                     chat_fn: Any = None) -> Dict[str, Any]:
    """单篇论文重抽（供 pipeline 调用）：核心三属性 + 关系线索 + 关系索引。"""
    pid = f"paper:{arxiv_id}"
    p = graph.nodes.get(pid)
    if not p:
        return {"ok": False, "reason": f"missing {pid}"}
    title = str(p.attrs.get("title") or p.label)
    r = extract_paper(title, md[:6000], chat_fn=chat_fn,
                      declared_domain=csv_domain(arxiv_id))
    core = core_of(p, r.get("data") or {},
                   declared_domain=csv_domain(arxiv_id))
    label = p.label
    keep = {k: v for k, v in p.attrs.items()
            if k in ("domain_codes", "algo_codes", "paper_type",
                     "evidence_ids", "provenance")}
    p.attrs.clear()
    p.attrs.update({"label": label})
    p.attrs.update(keep)
    p.attrs.update(core)
    apply_domain_rules(graph, persist=False)
    from .relation_layer import build_relations
    rel = build_relations(graph, persist=True)
    return {"ok": r["ok"], "arxiv_id": arxiv_id,
            "core": {k: core[k] for k in ("research_problem", "problem_type",
                                          "domain", "algorithm_family")},
            "n_hints": sum(len(v) for v in
                           core["relation_hints"].values()),
            "attempts": len(r.get("attempts") or []),
            "relations": rel}
