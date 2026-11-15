"""半朴素不动点推理引擎（纯标准库，直接吃 POGraph）。

借鉴 semantica datalog_reasoner 的 delta-based fixpoint，但修正三点：
EDB/IDB 分离、推导带完整 provenance、置信度沿链取 min。
"""
from __future__ import annotations
from collections import defaultdict, deque
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from .rules import (Fact, Atom, Rule, DerivedAssertion, is_var,
                    parse_rule, build_rules)


def _unify(atom: Atom, fact: Fact,
           bindings: Dict[str, str]) -> Optional[Dict[str, str]]:
    if atom[0] != fact[0] or len(atom) != len(fact):
        return None
    out = dict(bindings)
    for a, v in zip(atom[1:], fact[1:]):
        if is_var(a):
            if a in out and out[a] != v:
                return None
            out[a] = v
        elif a != v:
            return None
    return out


def _substitute(atom: Atom, b: Dict[str, str]) -> Fact:
    return tuple(b.get(x, x) if is_var(x) else x for x in atom)


class ReasoningEngine:
    """在 POGraph 断言之上做规则推理；不修改原图。"""

    def __init__(self, graph: Any, *, include_types: bool = True) -> None:
        self.graph = graph
        self.edb: Set[Fact] = set()
        self.rules: List[Rule] = []
        self.idb: Dict[Fact, DerivedAssertion] = {}
        self.iterations: int = 0
        for a in graph.assertions:
            self.edb.add((a.relation.lower(), a.source, a.target))
        if include_types:
            for n in graph.nodes.values():
                self.edb.add(("type_of", n.id, n.type))
        self._index: Dict[str, Set[Fact]] = defaultdict(set)
        for f in self.edb:
            self._index[f[0]].add(f)

    def add_rule(self, text: str, **kw: Any) -> Rule:
        r = parse_rule(text, **kw)
        self.rules.append(r)
        return r

    def add_rules(self, specs: List[Dict[str, Any]]) -> List[Rule]:
        rs = build_rules(specs)
        self.rules.extend(rs)
        return rs

    def derive_all(self, *, max_iterations: int = 20,
                   min_confidence: float = 0.0) -> Dict[str, Any]:
        all_facts: Set[Fact] = set(self.edb)
        delta: Set[Fact] = set(self.edb)
        idx: Dict[str, Set[Fact]] = defaultdict(set)
        for f in all_facts:
            idx[f[0]].add(f)
        conf: Dict[Fact, float] = {f: 1.0 for f in self.edb}
        it = 0
        while delta and it < max_iterations:
            it += 1
            new: Set[Fact] = set()
            didx: Dict[str, Set[Fact]] = defaultdict(set)
            for f in delta:
                didx[f[0]].add(f)
            for rule in self.rules:
                for pos in range(len(rule.body)):
                    for derived, premises, pconf in self._apply_rule(
                            rule, pos, didx, idx, conf):
                        c = min(rule.confidence, pconf)
                        if c < min_confidence or derived in all_facts:
                            continue
                        all_facts.add(derived)
                        idx[derived[0]].add(derived)
                        conf[derived] = c
                        new.add(derived)
                        self.idb[derived] = DerivedAssertion(
                            fact=derived, rule_id=rule.rule_id,
                            premises=tuple(premises), confidence=c,
                            iteration=it, origin="inferred")
            delta = new
        self.iterations = it
        return {"iterations": it, "edb": len(self.edb),
                "derived": len(self.idb), "total_facts": len(all_facts),
                "reached_fixpoint": not delta}

    def _apply_rule(self, rule: Rule, pos: int, didx: Dict[str, Set[Fact]],
                    idx: Dict[str, Set[Fact]], conf: Dict[Fact, float]
                    ) -> Iterable[Tuple[Fact, List[Fact], float]]:
        states: List[Tuple[Dict[str, str], List[Fact]]] = [({}, [])]
        for i, atom in enumerate(rule.body):
            pool = didx.get(atom[0], set()) if i == pos else idx.get(atom[0], set())
            nxt = []
            for b, used in states:
                for fact in pool:
                    nb = _unify(atom, fact, b)
                    if nb is not None:
                        nxt.append((nb, used + [fact]))
            states = nxt
            if not states:
                return
        for b, used in states:
            head = _substitute(rule.head, b)
            if len(set(head[1:])) < len(head[1:]) and \
                    head[0] in ("comparable", "phase_before", "same_metric"):
                continue
            pconf = min([conf.get(f, 1.0) for f in used], default=1.0)
            yield head, used, pconf

    @property
    def facts(self) -> Set[Fact]:
        return set(self.edb) | set(self.idb)

    def query(self, predicate: str, *args: str) -> List[Fact]:
        out = []
        for f in self.facts:
            if f[0] != predicate:
                continue
            if len(args) + 1 > len(f):
                continue
            if all(a == "*" or a == f[i + 1] for i, a in enumerate(args)):
                out.append(f)
        return sorted(out)

    def explain(self, fact: Fact) -> Dict[str, Any]:
        """递归 derivation tree（semantica 只有线性 steps）。"""
        d = self.idb.get(fact)
        if d is None:
            return {"fact": list(fact), "origin": "asserted",
                    "confidence": 1.0, "children": []}
        return {"fact": list(fact), "origin": "inferred",
                "rule_id": d.rule_id, "confidence": round(d.confidence, 4),
                "iteration": d.iteration,
                "children": [self.explain(p) for p in d.premises]}

    def path(self, start: str, end: str, *, max_hops: int = 6
             ) -> Optional[List[Tuple[str, str, str]]]:
        """BFS 最短路径，带 visited 环检测；支持反向边 rel^。"""
        adj: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        for a in self.graph.assertions:
            adj[a.source].append((a.relation, a.target))
            adj[a.target].append((a.relation + "^", a.source))
        q = deque([(start, [])])
        seen = {start}
        while q:
            cur, path = q.popleft()
            if cur == end:
                return path
            if len(path) >= max_hops:
                continue
            for rel, nxt in adj.get(cur, []):
                if nxt not in seen:
                    seen.add(nxt)
                    q.append((nxt, path + [(cur, rel, nxt)]))
        return None

    def consistency(self, *, min_confidence: float = 0.5) -> Dict[str, Any]:
        low = [d.fact for d in self.idb.values() if d.confidence < min_confidence]
        reflexive = [f for f in self.idb if len(f) == 3 and f[1] == f[2]]
        conflicts = []
        for f in self.idb:
            if f[0].startswith("not_"):
                pos = (f[0][4:],) + f[1:]
                if pos in self.facts:
                    conflicts.append({"asserted": list(pos), "negated": list(f)})
        return {"low_confidence": [list(x) for x in low[:20]],
                "reflexive": [list(x) for x in reflexive[:20]],
                "contradictions": conflicts, "iterations": self.iterations,
                "ok": not conflicts and not reflexive}
