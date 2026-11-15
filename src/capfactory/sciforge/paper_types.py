"""论文类型体系 + 解析前的题目/摘要预分类 + 分类型抽取重心。

为什么需要：10 篇里 ``2306.08018``（Mol-Instructions）是**指令数据集论文**，
用「方法论文」的 prompt 去抽 modules 得到 0 个——不是模型失败，是**任务模板错了**。

设计：解析全文前先只用题目+摘要判类型，再按类型决定抽什么、跳过什么：

| 类型 | 抽什么 | 跳过 |
|---|---|---|
| ``method`` | 方法栈 / 模块 / 基线 / 实验 | — |
| ``survey`` | 分类法 / 被讨论方法 / 开放问题 | modules / code_symbols |
| ``dataset_benchmark`` | Benchmark 契约 / 模态 / 切分 / 任务 | modules |
| ``knowledge_base`` | 实体类型 / 关系 / 覆盖规模 | modules |
| ``evaluation`` | 指标 / 观测 / 对比基线 | 新模型模块 |
| ``theory`` | 假设 / 命题 / 推导条件 | experiments / code |
| ``system_tool`` | 组件 / API / 依赖 / 可运行性 | 抽象机制 |
| ``application`` | 领域 / 研究对象 / 效果 | 新算法模块 |
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence

from ..utils import parse_llm_json

PAPER_TYPES: Dict[str, Dict[str, str]] = {
    "method": {"label": "方法/算法论文",
               "definition": "提出新模型、新算法或新训练/生成机制，含消融与对比实验"},
    "survey": {"label": "综述/立场论文",
               "definition": "系统梳理某一方向的方法、分类法与开放问题，不提出单一新模型"},
    "dataset_benchmark": {"label": "数据集/基准/指令集论文",
                          "definition": "主要贡献是数据集、基准、指令语料、评测协议或数据资源"},
    "knowledge_base": {"label": "知识库/本体/图谱论文",
                       "definition": "主要贡献是知识库、本体、图谱构建、对齐或语义层"},
    "evaluation": {"label": "评测/实证研究",
                   "definition": "系统比较已有方法、复现测量或分析失败模式，不以新方法为主"},
    "theory": {"label": "理论分析论文",
               "definition": "给出性质证明、泛化界、等价性或复杂度分析"},
    "system_tool": {"label": "系统/工具/平台论文",
                    "definition": "主要贡献是软件系统、工具链、平台或工程实现"},
    "application": {"label": "应用案例论文",
                    "definition": "把已有方法用到具体科学问题并报告实测效果"},
}

TYPE_FOCUS: Dict[str, Dict[str, Any]] = {
    "method": {"sections": ("abstract", "method", "experiment", "result"),
               "must_extract": ("proposed_methods", "baselines", "modules",
                                "questions", "experiments", "observations"),
               "skip": (), "prompt_hint": "重点拆方法栈的模块、机制与输入输出，并抽研究问题"},
    "survey": {"sections": ("abstract", "introduction", "taxonomy", "conclusion"),
               "must_extract": ("questions", "taxonomy", "methods_mentioned",
                                "open_problems"),
               "skip": ("modules", "code_symbols"),
               "prompt_hint": "不要抽方法模块；抽分类法、被综述的方法名与开放问题"},
    "dataset_benchmark": {"sections": ("abstract", "dataset", "benchmark",
                                        "construction", "experiment"),
                          "must_extract": ("questions", "benchmarks", "data_modalities",
                                           "split_types", "tasks", "observations"),
                          "skip": ("modules",),
                          "prompt_hint": "重点写基准的输入输出契约、模态、切分与任务，不要硬抽算法模块"},
    "knowledge_base": {"sections": ("abstract", "ontology", "construction",
                                     "evaluation"),
                       "must_extract": ("questions", "entity_types", "relations",
                                        "coverage", "observations"),
                       "skip": ("modules",),
                       "prompt_hint": "抽实体类型、关系模式与覆盖规模"},
    "evaluation": {"sections": ("abstract", "setup", "result", "analysis"),
                   "must_extract": ("questions", "metrics", "observations",
                                    "compared_methods", "benchmarks"),
                   "skip": ("modules",),
                   "prompt_hint": "重点抽指标定义与每条观测值，含对比方法"},
    "theory": {"sections": ("abstract", "assumption", "theorem", "proof"),
               "must_extract": ("questions", "assumptions", "claims",
                                "derivation_conditions"),
               "skip": ("modules", "experiments", "code_symbols"),
               "prompt_hint": "抽假设、命题与推导条件，不要抽实验与代码"},
    "system_tool": {"sections": ("abstract", "architecture", "implementation",
                                  "usage"),
                    "must_extract": ("questions", "components", "apis",
                                     "dependencies", "observations"),
                    "skip": ("abstract_mechanisms",),
                    "prompt_hint": "抽组件、接口、依赖与可运行性"},
    "application": {"sections": ("abstract", "case", "result", "discussion"),
                    "must_extract": ("questions", "research_objects",
                                     "applied_methods", "observations"),
                    "skip": ("new_modules",),
                    "prompt_hint": "抽研究对象、所用方法与实测效果"},
}

TYPE_PROMPT = """判下面这篇 AI4Science 论文的**主要贡献类型**。只依据题目与摘要。

