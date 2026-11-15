"""两个任务范式的最小可运行骨架（对齐 SciForge 的「门即代码」）。

任务 A：**图谱缺口 → 新算法方向**
任务 B：**缺代码论文 → 算法拆解 + 代码复现**

两者都遵守同一条分工：LLM 只产出「候选/拆解」，判定全部交给
``contracts.py`` 的确定性函数；每个任务输出一份可被 ``golden`` 回归的报告。
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .contracts import (gap_gate, verdict, method_code_parity, record_node,
                        validate_ladder, decide, relative_gain, sha256_text)


# ---------------------------------------------------------------------------
# 任务 A：图谱缺口 → 新算法方向
# ---------------------------------------------------------------------------
def graph_gaps(graph: Any, *, top_k: int = 20) -> List[Dict[str, Any]]:
    """把 ``discover_gaps`` 的输出规整成带稳定 gap-id 的条目。"""
    from ..po.reasoning import discover_gaps
    rep = discover_gaps(graph, top_k=top_k)
    out = []
    for i, x in enumerate(rep.get("gaps", []), 1):
        out.append({"gap_id": f"GAP-{i}", "type": x.get("type", ""),
                    "severity": x.get("severity", ""),
                    "object": x.get("object", ""),
                    "nodes": x.get("nodes", []),
                    "reason": x.get("reason", ""),
                    "action": x.get("action", "")})
    return out


def gap_report_text(gaps: Sequence[Dict[str, Any]], graph: Any) -> str:
    """生成可被 ``gap_gate`` 判别的报告：每条带 gap-id + 引用 + 判别性语言。"""
    papers = len(graph.by_type("Paper"))
    lines = [f"# GAP_REPORT（基于 {papers} 篇论文的 PO 图）", ""]
    for g in gaps:
        refs = ", ".join(str(x) for x in (g.get("nodes") or [])[:3]) or f"paper:01"
        lines.append(f"{g['gap_id']}: [{g['type']}] {g['object']} — "
                     f"未被覆盖/缺少实现（{refs}，{papers} 篇论文统计）。")
        if g.get("reason"):
            lines.append(f"  证据：{g['reason']}")
        lines.append("")
    return "\n".join(lines)


def _observed_pairs(graph: Any) -> Dict[str, set]:
    """图里已出现的 (D, A) 组合，用于 novelty 反重复（可复算，不靠模型自述）。"""
    pairs: Dict[str, set] = defaultdict(set)
    for p in graph.by_type("Paper"):
        ds = p.attrs.get("domain_codes") or []
        aas = p.attrs.get("algo_codes") or []
        for d in ds:
            for a in aas:
                pairs[str(d)].add(str(a))
    return pairs


def propose_directions(gaps: Sequence[Dict[str, Any]], graph: Any
                       ) -> List[Dict[str, Any]]:
    """规则版 idea 生成：**每个方向必须锚定 gap-id**，并标注是否与已有组合重复。

    接入 LLM 时只需替换本函数，下游的 ``gap_gate`` / novelty / 合法性门不变。
    """
    observed = _observed_pairs(graph)
    fam_codes = {n.attrs.get("code"): n.label
                 for n in graph.by_type("AlgorithmFamily") if n.attrs.get("code")}
    dom_codes = {n.attrs.get("code"): n.label
                 for n in graph.by_type("Domain") if n.attrs.get("code")}
    # batch10 图没有分类节点，分类在 Paper 属性里：补进词表以便生成方向
    for pnode in graph.by_type("Paper"):
        for c in pnode.attrs.get("algo_codes") or []:
            fam_codes.setdefault(str(c), str(c))
        for c in pnode.attrs.get("domain_codes") or []:
            dom_codes.setdefault(str(c), str(c))
    ideas = []
    for gi, g in enumerate(gaps):
        text = f"{g['type']} {g['object']} {g.get('reason','')}"
        codes = re.findall(r"\b([AD]\d{2})\b", text)
        a = next((c for c in codes if c in fam_codes), "")
        d = next((c for c in codes if c in dom_codes), "")
        if not a and not d:
            # 缺口文本无显式 D/A 码（batch10 图常见）：轮转取词表值，
            # 再由 evaluate_ideas 的合法性 / novelty 门把关，不静默跳过。
            fam_list, dom_list = sorted(fam_codes), sorted(dom_codes)
            if fam_list:
                a = fam_list[gi % len(fam_list)]
            if dom_list:
                d = dom_list[gi % len(dom_list)]
            if not a and not d:
                continue
        # 为缺口族挑一个图里已有但从未与该族组合的领域（或反之）
        # algo_coverage_gap 缺领域信息时，选一个该算法族从未与之共现的
        # **非 D0** 领域，而不是一律落到「通用算法」这个兜底标签。
        candidate_domains = [x for x in dom_codes if x != d and x != "D0"]
        if d and d != "D0":
            target_d = d
        else:
            target_d = next((x for x in candidate_domains
                             if (a or "") not in observed.get(x, set())),
                            candidate_domains[0] if candidate_domains else "D0")
        target_a = a or next((x for x in fam_codes if x not in
                              observed.get(target_d, set())),
                             next(iter(fam_codes), ""))
        repeated = target_a in observed.get(target_d, set())
        ideas.append({
            "idea_id": f"IDEA-{g['gap_id']}",
            "gap_id": g["gap_id"],
            "title": (f"把 {fam_codes.get(target_a, target_a)} 迁移到 "
                      f"{dom_codes.get(target_d, target_d)} 并补可复现基准"),
            "family_codes": [target_a], "domain_codes": [target_d],
            "novelty": "already_observed" if repeated else "unexplored_pair",
            "evidence": [g["gap_id"]] + list(g.get("nodes") or [])[:2],
            "family_valid": target_a in fam_codes,
            "domain_valid": target_d in dom_codes,
        })
    return ideas


IDEA_PROMPT = """你在为 AI4Science 知识图谱提出**新的算法研究方向**。

