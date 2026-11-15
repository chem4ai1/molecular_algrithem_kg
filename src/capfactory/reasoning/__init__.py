"""知识图谱推理层：规则、半朴素不动点、推导 provenance、解释。

从 semantica.reasoning 借鉴：Datalog delta-based fixpoint、前/后向链意图、
模板化解释；修正其 EDB/IDB 混写、置信度不传播、解释非树状的缺陷。
纯标准库，直接吃 ``capfactory.po.POGraph``。
"""
from .rules import (Fact, Atom, Rule, DerivedAssertion, is_var,
                    parse_rule, build_rules)
from .engine import ReasoningEngine
from .presets import (PAPER_RULES, PROCESS_RULES, default_rules,
                      rule_inventory)
from .explain import explain_tree, reasoning_report

__all__ = ["Fact", "Atom", "Rule", "DerivedAssertion", "is_var",
           "parse_rule", "build_rules", "ReasoningEngine",
           "PAPER_RULES", "PROCESS_RULES", "default_rules", "rule_inventory",
           "explain_tree", "reasoning_report"]
