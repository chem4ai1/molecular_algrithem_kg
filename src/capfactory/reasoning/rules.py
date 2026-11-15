"""规则与推导断言的数据结构（借鉴 semantica，修正其 provenance 缺陷）。

与 semantica 的三点不同：
1. EDB（原始事实）与 IDB（推导事实）严格分离，推导**不写回** facts；
2. 每条 DerivedAssertion 带 ``origin / rule_id / premises / confidence /
   iteration / phase``，可重建 derivation tree；
3. 置信度沿链取 min（保守传播），不是直接复制 rule.confidence。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple, Optional

Fact = Tuple[str, ...]          # (predicate, arg1, arg2, ...)
Atom = Tuple[str, ...]          # 同上，但参数可为变量（大写开头）


def is_var(x: str) -> bool:
    return bool(x) and x[0].isupper()


@dataclass(frozen=True)
class Rule:
    rule_id: str
    head: Atom
    body: Tuple[Atom, ...]
    confidence: float = 1.0
    note: str = ""

    @property
    def predicate(self) -> str:
        return self.head[0]


@dataclass(frozen=True)
class DerivedAssertion:
    """一等公民的推导三元组，带完整 provenance。"""
    fact: Fact
    rule_id: str
    premises: Tuple[Fact, ...] = ()
    confidence: float = 1.0
    iteration: int = 0
    origin: str = "inferred"
    phase: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"fact": list(self.fact), "rule_id": self.rule_id,
                "premises": [list(p) for p in self.premises],
                "confidence": round(self.confidence, 4),
                "iteration": self.iteration, "origin": self.origin,
                "phase": self.phase}


def parse_rule(text: str, *, rule_id: str = "", confidence: float = 1.0,
               note: str = "") -> Rule:
    """解析 ``head(X,Y) :- body1(X,Z), body2(Z,Y).``（大写=变量）。"""
    s = (text or "").strip().rstrip(".")
    if ":-" not in s:
        raise ValueError(f"规则缺 ':-': {text}")
    head_s, body_s = s.split(":-", 1)

    def atom(x: str) -> Atom:
        x = x.strip()
        if "(" not in x or not x.endswith(")"):
            return (x,)
        pred, args = x[:-1].split("(", 1)
        return tuple([pred.strip()] + [a.strip() for a in args.split(",")])

    def split_top(text: str) -> List[str]:
        """按括号外层的逗号切分，避免把 atom 内部的参数逗号切开。"""
        out, buf, depth = [], [], 0
        for ch in text:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if ch == "," and depth == 0:
                out.append("".join(buf).strip()); buf = []
            else:
                buf.append(ch)
        if "".join(buf).strip():
            out.append("".join(buf).strip())
        return [x for x in out if x]

    head = atom(head_s)
    body = tuple(atom(b) for b in split_top(body_s))
    if not body:
        raise ValueError(f"规则 body 为空: {text}")
    return Rule(rule_id=rule_id or f"R{abs(hash(text)) % 10000}",
                head=head, body=body, confidence=confidence, note=note)


def build_rules(specs: List[Dict[str, Any]]) -> List[Rule]:
    """从 [{'id','rule','confidence','note'}] 批量构造，按 id 去重。"""
    out, seen = [], set()
    for s in specs:
        r = parse_rule(s["rule"], rule_id=s.get("id", ""),
                       confidence=float(s.get("confidence", 1.0)),
                       note=str(s.get("note", "")))
        if r.rule_id not in seen:
            seen.add(r.rule_id)
            out.append(r)
    return out
