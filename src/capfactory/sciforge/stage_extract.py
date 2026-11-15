# DEPRECATED (2026-11-14): 旧抽取链路，仅保留给历史测试与旧 /extraction 页面。
# 新增抽取一律走 capfactory.semantic.extraction.runner.run_extraction；
# pipeline 与 sciforge.core 已统一到新链路。本文件计划后续迁入 backup/。
"""三阶段根对象抽取（面向本地 Qwen3.8-27B，65K 上下文）。

与 polo 128K 一次性整篇抽取的差别：
* 每阶段**只给该根对象需要的原文切片**（Abstract/Intro、Method+AST、Experiments/表格）；
* 每阶段独立小输出契约，便于校验与失败重试；
* Stage2 带 AST 符号清单，代码对应关系只能从给定符号里选（防幻觉）；
* 判定权在规则：schema 校验 + 引用/符号合法性 + 重试，模型只产候选。

阶段与 ontology.chains.STAGES 一一对应。
"""
from __future__ import annotations
import json, re, time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..ingest.pdf import split_sections
from ..utils import parse_llm_json

MD_DIR = Path("/home/zengshuxin/xKG-main/data/docx")


def semantic_contract() -> str:
    """DEPRECATED：旧链路曾把这个块追加到 prompt 末尾，但示例 JSON 与它矛盾。

    新方案见 ``capfactory/semantic/extraction/contracts.py``；这里只做转发，
    保证历史调用不报错，且不再由 run_stage 追加。
    """
    try:
        from ..semantic.extraction.contracts import contract_text
        return "语义层契约（已由 semantic/extraction 统一）\n" + contract_text()
    except Exception:  # noqa: BLE001
        return ""


PROMPTS: Dict[str, str] = {
    "paper": """你是论文知识抽取器。只基于下面给出的【摘要与引言】抽 Stage1（根对象=Paper）。
输出严格 JSON（不要代码块/解释）：
{"paper_type":"method|dataset_benchmark|theory|survey|system_tool|application",
 "research_questions":[{"question":"可回答的问句","problem_category":"P01..P11 或空"}],
 "hypotheses":[{"statement":"论文声明的假设或观点","kind":"assumption|claim|stance"}],
 "sections":["章节标题"]}
规则：
1. question 必须是问句或明确的目标陈述，不是主题词；没有对应 P 类就留空，禁止编造。
2. hypotheses 只写作者明确声称的观点（we argue / we hypothesize / one way to ...）。
3. 不得复述原文整段；没有就给空数组。
【规则层候选信号（只能从这里选，不要发明）】
{rule_hints}
【摘要与引言】
{paper_text}
""",
    "algorithm": """你是算法-代码抽取器。只基于【方法节】与【代码符号清单】抽 Stage2（根对象=Algorithm）。
输出严格 JSON：
{"algorithm_name":"",
 "steps":[{"name":"步骤名","mechanism":"机制动词短语","formula_ref":"公式编号或空",
           "tools":["工具/库/力场"],"code_symbols":["符号名"]}],
 "invariant":"可解析检验的不变量名或空"}
规则：
1. code_symbols 只能从【代码符号清单】里选，禁止发明不存在的函数/类。
2. tools 只写方法节里真实出现的（RDKit / force field / GMM / transformer ...）。
3. steps 按论文方法节的逻辑顺序，3-6 个；mechanism 用动宾短语，不要照抄标题。
4. invariant 只有论文明确给出可检验性质时才填。
【规则层候选信号（formula_ref / tools 只能从这里选）】
{rule_hints}
【方法节】
{paper_text}
【代码符号清单】
{code_symbols}
""",
    "benchmark_profile": """你是基准抽取器。只基于【实验节文本】抽 Stage3 的**结构部分**。
输出严格 JSON（纯 JSON，不要 ``` 代码块，不要解释）：
{"benchmarks":[{"name":"基准/数据集名","input_form":"","output_form":"",
  "input_object":"","output_object":"","sample_budget":"","threshold":"",
  "metrics":[""],"baselines":[""],"evaluation_tool":""}]}
规则：
1. benchmarks **最多 3 个**，只写论文里明确命名的数据集/评测场景。
2. input/output_form 从 SMILES / 3D 坐标 / 向量 / 图 / 序列 / 分布 / 标量 里选。
3. metrics / baselines 最多各 4 个，只写实验节出现的名字。
4. 每个字段值不超过 30 字；不确定就留空字符串，**不要解释、不要补理由**。
5. 不要输出 observations（下一阶段单独抽）。
【规则层候选信号（metric / 数值必须出现在这里）】
{rule_hints}
【实验节文本】
{paper_text}
""",
    "benchmark_values": """你是论文数值抽取器。只基于【实验节与表格文本】抽 Stage3 的**观测值部分**。
输出严格 JSON（纯 JSON，不要 ``` 代码块，不要解释）：
{"observations":[{"metric":"指标名","value":0,"unit":"","benchmark":"","subject":"方法名"}]}
规则：
1. **最多 8 条**，只写论文明确给出的主要数值；宁缺毋滥。
2. value 必须是数字（不带 % 时 unit 写 "percent"）；没有数值就输出 {"observations":[]}。
3. 禁止把表号、年份、epoch、dropout、学习率、引用编号当成观测值。
4. metric 用简短标准名（validity / novelty / MAE / R2 / hit_rate ...）。
5. 不要复述原文，不要输出其它字段。
【规则层候选信号（metric / 数值必须出现在这里）】
{rule_hints}
【实验节与表格文本】
{paper_text}
""",
}

