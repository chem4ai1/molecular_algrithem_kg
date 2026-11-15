# DEPRECATED (2026-11-14): 旧抽取链路，仅保留给历史测试与旧 /extraction 页面。
# 新增抽取一律走 capfactory.semantic.extraction.runner.run_extraction；
# pipeline 与 sciforge.core 已统一到新链路。本文件计划后续迁入 backup/。
"""Stage2：按块类型肢解（这才是最关键的一步）。

用户给的四种科技树样式、算法-代码对应、基准数据特征都落在这里。
每个模块：LLM 只产候选，判定权在规则（逐字证据 / AST 符号 / 原文数值）。
"""
from __future__ import annotations
import json, re, time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..utils import parse_llm_json

TREE_RELS = {"HAS_LIMITATION", "ADDRESSED_BY", "IMPROVED_BY", "REPLACES",
             "BELONGS_TO", "COMPARES_WITH", "ON_METRIC", "DELTA"}
TREE_STYLES = {"bottleneck", "improvement", "taxonomy", "comparison"}

PROMPTS: Dict[str, str] = {
    "related_work": """你是科技树抽取器。只基于【相关论文/Related Work 块】抽「局部、短、带证据」的演化链。
输出严格 JSON（纯 JSON，不要代码块）：
{"chains":[{"style":"bottleneck|improvement|taxonomy|comparison",
 "methods":["方法名"],
 "edges":[{"src":"","rel":"","dst":"","confidence":0.9,"evidence":"逐字引文"}]}]}
四种样式：
 bottleneck  HAS_LIMITATION 的 dst 写**局限短语**（如"忽略分子图信息"），
              ADDRESSED_BY 的 dst 写解决它的方法名；禁止 src==dst
 improvement IMPROVED_BY（同维度优化）/ REPLACES（换机制）
 taxonomy    BELONGS_TO（方法家族归类）
 comparison  COMPARES_WITH / ON_METRIC / DELTA（含数值提升）
规则：
1. 每条链 2-4 个方法节点，不要构造覆盖全流程的 DAG。
2. evidence **必须是从原文逐字复制的短句**（≤120 字），不得改写或编造。
3. rel 只能用上面列出的 8 种；confidence 0-1；chains 最多 4 条。
4. 找不到就输出 {"chains":[]}，不要硬凑。
【相关论文块】
{block_text}
""",
    "method": """你是算法-代码对齐抽取器。只基于【方法块】与【代码符号清单】。
输出严格 JSON（纯 JSON，不要代码块）：
{"steps":[{"name":"步骤名","mechanism":"机制动宾短语",
 "formula_ref":"公式编号或空","formula":"公式片段或空",
 "tools":["工具/库"],"code_symbols":["符号名"]}],
 "invariant":"可解析检验的不变量或空"}
规则：
1. code_symbols 只能从【代码符号清单】选，禁止发明函数/类。
2. formula_ref 只能是 (1)/(2)... 这类编号；formula 必须是原文公式片段。
3. tools 只写方法块里真实出现的；steps 3-6 个，按逻辑顺序。
4. mechanism 用动宾短语，不要照抄标题。
【方法块】
{block_text}
【代码符号清单】
{code_symbols}
""",
    "benchmark_profile": """你是基准数据契约抽取器。只基于【基准块】。
输出严格 JSON（纯 JSON，不要代码块）：
{"benchmarks":[{"name":"","input_form":"","output_form":"",
 "input_object":"","output_object":"","sample_budget":"","threshold":"",
 "metrics":[""],"baselines":[""],"evaluation_tool":""}]}
规则：benchmarks ≤3；metrics/baselines 各 ≤4；字段值 ≤30 字；
input/output_form 从 SMILES/3D坐标/向量/图/序列/分布/标量 选；不要输出观测值。
【基准块】
{block_text}
""",
    "benchmark_values": """你是论文数值抽取器。只基于【基准块】抽观测值。
输出严格 JSON（纯 JSON，不要代码块）：
{"observations":[{"metric":"","value":0,"unit":"","benchmark":"","subject":"","evidence":"逐字引文"}]}
规则：
1. ≤8 条，只写明确数值；evidence 必须是原文逐字短句。
2. 禁止把表号、年份、epoch、dropout、学习率、引用编号当观测值。
3. value 必须是数字；没有就输出 {"observations":[]}。
【基准块】
{block_text}
""",
}

BUDGET: Dict[str, int] = {"related_work": 2200, "method": 1800,
                          "benchmark_profile": 1600, "benchmark_values": 1400}


def _norm_evidence(s: str) -> str:
    """PDF→MD 会插入换行/断词连字符，逐字证据需归一后再比对。"""
    s = re.sub(r"-\s*\n\s*", "", str(s or ""))     # net-\nwork -> network
    s = re.sub(r"-\s+(?=[a-z])", "", s)              # net- work -> network
    s = re.sub(r"\s+", " ", s)
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"') \
         .replace("”", '"').replace("−", "-").replace("–", "-")
    return s.strip().lower()


