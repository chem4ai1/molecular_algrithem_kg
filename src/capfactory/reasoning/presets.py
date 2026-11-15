"""面向「论文 + 代码 + 复现」图的预设推理规则。

只使用**真实存在**的关系（关系名小写，与 engine 的 EDB 编码一致），
从扁平事实推出可查询的多跳结论。置信度按「跨层推断更不确定」递减。

设计原则：推理不能凭空造节点。像 `CONSUMES / PRODUCES / SCORED_BY`
这类需要 `MethodApplication` 与 `DataForm` 节点的边，必须先由抽取/建图补齐
（见 docs/REASONING_LAYER.md 的「抽取清单」），规则层只做可达性推导。
"""
from __future__ import annotations
from typing import Any, Dict, List

PAPER_RULES: List[Dict[str, Any]] = [
    {"id": "R01_code_for_paper",
     "rule": "code_implements_paper(F,P) :- implements_module(F,S), has_module_detail(P,S).",
     "confidence": 0.90, "note": "代码实现模块 + 论文有该模块 => 代码实现了该论文的部分方法"},
    {"id": "R02_module_has_code",
     "rule": "module_has_code(S,F) :- implements_module(F,S).",
     "confidence": 1.0, "note": "反向边，便于从模块查代码"},
    {"id": "R03_paper_metric",
     "rule": "paper_has_metric(P,M) :- reports(P,O), of_metric(O,M).",
     "confidence": 0.95, "note": "论文 -> 观测 -> 指标定义"},
    {"id": "R04_paper_benchmark",
     "rule": "paper_on_benchmark(P,B) :- evaluated_on(P,B).",
     "confidence": 1.0, "note": "别名，统一命名"},
    {"id": "R05_paper_algorithm",
     "rule": "paper_uses_algorithm(P,A) :- proposes_method(P,A).",
     "confidence": 1.0, "note": "别名"},
    {"id": "R06_same_metric_observation",
     "rule": "same_metric(O1,O2) :- of_metric(O1,M), of_metric(O2,M).",
     "confidence": 1.0, "note": "两个观测是否用同一指标定义（跨论文可比的原料）"},
    {"id": "R07_comparable_papers",
     "rule": "comparable(P1,P2) :- evaluated_on(P1,B), evaluated_on(P2,B).",
     "confidence": 0.80, "note": "同基准的论文可比；仍需 group_key 才能谈 SOTA"},
    {"id": "R08_paper_claim",
     "rule": "grounded_claim(C) :- supported_by(C,E).",
     "confidence": 1.0, "note": "有证据边的主张；不做论文×主张的笛卡尔积"},
]

PROCESS_RULES: List[Dict[str, Any]] = [
    {"id": "R09_phase_before_base",
     "rule": "phase_before(A,C) :- precedes(A,B), precedes(B,C).",
     "confidence": 1.0, "note": "相位顺序的两跳传递"},
    {"id": "R10_phase_before_recursive",
     "rule": "phase_before(A,C) :- precedes(A,B), phase_before(B,C).",
     "confidence": 1.0, "note": "递归传递闭包；检验 semi-naive fixpoint 与终止"},
    {"id": "R11_claim_grounded",
     "rule": "claim_grounded(C) :- anchored_to(C,A), produced_by(A,E).",
     "confidence": 0.95, "note": "主张锚到字节即视为 grounded"},
    {"id": "R12_repro_chain",
     "rule": "reproduces(X,E) :- reports_on(X,S), asserts(S,C), anchored_to(C,A), produced_by(A,E).",
     "confidence": 0.90, "note": "验收报告 -> 章节 -> 主张 -> 锚 -> 实验节点"},
    {"id": "R13_code_generated_by",
     "rule": "code_generated_by(F,T) :- generates(T,F).",
     "confidence": 1.0, "note": "反向：代码函数由哪个生成任务产出"},
    {"id": "R14_result_of_run",
     "rule": "result_of(R,T) :- runs_in(T,E), emits(E,R).",
     "confidence": 0.95, "note": "代码生成任务 -> 实验节点 -> 结果"},
]


def default_rules() -> List[Dict[str, Any]]:
    return PAPER_RULES + PROCESS_RULES


def rule_inventory() -> Dict[str, Any]:
    rs = default_rules()
    return {"n_rules": len(rs),
            "paper": len(PAPER_RULES), "process": len(PROCESS_RULES),
            "ids": [r["id"] for r in rs],
            "min_confidence": min(r["confidence"] for r in rs)}