# 每阶段最小必需字段：用于判定「抽出来了没有」
REQUIRED: Dict[str, Tuple[str, ...]] = {
    "paper": ("paper_type", "research_questions"),
    "algorithm": ("algorithm_name", "steps"),
    "benchmark_profile": ("benchmarks",),
    "benchmark_values": ("observations",),
}
VALID_TYPES = {"method", "dataset_benchmark", "theory", "survey",
               "system_tool", "application"}
# 逻辑三阶段 = 4 次小调用；Stage3 内部拆结构与数值，避免单次输出被截断
CALL_ORDER = ("paper", "algorithm", "benchmark_profile", "benchmark_values")
STAGE_BUDGET = {"paper": 900, "algorithm": 1800,
                "benchmark_profile": 1800, "benchmark_values": 1200}


def section_slices(sections: Dict[str, str], *, chars: int = 48000
                   ) -> Dict[str, str]:
    """按阶段切原文：不让 65K 上下文被整篇论文吃掉。"""
    def pick(keys: Tuple[str, ...]) -> str:
        parts = [f"## {k}\n{v}" for k, v in sections.items()
                 if any(x in k.lower() for x in keys)]
        return "\n\n".join(parts)[:chars]
    return {
        "paper": pick(("abstract", "introduction", "1. introduction")),
        "algorithm": pick(("method", "approach", "model", "architecture",
                           "preliminar", "training", "sampling", "rollout",
                           "representation")),
        "benchmark": pick(("experiment", "result", "benchmark", "setup",
                           "table", "calibration", "evaluation")),
    }


def rule_signals(md: str, sections: Dict[str, str]) -> Dict[str, Any]:
    """确定性规则层先跑一遍，产出候选清单给 LLM 选择（而非自由生成）。"""
    from .tentacle import (_formula_signals, _tool_signals,
                           metric_mentions, flattened_tables)
    from .citations import parse_references
    method = section_slices(sections, chars=20000)["algorithm"]
    exp = section_slices(sections, chars=20000)["benchmark"]
    formulas = [f"({f['equation_no']})" for f in _formula_signals(method)]
    tools = _tool_signals(method)
    mets = metric_mentions(md)
    refs = [f"[{r['ref_no']}]" for r in parse_references(md)[:60]]
    return {"formula_refs": formulas, "tools": tools,
            "metrics": sorted({m["metric"] for m in mets}),
            "values": sorted({str(m["value"]) for m in mets}),
            "table_refs": [f"Table {t['table']}" for t in
                           flattened_tables(md)[:8]],
            "citation_refs": refs}


def _hints_text(stage: str, sig: Dict[str, Any]) -> str:
    if stage == "paper":
        return ("引用标记候选：" + ", ".join(sig["citation_refs"][:20])
                + "\n表格：" + ", ".join(sig["table_refs"]))
    if stage == "algorithm":
        return ("公式：" + ", ".join(sig["formula_refs"] or ["(无)"])
                + "\n工具：" + ", ".join(sig["tools"] or ["(无)"])
                + "\n引用标记：" + ", ".join(sig["citation_refs"][:12]))
    return ("指标：" + ", ".join(sig["metrics"][:16])
            + "\n数值：" + ", ".join(sig["values"][:16])
            + "\n表格：" + ", ".join(sig["table_refs"]))


def hallucination_warnings(stage: str, data: Dict[str, Any],
                           sig: Dict[str, Any]) -> List[str]:
    """LLM 输出与规则层候选不符时报警（不硬失败，留给人复核）。"""
    out: List[str] = []
    if stage == "algorithm":
        legal = set(sig.get("formula_refs") or [])
        for st in data.get("steps") or []:
            fr = str(st.get("formula_ref") or "").strip()
            if fr and legal and fr not in legal:
                out.append(f"formula_ref_not_in_text:{fr}")
            for t in st.get("tools") or []:
                if t not in (sig.get("tools") or []):
                    out.append(f"tool_not_in_text:{t}")
    if stage in ("benchmark_values", "benchmark"):
        legal_m = set(sig.get("metrics") or [])
        for o in data.get("observations") or []:
            if str(o.get("metric") or "") not in legal_m and legal_m:
                out.append(f"metric_not_in_text:{o.get('metric')}")
    return out


