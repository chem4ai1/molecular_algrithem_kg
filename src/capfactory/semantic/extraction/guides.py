"""抽取指导层：T-Box 指导 + A-Box 指导 + 实例检索 + paper_type 阶段计划。

T-Box 指导：本体里有哪些类/字段/封闭词表、禁止造什么。
A-Box 指导：图里已有哪些实例，让模型优先复用已有名称而不是造新名。
paper_type：Stage0 判定类型，决定各 E 阶段开关与重点（接上旧 prompt 的断点）。
"""
from __future__ import annotations
from typing import Any, Dict, List

from .contracts import contract_text, _task_types

PAPER_TYPES = ("method", "dataset_benchmark", "theory", "survey",
               "system_tool", "application")

STAGE_PLAN: Dict[str, Dict[str, Any]] = {
    "method": {"stages": ("E1_paper", "E2_algorithm", "E3_benchmark",
                          "E4_values", "E5_relations", "E6_lineage"),
               "focus": "重点抽算法模块与机理；基准只抽本文实际评测的"},
    "dataset_benchmark": {"stages": ("E1_paper", "E2_algorithm",
                                      "E3_benchmark", "E4_values",
                                      "E5_relations", "E6_lineage"),
                          "focus": "重点抽基准结构、指标与数值；算法模块可空"},
    "system_tool": {"stages": ("E1_paper", "E2_algorithm", "E5_relations"),
                    "focus": "重点抽系统模块与代码/工具关系"},
    "theory": {"stages": ("E1_paper", "E6_lineage"),
               "focus": "重点抽问题与改进链；不抽基准数值"},
    "survey": {"stages": ("E1_paper", "E6_lineage"),
               "focus": "重点抽方法谱系；不把综述里的方法当本文新算法"},
    "application": {"stages": ("E1_paper", "E2_algorithm", "E3_benchmark",
                               "E4_values", "E6_lineage"),
                    "focus": "重点抽应用场景与所用基准"},
}


def tbox_guide() -> str:
    return contract_text()


def instance_catalog(graph: Any) -> Dict[str, List[str]]:
    """A-Box 实例目录：从语义层图抽已有实体名。"""
    if not graph:
        return {}
    return {
        "algorithms": sorted({(n.attrs.get("name") or n.label)
                              for n in graph.by_type("Algorithm")})[:60],
        "benchmarks": sorted({(n.attrs.get("name") or n.label)
                              for n in graph.by_type("Benchmark")})[:60],
        "code_symbols": sorted({(n.attrs.get("name") or n.label)
                                for n in graph.by_type("CodeFunction")})[:80],
        "modules": sorted({(n.attrs.get("name") or n.label)
                           for n in graph.by_type("AlgorithmModule")})[:60],
        "families": sorted({str(n.attrs.get("flow_family"))
                            for n in graph.by_type("Algorithm")
                            if n.attrs.get("flow_family")})[:20],
        "task_types": list(_task_types()),
    }


def retrieve_instances(text: str, graph: Any, *, k: int = 12,
                       stage: str | None = None) -> Dict[str, List[str]]:
    """实例检索：① 名称字面命中（确定性）② 语义检索兜底。"""
    cat = instance_catalog(graph)
    low = (text or "").lower()
    hits: Dict[str, List[str]] = {}
    for kind in ("algorithms", "benchmarks", "code_symbols", "modules"):
        hits[kind] = [n for n in cat.get(kind, [])
                      if n and len(n) > 2 and n.lower() in low][:k]
    if len(hits.get("algorithms", [])) < 3 and stage in (None, "E2_algorithm"):
        # 优先用语义层 BGE 向量索引（结果自带 paper_ids 可溯源）
        try:
            from ..vector_sync import search as _vsearch
            res = _vsearch((text or "")[:600],
                           types=["Algorithm", "AlgorithmModule"], k=k)
            extra = [r.get("label") for r in res]
            hits["algorithms"] = list(dict.fromkeys(
                hits.get("algorithms", []) + [x for x in extra if x]))[:k]
        except Exception:  # noqa: BLE001
            try:
                from ...sciforge.algorithm_problem import search_algorithms
                res = search_algorithms((text or "")[:600], k=k)
                extra = [r.get("name") or r.get("id") for r in res
                         if isinstance(r, dict)]
                hits["algorithms"] = list(dict.fromkeys(
                    hits.get("algorithms", []) + [x for x in extra if x]))[:k]
            except Exception:  # noqa: BLE001
                pass
    return hits


STAGE_INSTANCE_KINDS: Dict[str, Tuple[str, ...]] = {
    "E1_paper": ("algorithms", "benchmarks"),
    "E2_algorithm": ("algorithms", "code_symbols", "modules"),
    "E3_benchmark": ("benchmarks",),
    "E4_values": (),
    "E5_relations": ("modules",),
    "E6_lineage": ("algorithms",),
}


