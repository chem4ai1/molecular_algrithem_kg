"""推导结论的模板化解释（零 LLM）与推理报告。"""
from __future__ import annotations
from typing import Any, Dict, List


def explain_tree(engine: Any, fact: Any, *, depth: int = 0,
                 max_depth: int = 6) -> str:
    tree = engine.explain(fact)
    pad = "  " * depth
    head = ".".join(str(x).split(":")[-1] for x in tree["fact"])
    line = f"{pad}- {head} [{tree['origin']}, conf={tree.get('confidence',1.0)}"
    if tree.get("rule_id"):
        line += f", {tree['rule_id']}"
    line += "]"
    if depth >= max_depth or not tree.get("children"):
        return line
    return line + "\n" + "\n".join(
        explain_tree(engine, tuple(c["fact"]), depth=depth + 1,
                     max_depth=max_depth) for c in tree["children"])


def reasoning_report(engine: Any, *, top_k: int = 6) -> Dict[str, Any]:
    return {
        "edb": len(engine.edb),
        "derived": len(engine.idb),
        "iterations": engine.iterations,
        "rules": [r.rule_id for r in engine.rules],
        "consistency": engine.consistency(),
        "sample_derivations": [d.to_dict() for d in
                               list(engine.idb.values())[:top_k]],
        "by_rule": _by_rule(engine),
    }


def _by_rule(engine: Any) -> Dict[str, int]:
    from collections import Counter
    return dict(Counter(d.rule_id for d in engine.idb.values()))
