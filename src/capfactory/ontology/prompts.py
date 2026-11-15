"""统一抽取 prompt builder：把 ②③④⑤ 的修正写进**源头约束**。

之前 ``refine.py`` 是在 LLM 输出之后做事后修正（derive_forms / split_methods /
extract_experiments），成本高且依赖返工。本模块把这些规则前移为 prompt 约束：

| 编号 | 事后修正 | 源头约束 |
|---|---|---|
| ② | `derive_forms` 从 schema 重算 form | prompt 里**禁止填 form**，只准写 schema；form 由 `refine.derive_forms` 派生 |
| ③ | `split_methods` 事后分基线 | prompt 强制 `proposed_methods` / `baselines` 两个独立数组 |
| ④ | `extract_experiments` 逐节补抽 | prompt 要求 `metrics[].name` 只能取自受控词表，逐节各给一份 |
| ⑤ | `sample_overlap` / `ensure_paper` | prompt 注入合法 `evidence_ids` 集合，只准在集合内选 |

另外把 ① 的代码符号清单、⑦ 的「只建被引用符号」也一起注入，
形成**一次调用就产出可入图结果**的唯一 prompt 入口。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Sequence

from .layers import DATA_FORMS, MECHANISMS, CAUSAL_TYPES, ALGORITHM_ROLES
from .metrics import metric_names_for_prompt
from .refine import FORM_RULES

BASE_PROMPT = """你是 AI4Science 论文的结构化知识抽取器。按**下面的字段契约**输出严格 JSON。

# 输出契约
{
  "paper": {"title": "", "arxiv_id": "", "doi": "", "paper_type": ""},
  "questions": [{"question": "", "granularity": "paper_specific",
                 "problem_category": "P01..P11 或空", "evidence_ids": []}],
  "proposed_methods": [{"name": "", "aliases": [], "architecture": ""}],
  "baselines": [{"name": "", "kind": "baseline"}],
  "modules": [
    {"module_name": "", "mechanism": "", "causal_role": "",
     "input_schema": "", "output_schema": "",
     "inputs": [], "outputs": [], "parameters": [],
     "equation_ref": "", "order": 1,
     "code_symbols": [], "grounding_status": "",
     "evidence_ids": []}
  ],
  "experiments": [
    {"section": "", "benchmark": "",
     "metrics": [{"name": "", "direction": "", "unit": ""}],
     "values": [{"metric": "", "value": 0, "unit": ""}]}
  ],
  "observations": [
    {"metric": "", "value": 0, "unit": "", "subject": "",
     "benchmark": "", "stage": "", "evidence_ids": []}
  ],
  "metric_proposals": [""],
  "limitations": [""]
}

{focus}
# 硬性规则（违反的字段会被校验器丢弃）
1. 【② 数据形式】**不要填 input_form / output_form**。只写 `input_schema` /
   `output_schema`（具体张量/字段名，如 "h_i^l, x_i^l, edge_attr"）。
   形式标签由程序按下表从 schema 派生：{form_rules}
2. 【③ 方法 vs 基线】`proposed_methods` 只放**本文提出**的方法；
   相关工作里被比较的 SchNet / DimeNet++ / TFN 等一律放 `baselines`。
   `baselines` 里的名字不得出现在 `proposed_methods`。
3. 【④ 指标受控】`metrics[].name` 与 `values[].metric` **只能**取自下面这份
   `MetricDefinition` 受控词表；不在表里的通用指标（如 MSE / BCE）写进
   `metric_proposals`，不要自造指标名、不要写展开式。
   受控词表：{metric_names}
4. 【④ 逐节】`experiments` 按 Results 的每个小节**各给一条**，
   不要把所有实验压成一条；`section` 写小节原文名。
5. 【⑤ 证据】`evidence_ids` 只能从下面给定的合法集合里选；集合为空时写 []，
   **严禁编造** `evidence:Fig1a` 这类 ID。
   合法证据 ID：{evidence_ids}
6. 【① 模块级】`modules` 4–10 条，每条是一个**具体模块/机制**，
   不是整体方法名。`mechanism` 取自 {mechanisms}，
   `causal_role` 取自 {causal_types}，`role` 取自 {roles}。
7. 【① 代码对齐】`code_symbols` 只能从下面代码清单里选**真实存在**的符号，
   支持 `message` / `EGNN_Sparse.message` 两种写法。按 mechanism + IO 对齐，
   不要按名字相似对齐；找不到留空并写 `grounding_status=conceptual_gap`。
