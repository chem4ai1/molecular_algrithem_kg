"""四类 LLM 任务的提示词模板：知识抽取 / 推理 / 缺口发现 / 总结.

设计约束（与 ``semantics.TASK_PROTOCOLS`` 一一对应）：

* **schema 先行**：prompt 里直接给类 ID、必填字段、关系 domain/range，
  让模型只能填已定义的槽位，减少自造字段；
* **归属与缺失显式**：每条输出要求 ``attribution`` 与 ``evidence_ids``；
  无值必须写 ``missing_state``，禁止填 0；
* **可校验**：输出是 JSON，可用 ``validate_po_graph`` / ``Concept.validate`` 复核；
* **不喂全图**：只喂 ``context_pack`` 选出的子图，控制 token 并降低幻觉。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .semantics import SemanticBundle, TASK_PROTOCOLS, build_bundle

ROLE = ("你是多肽与 AI 药物发现领域的知识工程师，熟悉问题导向本体（PO）、"
        "因果推断与实验证据分级。你的输出必须是可被程序校验的结构化 JSON。")

ATTRIBUTION_VALUES = ("author_explicit", "author_measured", "analyst_synthesis",
                      "analyst_derived", "evidence_bounded_synthesis")
MISSING_VALUES = ("not_reported", "not_read", "not_extracted", "not_applicable",
                  "not_measured", "failed", "withheld", "unknown")


def compact_schema(bundle: Optional[SemanticBundle] = None, *,
                   max_classes: int = 40) -> str:
    """精简 schema 文本：类（ID｜定义｜必填｜词表绑定）+ 关系（domain→range）。"""
    b = bundle or build_bundle(include_vocab=False)
    lines = ["## 概念类（只能使用这些 type）"]
    for c in b.classes[:max_classes]:
        req = ",".join(c["required"]) or "-"
        vocab = ",".join(f"{k}∈{v}" for k, v in c["vocab_bindings"].items()) or "-"
        lines.append(f"- {c['id']}｜{c['definition'][:56]}｜必填:{req}｜词表:{vocab}")
    lines.append("")
    lines.append("## 关系（只能使用这些 relation）")
    for r in b.relations:
        dom = "|".join(r["domain"])
        rng = "|".join(r["range"])
        lines.append(f"- {r['id']}：{dom} → {rng}")
    return "\n".join(lines)


def _rules_block(protocol: Dict[str, Any]) -> str:
    rules = "\n".join(f"{i+1}. {r}" for i, r in enumerate(protocol["rules"]))
    return f"""## 硬性规则
{rules}
{len(protocol["rules"])+1}. attribution ∈ {list(ATTRIBUTION_VALUES)}；分析者推断必须用 analyst_*。
{len(protocol["rules"])+2}. 数值缺失时写 missing_state ∈ {list(MISSING_VALUES)}，严禁填 0 或估计值。
{len(protocol["rules"])+3}. 每个节点/边都要有 evidence_ids（指向给定 Evidence 节点）或显式 attribution。
{len(protocol["rules"])+4}. 不得编造 DOI、页码、registry ID、靶点物种。"""


def _schema_block(protocol: Dict[str, Any]) -> str:
    return ("## 输出 JSON Schema\n```json\n"
            + json.dumps(protocol["output_schema"], ensure_ascii=False, indent=2)
            + "\n```")


_EXTRACTION_FEWSHOT = """## 示例（片段）
输入: "A threshold of 0.5 is applied to the predicted toxicity probability. IC50 = 0.63 nM at pH 7.4 with cGAMP substrate (Table 2)."
输出:
```json
{"nodes":[
 {"id":"metric:IC50","type":"MetricDefinition","label":"IC50",
  "attrs":{"name":"IC50","direction":"lower","unit_scale":"concentration"},
  "attribution":"author_explicit","evidence_ids":["evidence:T2"]},
 {"id":"observation:01","type":"MetricObservation","label":"IC50 = 0.63 nM",
  "attrs":{"metric":"IC50","value":0.63,"unit":"nM","stage":"tested",
           "condition":{"pH":7.4,"substrate":"cGAMP"}},
  "attribution":"author_measured","evidence_ids":["evidence:T2"]}],
 "assertions":[
 {"source":"observation:01","target":"metric:IC50","relation":"OF_METRIC",
  "attribution":"author_explicit","evidence_ids":["evidence:T2"]}]}
```
注意: 原文没有 CI 时写 missing_state，而不是 0。"""


def extraction_prompt(*, text: str, paper_id: str = "", paper_version_id: str = "",
                      evidence_locator: str = "",
                      bundle: Optional[SemanticBundle] = None,
                      max_nodes: int = 30,
                      max_text_chars: int = 12000) -> str:
    """抽取 prompt。

    ``max_text_chars`` 默认 12K（块级抽取）；整篇抽取时传 60000+，
    配合 qwen3.8-27B 的 64K 上下文（vLLM ``--max-model-len 65536``）使用。
    注意：超出上下文会由服务端截断并报错，别盲目传 1M。
    """
    b = bundle or build_bundle(include_vocab=False)
    p = TASK_PROTOCOLS["extraction"]
    return f"""{ROLE}