类型（只能选一个）：
{types}

判断要点：
- 主要贡献是「新数据集/基准/指令语料」→ dataset_benchmark，即使文中也用了模型；
- 主要贡献是「系统梳理与分类」→ survey；
- 主要贡献是「知识库/本体/图谱」→ knowledge_base；
- 主要贡献是「新模型/新算法」→ method；
- 主要贡献是「比较与测量」→ evaluation。

输出严格 JSON：
{{"paper_type":"", "confidence":0.0, "signals":["题目/摘要里的判断依据"],
  "secondary_type":"", "rationale":"一句话"}}

## 题目
{title}

## 摘要
{abstract}

只输出 JSON。"""


def type_prompt(title: str, abstract: str) -> str:
    types = "\n".join(f"- {k}: {v['label']} — {v['definition']}"
                      for k, v in PAPER_TYPES.items())
    return (TYPE_PROMPT.replace("{types}", types)
                       .replace("{title}", (title or "")[:500])
                       .replace("{abstract}", (abstract or "")[:4000]))


def classify_paper_type(title: str, abstract: str, *, chat_fn: Any,
                        task: str = "paper_type") -> Dict[str, Any]:
    """解析前预分类；模型失败时退回保守的关键词规则。"""
    raw = parse_llm_json(chat_fn(type_prompt(title, abstract))) or {}
    t = str(raw.get("paper_type") or "")
    if t not in PAPER_TYPES:
        t = _rule_fallback(f"{title} {abstract}")
        raw = {"paper_type": t, "confidence": 0.55,
               "signals": ["LLM 未给出合法类型，规则兜底"],
               "rationale": "fallback"}
    raw.setdefault("confidence", 0.8)
    raw["focus"] = TYPE_FOCUS.get(t, TYPE_FOCUS["method"])
    raw["task_tag"] = task
    return raw


def _rule_fallback(text: str) -> str:
    low = (text or "").lower()
    rules = (
        ("survey", ("survey", "review of", "systematic review", "综述")),
        ("dataset_benchmark", ("dataset", "benchmark", "instruction", "corpus",
                               "we present a dataset", "data resource")),
        ("knowledge_base", ("knowledge graph", "knowledge base", "ontology",
                            "知识库", "本体")),
        ("evaluation", ("empirical study", "benchmarking", "evaluation of",
                        "comparative study")),
        ("theory", ("we prove", "theoretical", "generalization bound",
                    "convergence analysis")),
        ("system_tool", ("we present a system", "platform", "toolkit",
                         "software", "framework for")),
    )
    for t, keys in rules:
        if any(k in low for k in keys):
            return t
    return "method"


def focus_prompt_block(paper_type: str) -> str:
    """注入主抽取 prompt 的「按类型调整抽取重心」段。"""
    f = TYPE_FOCUS.get(paper_type, TYPE_FOCUS["method"])
    skip = ", ".join(f["skip"]) or "无"
    must = ", ".join(f["must_extract"])
    return (f"\\n# 论文类型与抽取重心\\n"
            f"本文类型：{paper_type}（{PAPER_TYPES.get(paper_type, {}).get('label','')}）。\\n"
            f"{f['prompt_hint']}。\\n"
            f"必抽字段：{must}。\\n"
            f"跳过/留空：{skip}。\\n"
            f"优先阅读的小节：{', '.join(f['sections'])}。\\n")