def validate_stage(stage: str, data: Dict[str, Any], *,
                   code_symbols: Optional[set] = None) -> List[str]:
    """确定性校验：模型只产候选，合格与否由规则判。"""
    issues: List[str] = []
    if not isinstance(data, dict):
        return ["输出不是 JSON 对象"]
    for k in REQUIRED.get(stage, ()):
        if k not in data:
            issues.append(f"missing:{k}")
    if stage == "paper":
        if data.get("paper_type") not in VALID_TYPES:
            issues.append(f"bad_paper_type:{data.get('paper_type')}")
        for i, q in enumerate(data.get("research_questions") or []):
            if not isinstance(q, dict) or not str(q.get("question") or "").strip():
                issues.append(f"bad_question:{i}")
    elif stage == "algorithm":
        steps = data.get("steps") or []
        if not isinstance(steps, list) or not steps:
            issues.append("empty_steps")
        else:
            for i, s in enumerate(steps):
                if not isinstance(s, dict) or not str(s.get("name") or "").strip():
                    issues.append(f"bad_step:{i}")
                if code_symbols is not None:
                    for sym in s.get("code_symbols") or []:
                        if sym not in code_symbols:
                            issues.append(f"hallucinated_symbol:{sym}")
    elif stage in ("benchmark", "benchmark_profile"):
        bs = data.get("benchmarks") or []
        if not isinstance(bs, list) or not bs:
            issues.append("empty_benchmarks")
        else:
            for i, b in enumerate(bs):
                if not isinstance(b, dict) or not str(b.get("name") or "").strip():
                    issues.append(f"bad_benchmark:{i}")
    if stage in ("benchmark", "benchmark_values"):
        for i, o in enumerate(data.get("observations") or []):
            if not isinstance(o, dict) or not str(o.get("metric") or "").strip():
                issues.append(f"bad_observation:{i}")
            elif o.get("value") in (None, ""):
                issues.append(f"missing_value:{i}")
    return issues


