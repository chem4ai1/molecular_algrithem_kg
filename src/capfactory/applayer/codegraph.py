"""把 codescan 的结果写入图：CodeUnit / CodeSymbol / Dependency / EntryPoint / TestUnit / EnvSpec。"""
from __future__ import annotations
from typing import Any, Dict

ATTR_DROP = {"id", "unit", "bases"}


def build_code_graph(graph: Any, scan: Dict[str, Any], *,
                     env_id: str | None = None) -> Dict[str, int]:
    """幂等写入：同 id 只更新属性，不重复建节点。"""
    rid = scan.get("repo_id") or "repo"
    n = {"units": 0, "symbols": 0, "deps": 0, "entries": 0, "tests": 0,
         "relations": 0}

    def node(nid, typ, label, **attrs):
        attrs = {k: v for k, v in attrs.items() if v not in (None, "", [])
                 and k not in ATTR_DROP}
        if nid in graph.nodes:
            for k, v in attrs.items():
                graph.nodes[nid].attrs[k] = v
            return False
        graph.node(nid, typ, str(label)[:80], layer="application", task="code",
                   repo=rid, **attrs)
        return True

    def rel(a, b, r):
        if a in graph.nodes and b in graph.nodes:
            graph.assert_rel(a, b, r, layer="application")
            n["relations"] += 1

    for u in scan.get("units", []):
        if node(u["id"], "CodeUnit", u["path"], **u):
            n["units"] += 1
    for s in scan.get("symbols", []):
        if node(s["id"], "CodeSymbol", s.get("qualname") or s["name"], **s):
            n["symbols"] += 1
        rel(s.get("unit", ""), s["id"], "CONTAINS")
        for base in s.get("bases") or []:
            for other in scan.get("symbols", []):
                if other.get("kind") == "class" and other.get("name") == base:
                    rel(s["id"], other["id"], "INHERITS")
    for d in scan.get("deps", []):
        if node(d["id"], "Dependency", d["name"], **d):
            n["deps"] += 1
        if d.get("declared_in"):
            uid = f"codeunit:{rid}:{d['declared_in'].replace('/', '_').replace('.', '_')}"
            for u in scan.get("units", []):
                if u["path"] == d["declared_in"]:
                    rel(u["id"], d["id"], "DEPENDS_ON")
    eid = env_id or f"env:{rid}"
    if node(eid, "EnvSpec", f"{rid} env", **(scan.get("env") or {})):
        pass
    for e in scan.get("entries", []):
        if node(e["id"], "EntryPoint", e["path"], **e):
            n["entries"] += 1
        for u in scan.get("units", []):
            if u["path"] == e["path"]:
                rel(e["id"], u["id"], "IN_UNIT")
        rel(e["id"], eid, "USES_ENV")
    for t in scan.get("tests", []):
        if node(t["id"], "TestUnit", t["name"], **t):
            n["tests"] += 1
        for u in scan.get("units", []):
            if u["path"] == t["path"]:
                rel(t["id"], u["id"], "TEST_IN")
    return n
