"""语义层抽取 prompt（v4.1）。每个输出 JSON 的字段都能在契约里找到。

通用规则（每个模板都会自动拼接）：
  - 只输出纯 JSON，不要代码块/解释；
  - 找不到就给空字符串 / 空数组，**不要编造、不要补理由**；
  - 每个可选字段失败不影响必填字段（校验器会单独归一）；
  - evidence 必须是从给定原文逐字复制的短句（≤120 字）。
"""
from __future__ import annotations
from typing import Any, Dict

from .contracts import contract_text, FORM_VOCAB, DOMAIN_CODES, _task_types

COMMON = """你是知识图谱语义层抽取器。只基于下面给出的原文片段抽取。
输出严格纯 JSON（不要 ``` 代码块、不要解释、不要补理由）。
规则：
1. 不确定就留空字符串 "" 或空数组 []，禁止编造、禁止写"未知/未提及"之外的解释。
2. 字段值不超过 60 字，数组最多 6 项；宁缺毋滥。
3. evidence 必须从原文逐字复制（≤120 字），不得改写。
4. 遇到词表外的新类：字段填 "other"，并在 proposed_new 写出建议新类名。
{catalogs}
"""

PROMPTS: Dict[str, str] = {
    "E1_paper": """任务：抽 Paper 的核心属性（研究什么问题 / 问题类别 / 瓶颈 / 关系线索）。
输出 JSON：
{"research_question":"一句话说清本文研究什么问题（含输入、目标、约束）",
  "problem_category":"从 TASK_TYPES 词表里选一个，没有就空",
  "domain_code":"D0..D10，不确定留空（后续由规则校准）",
  "why_hard":"现有方法的瓶颈 1 句",
  "relation_hints":{"related_papers":["相关方法/文献名"],
                    "algorithms":["本文提到的算法名"],
                    "benchmarks":["本文提到的数据集/基准名"]},
  "evidence":{"research_question":"逐字引文","why_hard":"逐字引文"}}
注意：research_question 与 problem_category 是**字符串**，不是数组、不建节点。
【论文标题】{title}
【规则层候选信号（problem_category 只能从这里选）】
{rule_hints}
【摘要与引言】
{paper_text}
""",
    "E2_algorithm": """任务：抽 Algorithm 及它的 AlgorithmModule（算法模块）。
输出 JSON：
{"algorithms":[{"name":"算法名",
  "task_type":"从 TASK_TYPES 选一个",
  "problems_solved":["能解决什么问题，最多 3 句"],
  "mechanism":"机理 1-2 句（怎么做）",
  "why_it_works":"为什么有效，可空",
  "applicable_to":["适用场景"],
  "limitations":["作者明确指出的局限"],
  "modules":[{"name":"模块名","mechanism":"动宾短语",
    "formula":"原文公式片段或空","inputs":"输入","outputs":"输出",
    "code_symbols":["只能从代码符号清单选"],
    "tools":["方法节真实出现的工具/库/力场"]}]}]}
规则：
1. modules 3-6 个，按方法逻辑顺序；mechanism 用动宾短语，不照抄标题。
2. code_symbols 只能从【代码符号清单】选，禁止发明函数/类。
3. tools 只写方法节真实出现的；formula 必须是原文片段。
4. flow_family（算法族）不由你判定，规则层会算。
【方法节】
{paper_text}
【代码符号清单】
{code_symbols}
""",
    "E3_benchmark": """任务：抽 Benchmark 的结构字段（**不要输出任何数值**）。
输出 JSON：
{"benchmarks":[{"name":"明确命名的数据集/基准名",
  "input_form":"从 FORM_VOCAB 选","output_form":"从 FORM_VOCAB 选",
  "n_samples":"样本量描述或空","scale":"规模描述或空",
  "modality":"数据模态或空","research_object":"研究对象或空",
  "metrics":[{"name":"指标名","unit":"单位或空","direction":"min|max|空"}]}]}
规则：benchmarks ≤3；metrics ≤4；input/output_form 必须来自封闭词表；
数值/模型成绩一律不输出（下一阶段由表格解析负责）。
【实验节】
{paper_text}
""",
    "E4_values": """任务：兜底抽取**表格之外**明确写出的评测数值。
输出 JSON：
{"model_results":[{"model":"方法名","metric":"指标名",
  "value":0,"unit":"单位或空","benchmark":"基准名",
  "source":"table:1|text:段落|空","evidence":"逐字引文"}]}
规则：
1. 最多 8 条；value 必须是数字（不要字符串）。
2. 禁止把 表号/年份/epoch/dropout/学习率/引用编号/参数量 当数值。
3. 表格里的数值由确定性表格解析器抽，你只补正文明确写出的；没有就空数组。
【实验节与表格文本】
{paper_text}
""",
    "E6_lineage": """任务：抽**算法-算法改进链**（本文方法继承自/替换了/改进了哪些已有方法）。
输出 JSON：
{"lineage":[{"from":"本文方法名","to":"被继承/替换/改进的方法名",
  "kind":"extends|replaces|improves|compared_with","evidence":"逐字引文"}]}
规则：
1. 只依据明确的谱系措辞：builds on / extends / is based on / follows /
   improves upon / replaces / unlike X we ...（最后一种算 compared_with）。
2. kind 判定：继承或基于 → extends；换掉机制 → replaces；同维度提升 → improves；
   只是拿来做对比/基线 → compared_with（**这种不会建 SUBCLASS_OF 边**）。
3. evidence 必须从原文逐字复制（≤120 字）；没有谱系措辞就输出空数组。
4. 最多 6 条；from 与 to 都必须是算法/方法名，不要写论文标题、作者或数据集。
【Related Work / Introduction / Method 文本】
{paper_text}
""",
    "E5_relations": """任务：为算法模块补「工具」与「公式」两类关系（**只允许这两类**）。
输出 JSON：
{"relations":[{"module":"模块名","kind":"tool|formula",
  "target":"工具名或公式编号","evidence":"逐字引文"}]}
规则：
1. kind 只能是 tool 或 formula；module 必须是上一阶段抽出的模块名。
2. 其它关系（论文→算法、模块→代码、仓库→函数、算法→基准）全部由规则/AST 建，不要输出。
3. 科技树链（对比/改进/局限）不属于语义层，不要输出。
【方法节】
{paper_text}
""",
}


def catalogs(text: str = "", stage: str | None = None) -> str:
    """按阶段拼装：动态词表（top20）+ 该阶段契约。无关类/词表不注入。"""
    from .vocab import render as _render_vocab
    from .contracts import contract_text
    parts = [_render_vocab(text, stage=stage), contract_text(stage)]
    return "\n".join(x for x in parts if x)


def render(stage: str, *, title: str = "", paper_text: str = "",
           code_symbols: str = "", rule_hints: str = "") -> str:
    """拼出完整 prompt：通用规则 + 语义层契约 + 阶段模板。"""
    cat = catalogs(paper_text, stage)
    head = COMMON.replace("{catalogs}", cat)
    body = PROMPTS[stage]
    for k, v in (("title", title), ("paper_text", paper_text),
                 ("code_symbols", code_symbols),
                 ("rule_hints", rule_hints)):
        body = body.replace("{" + k + "}", str(v or "(无)"))
    return head + body


def stages() -> tuple:
    return tuple(PROMPTS)