def _verbatim(ev: str, text: str) -> bool:
    a, b = _norm_evidence(ev), _norm_evidence(text)
    if not a or not b:
        return False
    return a in b or a[:60] in b      # 允许模型把长引文截到 60 字


def _issues(kind: str, data: Dict[str, Any], *, text: str = "",
            symbols: Optional[set] = None) -> List[str]:
    out: List[str] = []
    if not isinstance(data, dict):
        return ["not_object"]
    if kind == "related_work":
        chains = data.get("chains")
        if not isinstance(chains, list):
            return ["missing:chains"]
        for i, c in enumerate(chains):
            if not isinstance(c, dict) or c.get("style") not in TREE_STYLES:
                out.append(f"bad_style:{i}")
            ms = c.get("methods") or []
            if not (2 <= len(ms) <= 4):
                out.append(f"bad_method_count:{i}:{len(ms)}")
            for j, e in enumerate(c.get("edges") or []):
                if not isinstance(e, dict) or e.get("rel") not in TREE_RELS:
                    out.append(f"bad_rel:{i}:{j}")
                elif e.get("rel") in ("HAS_LIMITATION", "ADDRESSED_BY",
                                      "IMPROVED_BY", "REPLACES",
                                      "BELONGS_TO", "COMPARES_WITH") and \
                        str(e.get("src") or "") == str(e.get("dst") or ""):
                    out.append(f"self_loop:{i}:{j}")
                ev = str(e.get("evidence") or "")
                if not _verbatim(ev, text):
                    out.append(f"evidence_not_verbatim:{i}:{j}")
    elif kind == "method":
        steps = data.get("steps") or []
        if not isinstance(steps, list) or not steps:
            return ["empty_steps"]
        for i, s in enumerate(steps):
            if not isinstance(s, dict) or not s.get("name"):
                out.append(f"bad_step:{i}")
            if symbols is not None:
                for sym in s.get("code_symbols") or []:
                    if sym not in symbols:
                        out.append(f"hallucinated_symbol:{sym}")
    elif kind == "benchmark_profile":
        bs = data.get("benchmarks") or []
        if not isinstance(bs, list) or not bs:
            return ["empty_benchmarks"]
        for i, b in enumerate(bs):
            if not isinstance(b, dict) or not b.get("name"):
                out.append(f"bad_benchmark:{i}")
    elif kind == "benchmark_values":
        for i, o in enumerate(data.get("observations") or []):
            if not isinstance(o, dict) or not o.get("metric") or \
                    o.get("value") in (None, ""):
                out.append(f"bad_observation:{i}")
            ev = str(o.get("evidence") or "")
            if ev and not _verbatim(ev, text):
                out.append(f"evidence_not_verbatim:{i}")
    return out