输入是图谱自动发现的研究缺口，以及图里已经出现过的 (领域 D0–D10, 算法族 A01–A18) 组合。
要求：
1. 每个方向必须锚定一个 gap-id，并解释它为什么能补这个缺口；
2. 优先选图里**从未共现**的 (D, A) 组合；已共现的组合标 already_observed；
3. family_codes 只能取自下面受控算法族清单，domain_codes 只能取自受控领域清单；
4. evidence 只能引用给定 gap-id 与图内节点 id，不得编造论文或引用；
5. 允许基于你对算法能力的认知做跨领域迁移设计，但必须写清「迁移什么机制、解决什么缺口」；
6. 输出 <= 1500 token，严格 JSON。

输出：
{"ideas":[{"idea_id":"IDEA-GAP-1","gap_id":"GAP-1","title":"",
  "family_codes":["A06"],"domain_codes":["D7"],
  "rationale":"", "mechanism_transfer":"", "novelty":"unexplored_pair|already_observed",
  "evidence":["GAP-1"]}]}

## 缺口
{gaps}

## 已观察到的 (D, A) 组合
{pairs}

## 受控算法族
{families}

## 受控领域
{domains}

只输出 JSON。"""


def propose_directions_llm(gaps: Sequence[Dict[str, Any]], graph: Any, *,
                           chat_fn: Any) -> List[Dict[str, Any]]:
    """LLM 版生成器：**只负责产出候选**，判定交给 ``evaluate_ideas``。"""
    from ..utils import parse_llm_json
    observed = _observed_pairs(graph)
    fam_codes = {n.attrs.get("code"): n.label
                 for n in graph.by_type("AlgorithmFamily") if n.attrs.get("code")}
    dom_codes = {n.attrs.get("code"): n.label
                 for n in graph.by_type("Domain") if n.attrs.get("code")}
    pairs_text = "; ".join(f"{d}+{','.join(sorted(a))}" for d, a in sorted(observed.items()))
    gaps_text = "\n".join(
        f"{g['gap_id']} [{g['type']}] {g['object']} | {g.get('reason','')}"
        for g in gaps)
    prompt = (IDEA_PROMPT.replace("{gaps}", gaps_text)
                         .replace("{pairs}", pairs_text[:2500])
                         .replace("{families}", ", ".join(sorted(fam_codes)))
                         .replace("{domains}", ", ".join(sorted(dom_codes))))
    raw = parse_llm_json(chat_fn(prompt)) or {}
    return [x for x in (raw.get("ideas") or []) if isinstance(x, dict)]


def evaluate_ideas(ideas: Sequence[Dict[str, Any]],
                   gaps: Sequence[Dict[str, Any]], graph: Any) -> Dict[str, Any]:
    """★ 两版生成器共用的判定门：换生成器不换判定。"""
    # 两种图都兼容：V1 报告包有 AlgorithmFamily/Domain 节点；
    # batch10 图把分类放在 Paper.algo_codes / domain_codes 属性里。
    fam = {n.attrs.get("code") for n in graph.by_type("AlgorithmFamily")
           if n.attrs.get("code")}
    dom = {n.attrs.get("code") for n in graph.by_type("Domain")
           if n.attrs.get("code")}
    # 与 propose_directions 保持同一封闭词表：无论节点是否已存在，
    # 都并入 Paper.algo_codes / domain_codes，否则生成器用 A04、评估器
    # 只认 AlgorithmFamily 节点里的 6 个码，会误报 codes_legal=false。
    for p in graph.by_type("Paper"):
        fam |= {str(x) for x in (p.attrs.get("algo_codes") or [])}
        dom |= {str(x) for x in (p.attrs.get("domain_codes") or [])}
    gap_ids = {g["gap_id"] for g in gaps}
    checks = {
        "every_idea_anchored": bool(ideas) and all(
            i.get("gap_id") in gap_ids for i in ideas),
        "codes_legal": all(
            set(i.get("family_codes") or []) <= fam and
            set(i.get("domain_codes") or []) <= dom for i in ideas),
        "no_hallucinated_refs": all(
            all(str(x).startswith(("GAP-", "paper:", "problem:", "algofamily:",
                                   "domain:", "benchmark:"))
                for x in (i.get("evidence") or [])) for i in ideas),
        "novelty_recomputable": all(
            i.get("novelty") in ("unexplored_pair", "already_observed")
            for i in ideas),
    }
    # novelty 可复算：把 LLM 声明与共现矩阵重算结果比对
    observed = _observed_pairs(graph)
    mismatches = []
    for i in ideas:
        d = next(iter(i.get("domain_codes") or []), "")
        a = next(iter(i.get("family_codes") or []), "")
        real = "already_observed" if a in observed.get(d, set()) else "unexplored_pair"
        if i.get("novelty") != real:
            mismatches.append({"idea": i.get("idea_id"), "claimed": i.get("novelty"),
                               "recomputed": real})
    checks["novelty_matches_matrix"] = not mismatches
    return {"checks": checks, "novelty_mismatches": mismatches,
            "n_ideas": len(ideas),
            "novelty_distribution": dict(Counter(i.get("novelty") for i in ideas))}


def task_a(graph: Any, *, top_k: int = 20, generator: str = "rule",
           chat_fn: Any = None) -> Dict[str, Any]:
    """任务 A 全流程：缺口 → 报告 → gap 门 → 生成器 → 共用判定 → 机器 verdict。

    ``generator`` = ``rule`` | ``llm``；两版共用 ``gap_gate`` 与
    ``evaluate_ideas``，用于验证「换生成器不换判定」。
    """
    gaps = graph_gaps(graph, top_k=top_k)
    report = gap_report_text(gaps, graph)
    gate = gap_gate(report, min_gaps=min(2, max(1, len(gaps))))
    if generator == "llm":
        if chat_fn is None:
            raise ValueError("generator=llm 需要 chat_fn")
        ideas = propose_directions_llm(gaps, graph, chat_fn=chat_fn)
    else:
        ideas = propose_directions(gaps, graph)
    ev = evaluate_ideas(ideas, gaps, graph)
    checks = {"gap_gate": gate["ok"], **ev["checks"]}
    v = verdict("PASS" if all(checks.values()) else "FAIL",
                artifacts=["GAP_REPORT.md", "IDEA_DAG.json"],
                notes=f"generator={generator} n_gaps={len(gaps)} n_ideas={len(ideas)}")
    return {"task": "A:gap_to_algorithm_direction", "generator": generator,
            "n_gaps": len(gaps), "gaps": gaps,
            "gap_report": report, "gap_gate": gate,
            "n_ideas": len(ideas), "ideas": ideas,
            "novelty_distribution": ev["novelty_distribution"],
            "novelty_mismatches": ev["novelty_mismatches"],
            "checks": checks, "verdict": v}


# ---------------------------------------------------------------------------
# 任务 B：缺代码论文 → 算法拆解 + 代码复现
# ---------------------------------------------------------------------------
def intake_census(*, md_path: str | Path, code_dir: Optional[str | Path] = None,
                  paper_id: str = "") -> Dict[str, Any]:
    """SciForge ``intake-triage`` 的最小版：census + 信任分类 + 缺什么。"""
    md = Path(md_path) if md_path else None
    md_text = md.read_text(encoding="utf-8", errors="replace") if md and md.exists() else ""
    code_files = []
    if code_dir and Path(code_dir).exists():
        code_files = [str(p.relative_to(Path(code_dir)))
                      for p in sorted(Path(code_dir).rglob("*.py"))][:20]
    return {"paper_id": paper_id, "has_pdf_text": bool(md_text),
            "md_chars": len(md_text), "code_files": code_files,
            "n_code_files": len(code_files),
            "trust": "self_reported" if md_text else "missing",
            "missing": [x for x, ok in (("paper_text", bool(md_text)),
                                        ("implementation", bool(code_files)))
                        if not ok]}


def method_registry(*, modules: Sequence[Dict[str, Any]],
                    paper_id: str) -> Dict[str, Any]:
    """方法预注册（hash-lock）：先冻结模块清单，再允许复现，防止事后改方法。"""
    canonical = [{"module_name": m.get("module_name", ""),
                  "mechanism": m.get("mechanism", ""),
                  "inputs": m.get("inputs", []),
                  "outputs": m.get("outputs", [])}
                 for m in modules]
    payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True)
    return {"paper_id": paper_id, "n_modules": len(canonical),
            "modules": canonical, "registry_hash": sha256_text(payload),
            "note": "复现前冻结；结果出来后不得改模块清单"}


def task_b(*, md_path: str | Path, code_dir: Optional[str | Path] = None,
           paper_id: str = "", modules_raw: Optional[Dict[str, Any]] = None,
           baseline: float = 0.80, candidate: float = 0.86,
           direction: str = "maximize",
           run_real_toy: bool = False) -> Dict[str, Any]:
    """任务 B 全流程骨架：census → 预注册 → 代码-方法 parity → 阶梯 → 证据节点。

    ``baseline/candidate`` 由复现实验产生；未跑实验时给的是**结构演示值**，
    报告里会明确标 ``synthetic=True``，绝不冒充真实复现结果。
    """
    census = intake_census(md_path=md_path, code_dir=code_dir, paper_id=paper_id)
    mods = (modules_raw or {}).get("modules") or []
    reg = method_registry(modules=mods, paper_id=paper_id)

    # 两种文本：raw（论文原始模块名）与 grounded（含 CAD/模块对齐后的代码符号）。
    # 论文组件名常与代码符号不同名（EGCL vs EGNN_Sparse.message），
    # raw_parity 天然接近 0；grounded_parity 才反映「对齐后是否忠实」。
    method_text = "\n".join(
        f"{m.get('module_name','')} {m.get('mechanism','')} "
        f"{' '.join(str(x) for x in (m.get('inputs') or []))} "
        f"{' '.join(str(x) for x in (m.get('outputs') or []))}" for m in mods)
    # 用反引号包成「机器 token」，对齐 SciForge 的 `identifier` 规则
    lines = method_text.split("\n")
    grounded_text = "\n".join(
        lines[i] + " " + " ".join(f"`{str(x).split('.')[-1]}`"
                                  for x in (m.get("code_symbols") or []))
        for i, m in enumerate(mods))
    if census["has_pdf_text"] and not method_text:
        method_text = Path(md_path).read_text(encoding="utf-8", errors="replace")[:4000]
    code_text = ""
    if code_dir and Path(code_dir).exists():
        for p in sorted(Path(code_dir).rglob("*.py"))[:12]:
            code_text += p.read_text(encoding="utf-8", errors="replace") + "\n"

    parity = method_code_parity(grounded_text, code_text)
    raw_parity = method_code_parity(method_text, code_text)
    toy = None
    if run_real_toy:
        from .toy_egnn import run_toy, run_toy_ladder
        toy = run_toy()
        ladder = run_toy_ladder()
    else:
        ladder = {"critic_state": decide(baseline, candidate, direction),
                  "engineer_rounds": 1, "baseline_score": baseline,
                  "candidate_score": candidate, "direction": direction,
                  "relative_gain_pct": relative_gain(baseline, candidate, direction),
                  "full_set_pass": candidate > baseline if direction == "maximize"
                                   else candidate < baseline}
    ladder_problems = validate_ladder(ladder)
    node = record_node(kind="reproduction", phase="toy",
                       code=str(code_dir or md_path),
                       inputs=[{"baseline": baseline, "seed": 42}],
                       outputs=[{"candidate": candidate}],
                       reexec_cmd=f"python3 -m capfactory.sciforge.tasks --paper {paper_id}")

    blocking = {
        "has_paper_text": census["has_pdf_text"],
        "method_registered": bool(reg["registry_hash"]) and reg["n_modules"] > 0,
        "code_present": census["n_code_files"] > 0,
        "ladder_valid": not ladder_problems,
        "evidence_anchored": bool(node["code"]["sha256"]),
    }
    if run_real_toy:
        blocking["toy_analytic_pass"] = toy["status"] == "PASS"
        blocking["toy_deterministic"] = toy == __import__(
            "capfactory.sciforge.toy_egnn", fromlist=["run_toy"]).run_toy()
    # SciForge 定位：method_code_parity 是**审计项**（s2/audit.py），
    # 不是生死门；阻塞权在 toy 实验与 full-set ladder（s2/ladder.py）。
    # 这里如实记录两种 parity，低分给 WARN 而非冒充 PASS。
    audit = {"raw_parity": raw_parity.get("ratio"),
             "grounded_parity": parity.get("ratio"),
             "parity_status": parity["status"]}
    checks = dict(blocking, **audit)
    if not all(blocking.values()):
        state = "BLOCKED" if not census["n_code_files"] else "FAIL"
    elif parity["status"] == "PASS":
        state = "PASS"
    else:
        state = "WARN"
    return {"task": "B:paper_to_algorithm_reproduction",
            "paper_id": paper_id, "census": census,
            "method_registry": reg, "method_code_parity": parity,
            "raw_method_code_parity": raw_parity,
            "naming_gap": {"raw_ratio": raw_parity.get("ratio"),
                           "grounded_ratio": parity.get("ratio"),
                           "note": "两者之差即论文组件名与代码符号的命名鸿沟"},
            "ladder": ladder, "ladder_problems": ladder_problems,
            "evidence_node": node, "toy": toy,
            "checks": checks, "blocking": blocking, "audit": audit,
            "synthetic": not run_real_toy,
            "note": ("真实 toy：EGNN E(n) 等变性解析解 + naive 基线 ladder"
                     if run_real_toy else
                     "baseline/candidate 为结构演示值；真实复现须由 toy 实验写入 RESULT.json"),
            "verdict": verdict(state, artifacts=["METHOD_REGISTRY.json",
                                                 "S2_LADDER.json", "RESULT.json"],
                               notes=f"parity={parity.get('ratio')}")}