def abox_guide(text: str, graph: Any,
               stage: str | None = None) -> str:
    """把检索到的实例注入 prompt：要求优先复用、不得造同义新名。"""
    kinds = STAGE_INSTANCE_KINDS.get(stage, ("algorithms", "benchmarks",
                                             "code_symbols", "modules")) \
        if stage else ("algorithms", "benchmarks", "code_symbols", "modules")
    if not kinds:
        return ""   # 该阶段不需要实例目录
    hits = retrieve_instances(text, graph, stage=stage)
    cat = instance_catalog(graph)
    lines = ["【A-Box 指导 · 已有实例（优先复用，不要造同义新名）】"]
    for kind in kinds:
        h = hits.get(kind) or []
        allc = cat.get(kind) or []
        if h:
            lines.append("- 本文已提到的 " + kind + "：" + ", ".join(h[:12]))
        if allc:
            lines.append("  （库中共有 " + str(len(allc)) + " 个 " + kind +
                         "，例：" + ", ".join(allc[:6]) + "）")
    # 词表由 prompts.catalogs 按阶段注入，这里不重复
    lines += ["规则：输出里的算法名/基准名/代码符号若在库里存在，必须原样使用；"
              "库里没有的才允许新建，并在 evidence 给出依据。"]
    return "\n".join(lines)


def classify_paper_type(text: str, *, graph: Any = None,
                        chat_fn: Any = None, title: str = "",
                        low_conf_threshold: float = 0.5,
                        use_llm: bool = True) -> Dict[str, Any]:
    """Stage0：规则优先 + 低置信时用「标题+摘要」做一次轻量分类。

    LLM 输出只允许一个类型词（max_tokens=24，不是 JSON），失败静默回退规则。
    """
    low = (text or "")[:3000].lower()
    score = {k: 0 for k in PAPER_TYPES}
    for kw in ("we propose", "our method", "we introduce a", "our model",
               "we present", "we develop", "our approach", "our framework"):
        score["method"] += 2 * low.count(kw)
    for kw in ("benchmark", "dataset", "we collect", "we curate"):
        score["dataset_benchmark"] += low.count(kw)
    # 裸 "survey/review" 常出现在相关工作里（"recent surveys have…"），
    # 降权；只有明确的综述措辞才给高分。
    for kw in ("this survey", "we survey", "systematic review",
               "literature review", "we summarize", "a survey of"):
        score["survey"] += 2 * low.count(kw)
    score["survey"] += 0.5 * (low.count("survey") + low.count("review"))
    for kw in ("we prove", "theorem", "theoretical"):
        score["theory"] += low.count(kw)
    # framework/implementation 在方法论文里也很常见，权重压低避免误判
    for kw in ("toolkit", "software package", "we implement a system"):
        score["system_tool"] += 3 * low.count(kw)
    ranked = sorted(score.values(), reverse=True)
    best = max(score, key=lambda k: score[k])
    conf = round(score[best] / max(sum(score.values()), 1), 2)
    margin = ranked[0] - (ranked[1] if len(ranked) > 1 else 0)
    method = "rule"
    uncertain = (conf < low_conf_threshold or margin <= 1
                 or sum(score.values()) == 0)
    if use_llm and uncertain and chat_fn:
        snippet = ((title.strip() + "\n") if title else "") + (text or "")[:800]
        p = ("判断下面这篇论文属于哪一类，只输出一个类型词，不要解释：\n"
             "method / dataset_benchmark / theory / survey / "
             "system_tool / application\n\n" + snippet)
        try:
            try:
                raw = chat_fn(p, max_tokens=24)
            except TypeError:
                raw = chat_fn(p)
            ans = str(raw).strip().lower()
            for cand in PAPER_TYPES:
                if cand in ans:
                    best, conf, method = cand, 0.75, "llm"
                    break
        except Exception:  # noqa: BLE001  分类失败必须回退规则
            pass
    plan = STAGE_PLAN.get(best, STAGE_PLAN["method"])
    return {"paper_type": best, "confidence": conf, "method": method,
            "margin": round(margin, 2), "uncertain": bool(uncertain),
            "scores": score, "stages": list(plan["stages"]),
            "focus": plan["focus"]}


def guide_text(text: str, graph: Any,
               paper_type: Dict[str, Any] | None = None,
               stage: str | None = None) -> str:
    p = ("论文类型 " + paper_type["paper_type"] + "；" +
         paper_type["focus"] if paper_type
         else "论文类型未判定，按通用方法论文处理")
    # 契约由 prompts.render 统一注入，这里只给 A-Box 与 Stage0
    parts = [abox_guide(text, graph, stage), "【Stage0 指导】" + p]
    return "\n".join(x for x in parts if x)