def run_module(kind: str, *, block_text: str, code_symbols: str = "",
               chat_fn: Optional[Callable[..., str]] = None,
               max_tokens: int = 0, retries: int = 1,
               timeout: int = 240, router: Any = None) -> Dict[str, Any]:
    """跑一个深挖模块；有 router 时走「本地→加预算→polo」三级升级。"""
    if router is not None:
        sym_set = (set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}",
                                  code_symbols or "")) if kind == "method"
                   else None)

        def _validate(out: str) -> List[str]:
            data = parse_llm_json(out) or {}
            return _issues(kind, data, text=block_text, symbols=sym_set)
        from .llm_router import STAGE_CAPS
        rr = router.run(
            (PROMPTS[kind].replace("{block_text}", block_text or "(无)")
             .replace("{code_symbols}", code_symbols or "(无)")),
            stage=kind, validate=_validate,
            requested=max_tokens or STAGE_CAPS.get(kind, 5000))
        data = parse_llm_json(rr["out"]) or {}
        return {"kind": kind, "ok": rr["ok"], "data": data,
                "attempts": [a.to_dict() for a in rr["attempts"]],
                "n_attempts": rr["n_attempts"], "backend": rr["backend"],
                "budget": {k: v for k, v in rr["final_budget"].items()
                           if k != "boost"}}
    syms = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", code_symbols or ""))
    if chat_fn is None:
        from ..llm.backends import chat as _chat
        chat_fn = lambda p, **kw: _chat(p, backend="vllm", **kw)  # noqa: E731
    syms = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", code_symbols or ""))
    base = (PROMPTS[kind].replace("{block_text}", block_text or "(无)")
            .replace("{code_symbols}", code_symbols or "(无)"))
    budget = max_tokens or BUDGET[kind]
    attempts: List[Dict[str, Any]] = []
    prompt = base
    for i in range(retries + 1):
        t0 = time.time()
        try:
            out = chat_fn(prompt, max_tokens=budget, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            attempts.append({"i": i, "error": f"{type(exc).__name__}:{exc}"[:150],
                             "latency_s": round(time.time() - t0, 2)})
            continue
        truncated = bool((out or "").rstrip()) and not \
            (out or "").rstrip().endswith(("}", "]", "```"))
        data = parse_llm_json(out) or {}
        issues = _issues(kind, data, text=block_text,
                         symbols=syms if kind == "method" else None)
        attempts.append({"i": i, "prompt_chars": len(prompt),
                         "out_chars": len(out or ""),
                         "latency_s": round(time.time() - t0, 2),
                         "truncated": truncated, "issues": issues[:8],
                         "n_issues": len(issues),
                         "head": (out or "")[:150]})
        if not issues:
            return {"kind": kind, "ok": True, "data": data,
                    "attempts": attempts, "n_attempts": i + 1}
        if truncated:
            prompt = base + "\n【上次被截断】只输出 2 条最短的链/项，不要代码块。"
            budget = int(budget * 1.4)
        else:
            hint = ("；证据必须**逐字复制原文连续片段**（≤120 字），"
                    "不要改写、不要合并跨行句子、不要自己造句"
                    if any("evidence" in x for x in issues) else "")
            prompt = (base + "\n【上次未通过校验，请修正后重输出完整 JSON】"
                      + "; ".join(issues[:5]) + hint)
    return {"kind": kind, "ok": False, "data": data if "data" in locals() else {},
            "attempts": attempts, "n_attempts": len(attempts)}


def blocks_text(blocks: Sequence[Dict[str, Any]], kind: str, *,
                max_chars: int = 40000) -> str:
    parts = [f"## {b['heading']}\n{b['text']}" for b in blocks
             if b["kind"] == kind]
    return "\n\n".join(parts)[:max_chars]


def deep_dive(blocks: Sequence[Dict[str, Any]], *,
              code_symbols: str = "",
              chat_fn: Optional[Callable[..., str]] = None,
              retries: int = 1, router: Any = None) -> Dict[str, Any]:
    """按三类块分别深挖；benchmark 内部再拆结构/数值，避免输出截断。"""
    report: Dict[str, Any] = {"modules": {}, "logical": {}}
    specs = [
        ("related_work", "related_work"),
        ("method", "method"),
        ("benchmark_profile", "benchmark"),
        ("benchmark_values", "benchmark"),
    ]
    for kind, block_kind in specs:
        text = blocks_text(blocks, block_kind)
        r = run_module(kind, block_text=text,
                       code_symbols=code_symbols if kind == "method" else "",
                       chat_fn=chat_fn, retries=retries, router=router)
        report["modules"][kind] = r
    b = {**(report["modules"]["benchmark_profile"].get("data") or {}),
         **(report["modules"]["benchmark_values"].get("data") or {})}
    report["logical"] = {
        "related_work": report["modules"]["related_work"].get("data") or {},
        "method": report["modules"]["method"].get("data") or {},
        "benchmark": b,
    }
    report["ok"] = all(r["ok"] for r in report["modules"].values())
    report["n_attempts"] = sum(r["n_attempts"] for r in report["modules"].values())
    report["total_latency_s"] = round(sum(
        a.get("latency_s", 0) for r in report["modules"].values()
        for a in r["attempts"]), 2)
    report["backends"] = {k: v.get("backend", "legacy")
                          for k, v in report["modules"].items()}
    report["summary"] = {
        "tree_chains": len(report["logical"]["related_work"].get("chains") or []),
        "method_steps": len(report["logical"]["method"].get("steps") or []),
        "benchmarks": len(b.get("benchmarks") or []),
        "observations": len(b.get("observations") or []),
    }
    return report


def tree_to_graph(graph: Any, chains: Sequence[Dict[str, Any]], *,
                  paper_id: str = "") -> Dict[str, int]:
    """科技树链落成图节点/边：逐字证据挂在边上。"""
    n = {"nodes": 0, "edges": 0}
    for ci, c in enumerate(chains or []):
        for name in c.get("methods") or []:
            mid = f"sourcepaper:tree:{re.sub(r'[^a-z0-9]+', '_', name.lower())[:40]}"
            if mid not in graph.nodes:
                graph.node(mid, "SourcePaper", name[:60],
                           root_type="related_paper", root_id=name,
                           source_kind="related_paper",
                           tree_style=c.get("style", ""),
                           evidence="", provenance="tech_tree")
                n["nodes"] += 1
            if paper_id and paper_id in graph.nodes:
                graph.assert_rel(paper_id, mid, "SITUATED_IN")
                n["edges"] += 1
        for j, e in enumerate(c.get("edges") or []):
            rel = e.get("rel")
            # 蓝图 P0-2：8 种 TREE_RELS 全放行；REPLACED_BY 作为 REPLACES 别名
            if rel == "REPLACED_BY":
                rel = "REPLACES"
            if rel not in TREE_RELS:
                continue
            a = f"sourcepaper:tree:{re.sub(r'[^a-z0-9]+', '_', str(e.get('src','')).lower())[:40]}"
            b = f"sourcepaper:tree:{re.sub(r'[^a-z0-9]+', '_', str(e.get('dst','')).lower())[:40]}"
            if a in graph.nodes and b in graph.nodes:
                graph.assert_rel(a, b, rel)
                n["edges"] += 1
    return n