# 任务：知识抽取
从给定文本抽取 PO 概念与断言，最多 {max_nodes} 个节点。
论文: {paper_id or "(未给出)"}
版本: {paper_version_id or "(未给出)"}
证据定位: {evidence_locator or "(未给出)"}

{compact_schema(b)}

{_rules_block(p)}

{_schema_block(p)}

{_EXTRACTION_FEWSHOT}

## 待抽取文本
\"\"\"
{text[:max_text_chars]}
\"\"\"

只输出 JSON，不要解释。"""


def reasoning_prompt(*, pack: Dict[str, Any], question: str,
                     bundle: Optional[SemanticBundle] = None) -> str:
    b = bundle or build_bundle(include_vocab=False)
    p = TASK_PROTOCOLS["reasoning"]
    return f"""{ROLE}

# 任务：基于给定子图回答
问题: {question}

{compact_schema(b, max_classes=20)}

## 图中推理规则
{json.dumps(pack.get("schema", {}).get("rules", []), ensure_ascii=False, indent=2)}

## 相关子图（已裁剪，truncated={pack.get('subgraph', {}).get('truncated')}）
```json
{json.dumps(pack.get("subgraph", {}), ensure_ascii=False)[:14000]}
```

{_rules_block(p)}

{_schema_block(p)}

要求: 结论必须引用 node id；不可比观测不得比较大小；缺失不得当作 0 或阴性。"""


def gap_prompt(*, stats: Dict[str, Any], gaps: Dict[str, Any],
               bundle: Optional[SemanticBundle] = None) -> str:
    b = bundle or build_bundle(include_vocab=False)
    p = TASK_PROTOCOLS["gap_discovery"]
    return f"""{ROLE}

# 任务：缺口发现与排序
下面是确定性统计与候选缺口，请复核、补充理由并排序（不要编造不存在的节点）。

## 统计
```json
{json.dumps(stats, ensure_ascii=False)[:9000]}
```

## 候选缺口
```json
{json.dumps(gaps.get("gaps", []), ensure_ascii=False)[:9000]}
```

{compact_schema(b, max_classes=14)}

{_rules_block(p)}

{_schema_block(p)}

要求: 严重度依据「无实现 > 无评测 > 无证据 > 覆盖空白」；「未抽取」不等于「不存在」。"""


def summary_prompt(*, stats: Dict[str, Any], scope: str = "all",
                   selected: Optional[List[Dict[str, Any]]] = None,
                   bundle: Optional[SemanticBundle] = None) -> str:
    p = TASK_PROTOCOLS["summarization"]
    return f"""{ROLE}

# 任务：结构化总结（scope={scope}）
只能使用下面统计里的数字，不得估算或外推。

## 统计
```json
{json.dumps(stats, ensure_ascii=False)[:10000]}
```

## 代表性节点
```json
{json.dumps(selected or [], ensure_ascii=False)[:6000]}
```

{compact_schema(bundle or build_bundle(include_vocab=False), max_classes=10)}

{_rules_block(p)}

{_schema_block(p)}

要求: 保留证据模态分层（computational / biochemical / in_vitro / animal / clinical），
不得压成单一总分；结尾必须列出覆盖边界。"""


_BUILDERS = {
    "extraction": extraction_prompt,
    "reasoning": reasoning_prompt,
    "gap_discovery": gap_prompt,
    "summarization": summary_prompt,
}


def build_prompt(task: str, **kwargs: Any) -> str:
    fn = _BUILDERS.get(task)
    if not fn:
        raise ValueError(f"未知任务 {task!r}；可选 {list(_BUILDERS)}")
    return fn(**kwargs)


def prompt_catalog() -> Dict[str, Any]:
    """返回四类任务的元信息（供前端/文档展示，不返回完整 prompt）。"""
    return {
        "tasks": {k: {"goal": v["goal"], "input": v["input"],
                      "rules": v["rules"], "post_checks": v["post_checks"],
                      "output_schema": v["output_schema"]}
                  for k, v in TASK_PROTOCOLS.items()},
        "attribution_values": list(ATTRIBUTION_VALUES),
        "missing_values": list(MISSING_VALUES),
        "note": "prompt 通过 build_prompt(task, **kwargs) 生成；输入来自 context_pack。",
    }
