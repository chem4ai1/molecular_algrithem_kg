"""VL 图注提示词：把论文页面转成可入库的结构化图注.

约束（与 PO 本体一致）：
- 只描述**图中可见**内容，不推断未展示的结论；
- 看不清的数值写 ``not_read``，不猜；
- 区分图（figure）/ 表（table）/ 分子结构（molecule）/ 纯文本（text）。
"""

from __future__ import annotations

CAPTION_PROMPT = """你在读一篇 AI 药物发现 / 分子设计 / 蛋白设计论文的页面渲染图。
请只根据**页面中可见的内容**输出 JSON，不要推测页面之外的结论，看不清的数值写 "not_read"。

输出严格使用以下 JSON 结构（缺项用空数组/空字符串，不要新增顶层字段）：

{
  "page_type": "figure | table | mixed | text",
  "summary": "一句话概括本页主要内容（<=60字）",
  "figures": [
    {
      "label": "Figure 2 或 Fig. 3(a)",
      "type": "bar | line | scatter | heatmap | diagram | molecule | distribution | other",
      "axes": {"x": "横轴含义与单位", "y": "纵轴含义与单位"},
      "key_values": ["图中可读出的关键数值或趋势，如 baseline 0.62 -> ours 0.71"],
      "conclusion": "该图支持的结论（仅限图上可见）"
    }
  ],
  "tables": [
    {"label": "Table 1", "columns": ["列名"], "key_cells": ["重要单元格内容"]}
  ],
  "molecule_depiction": true,
  "method_diagram": false,
  "evidence_quotes": ["页面上与图表直接相关的原文短句（<=30字/条，最多3条）"]
}

要求（务必紧凑，整体输出 <= 600 token，否则会被截断）：
1. 若本页没有图或表，page_type 写 "text"，figures/tables 为空数组；
2. key_values 最多 2 条，只写图上直接标注的数字，不要从正文抄；
3. evidence_quotes 最多 2 条，每条 <= 20 字；
4. 不要把表头当成结论；图多于 3 个时只描述最主要的 3 个；
5. 只输出 JSON，不要 markdown 代码块、不要解释。"""


def caption_prompt(extra: str = "") -> str:
    return CAPTION_PROMPT + (f"\n\n补充关注点：{extra}" if extra else "")