def run_stage(stage: str, *, paper_text: str, code_symbols: str = "",
              chat_fn: Optional[Callable[..., str]] = None,
              max_tokens: int = 0, retries: int = 1,
              timeout: int = 300, rule_hints: str = "",
              signal: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """跑一个阶段：失败时把校验问题回注 prompt 重试。"""
    if chat_fn is None:
        from ..llm.backends import chat as _chat
        chat_fn = lambda p, **kw: _chat(p, backend="vllm", **kw)  # noqa: E731
    budget = max_tokens or STAGE_BUDGET.get(stage, 2000)
    max_tokens = budget
    base = PROMPTS[stage].replace("{paper_text}", paper_text or "(无)")
    # 不再追加语义层契约：旧示例 JSON 面向 legacy TBox，追加会自相矛盾。
    # 语义层抽取请走 capfactory.semantic.extraction.runner.run_extraction。
    base = base.replace("{code_symbols}", code_symbols or "(无)")
    base = base.replace("{rule_hints}", rule_hints or "(无)")
    syms = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", code_symbols or ""))
    attempts: List[Dict[str, Any]] = []
    prompt = base
    for i in range(retries + 1):
        t0 = time.time()
        try:
            out = chat_fn(prompt, max_tokens=max_tokens, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            attempts.append({"i": i, "error": f"{type(exc).__name__}:{exc}"[:180],
                             "latency_s": round(time.time() - t0, 2)})
            continue
        stripped = (out or "").rstrip()
        truncated = bool(stripped) and not stripped.endswith(("}", "]", "```"))
        data = parse_llm_json(out) or {}
        issues = validate_stage(stage, data,
                                code_symbols=syms if stage == "algorithm" else None)
        attempts.append({"i": i, "prompt_chars": len(prompt),
                         "out_chars": len(out or ""),
                         "latency_s": round(time.time() - t0, 2),
                         "issues": issues, "truncated": truncated,
                         "max_tokens": max_tokens,
                         "head": (out or "")[:160]})
        if not issues:
            return {"stage": stage, "ok": True, "data": data,
                    "attempts": attempts, "n_attempts": i + 1,
                    "hallucination_warnings": hallucination_warnings(
                        stage, data, signal or {})}
        if truncated:
            # 截断时**不重试原 prompt**：砍掉可选字段、提高预算，避免再烧 130 s
            prompt = (base.split("输出严格 JSON")[0]
                      + "输出严格 JSON，只含必需字段 "
                      + str(list(REQUIRED.get(stage, ())))
                      + "，每项字段值尽量短，最多 3 条。不要代码块。\n"
                      + (base.split("【实验节文本】")[-1] if "【实验节文本】" in base
                         else base.split("【方法节】")[-1] if "【方法节】" in base
                         else base.split("【摘要与引言】")[-1]))
            max_tokens = int(budget * 1.5)
        else:
            prompt = (base + "\n\n【上一次输出未通过校验，请修正后重输出完整 JSON】\n"
                      + "; ".join(issues[:8]))
    return {"stage": stage, "ok": False, "data": data if "data" in locals() else {},
            "attempts": attempts, "n_attempts": len(attempts)}


def _ast_symbol_text(repo: str, limit: int = 3000) -> Tuple[str, set]:
    from ..ontology.modules import code_structure
    root = Path("/home/zengshuxin/xKG-main/data/repos/src") / repo
    if not repo or not root.exists():
        return "", set()
    st = code_structure(root, max_symbols=40)
    syms = [str(s.get("name") or "") for s in (st.get("symbols") or [])
            if s.get("name")]
    return "\n".join(f"- {s}" for s in syms)[:limit], set(syms)


def run_three_stages(*, arxiv_id: str, repo: str = "",
                     chat_fn: Optional[Callable[..., str]] = None,
                     max_tokens: int = 0, retries: int = 1,
                     out_dir: Optional[str | Path] = None,
                     chars_per_stage: int = 48000) -> Dict[str, Any]:
    """按根对象依次跑 Stage1 Paper → Stage2 Algorithm-Code → Stage3 Benchmark。"""
    f = MD_DIR / f"{arxiv_id}.md"
    if not f.exists():
        return {"arxiv_id": arxiv_id, "error": "md_not_found"}
    md = f.read_text(encoding="utf-8", errors="replace")
    secs = split_sections(md)
    slices = section_slices(secs, chars=chars_per_stage)
    sym_text, syms = _ast_symbol_text(repo)
    sig = rule_signals(md, secs)

    report: Dict[str, Any] = {
        "arxiv_id": arxiv_id, "repo": repo, "model": "Qwen3.8-27B (local vLLM)",
        "md_chars": len(md), "n_sections": len(secs),
        "slice_chars": {k: len(v) for k, v in slices.items()},
        "ast_symbols": len(syms), "stages": {},
        "rule_signals": {k: len(v) if isinstance(v, list) else v
                         for k, v in sig.items()},
    }
    data_by_stage: Dict[str, Dict[str, Any]] = {}
    for stage in CALL_ORDER:
        key = "paper" if stage == "paper" else \
              "algorithm" if stage == "algorithm" else "benchmark"
        r = run_stage(stage,
                      paper_text=slices[key] or md[:chars_per_stage],
                      code_symbols=sym_text if stage == "algorithm" else "",
                      chat_fn=chat_fn,
                      max_tokens=max_tokens or STAGE_BUDGET[stage],
                      retries=retries,
                      rule_hints=_hints_text(stage, sig), signal=sig)
        report["stages"][stage] = r
        data_by_stage[stage] = r.get("data") or {}
    # 合并 Stage3 两个子调用为一个逻辑阶段
    merged = {**(data_by_stage.get("benchmark_profile") or {}),
              **(data_by_stage.get("benchmark_values") or {})}
    data_by_stage["benchmark"] = merged
    report["logical_stages"] = {
        "paper": data_by_stage["paper"],
        "algorithm": data_by_stage["algorithm"],
        "benchmark": merged,
    }
    report["ok"] = all(r["ok"] for r in report["stages"].values())
    report["hallucination_warnings"] = [w for r in report["stages"].values()
                                        for w in r.get("hallucination_warnings", [])]
    report["n_attempts"] = sum(r["n_attempts"] for r in report["stages"].values())
    report["total_latency_s"] = round(sum(
        a.get("latency_s", 0) for r in report["stages"].values()
        for a in r["attempts"]), 2)
    # 阶段间一致性：Stage2 的算法名不应与 Stage1 的论文类型冲突；
    # Stage3 的 observations 数量是召回指标，不做硬门。
    report["cross_stage"] = {
        "paper_type": data_by_stage["paper"].get("paper_type"),
        "n_questions": len(data_by_stage["paper"].get("research_questions") or []),
        "n_hypotheses": len(data_by_stage["paper"].get("hypotheses") or []),
        "n_steps": len(data_by_stage["algorithm"].get("steps") or []),
        "n_benchmarks": len(data_by_stage["benchmark"].get("benchmarks") or []),
        "n_observations": len(data_by_stage["benchmark"].get("observations") or []),
        "symbols_used": sorted({s for st in
                                (data_by_stage["algorithm"].get("steps") or [])
                                for s in (st.get("code_symbols") or [])}),
    }
    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / f"qwen_stages_{arxiv_id}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
        for stage, d in report["logical_stages"].items():
            (out / f"qwen_{stage}_{arxiv_id}.json").write_text(
                json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