8. 【⑦ 稀疏】只输出被 `code_symbols` 引用的符号；不要罗列仓库里所有函数。
9. 【研究问题】`questions` 每条必须是**可回答的问句**（不是主题词），
   并尽量给 `problem_category`；没有对应 P 类时留空，不要编造。
10. 【观测】`observations` 只写论文里**明确给出的数值**，
   带 metric/value/unit/subject/benchmark；没有数值就留空数组，严禁填 0 充当缺失。
11. 输出 <= 6000 token，只输出 JSON，不要代码块、不要解释。

# 代码符号清单（AST）
{code_symbols}

# 论文文本
{paper}

只输出 JSON。"""


def build_prompt(*, paper_text: str,
                 code_symbols: str = "",
                 evidence_ids: Iterable[str] = (),
                 paper_chars: int = 128000,
                 paper_type: str = "method") -> str:
    """``paper_chars`` 默认 128K 字符（polo gemini-3.8-flash 大上下文）。"""
    from ..sciforge.paper_types import focus_prompt_block
    """构造带全部源头约束的抽取 prompt。

    ``code_symbols`` 传 ``modules._compact_structure()`` 的结果；
    ``evidence_ids`` 传该论文已由规则生成的 Section/Evidence id 列表。
    """
    rules = "; ".join(f"{form}<-{','.join(keys[:3])}"
                      for form, keys in FORM_RULES[:9])
    ids = list(dict.fromkeys(str(x) for x in evidence_ids if x))
    return (BASE_PROMPT
            .replace("{form_rules}", rules)
            .replace("{metric_names}", metric_names_for_prompt())
            .replace("{evidence_ids}", ", ".join(ids[:40]) or "(本轮未提供，写 [])")
            .replace("{mechanisms}", ", ".join(MECHANISMS))
            .replace("{causal_types}", ", ".join(CAUSAL_TYPES))
            .replace("{roles}", ", ".join(ALGORITHM_ROLES))
            .replace("{code_symbols}", code_symbols or "(未提供代码清单，code_symbols 写 [])")
            .replace("{focus}", focus_prompt_block(paper_type))
            .replace("{paper}", paper_text[:paper_chars]))


def validate_source_constraints(raw: Dict[str, Any], *,
                                evidence_ids: Iterable[str] = ()) -> Dict[str, Any]:
    """校验 LLM 是否遵守源头约束；返回违规清单（不静默修正）。

    这条与事后修正互补：**先看模型有没有守规矩**，再决定要不要返工。
    """
    problems: Dict[str, Any] = {"violations": [], "counts": {}}
    allowed_ev = set(str(x) for x in evidence_ids)
    from .metrics import canonical_metric
    vocab = set()
    try:
        from ..po.vocab import default_registry
        vocab = set(default_registry.get("metric_name").values)
    except Exception:  # noqa: BLE001
        pass

    mods = raw.get("modules") or []
    problems["counts"] = {"modules": len(mods),
                          "proposed": len(raw.get("proposed_methods") or []),
                          "baselines": len(raw.get("baselines") or []),
                          "experiments": len(raw.get("experiments") or [])}
    if not (4 <= len(mods) <= 10):
        problems["violations"].append("②/① modules 数量不在 4–10")
    for i, m in enumerate(mods):
        if isinstance(m, dict) and (m.get("input_form") or m.get("output_form")):
            problems["violations"].append(f"② module[{i}] 违规填了 form（应只写 schema）")
        for eid in (m.get("evidence_ids") or []):
            if allowed_ev and eid not in allowed_ev:
                problems["violations"].append(f"⑤ module[{i}] 编造证据 ID {eid}")
    proposed = {str(x.get("name", "")).lower() for x in raw.get("proposed_methods") or []}
    for b in raw.get("baselines") or []:
        if str(b.get("name", "")).lower() in proposed:
            problems["violations"].append(f"③ 基线重复出现在 proposed_methods: {b.get('name')}")
    for exp in raw.get("experiments") or []:
        for m in exp.get("metrics") or []:
            name = str(m.get("name") or "")
            canon, _ = canonical_metric(name)
            if vocab and canon not in vocab and not raw.get("metric_proposals"):
                problems["violations"].append(
                    f"④ 指标 {name} 不在受控词表且未写进 metric_proposals")
    return problems


def legacy_prompt_names() -> Sequence[str]:
    """保留的旧 prompt 入口（兼容层，逐步废弃）。"""
    return ("instantiate.PROMPT", "modules.MODULE_PROMPT",
            "refine.EXPERIMENT_PROMPT")
