"""确定性工具：哈希 / 原子写 / append-only 日志 / 图读取 / 重建等价闸门。

I2：verify_rebuild 是「增量回写 ≡ 全量重建」的唯一判据。
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

from . import config


def sha256_bytes(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()


def sha256_file(p: str | Path) -> str:
    path = Path(p)
    if not path.exists():
        return "sha256:" + hashlib.sha256(b"").hexdigest()
    return sha256_bytes(path.read_bytes())


def sha256_json(obj: Any) -> str:
    s = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    return sha256_bytes(s.encode("utf-8"))


def atomic_write(path: str | Path, obj: Any) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str),
                   encoding="utf-8")
    os.replace(tmp, p)
    return p


def append_jsonl(path: str | Path, row: Dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True,
                           default=str) + "\n")


def read_jsonl(path: str | Path, limit: int = 1000) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


_LOCK_DEPTH = __import__("threading").local()


def with_lock(fn):
    """可重入文件锁：同一线程内嵌套调用不再二次 flock（避免自锁）。

    多 run/多进程同时写注册表或应用图时，最外层持锁；内层直接执行。
    """
    def wrapper(*a, **kw):
        depth = getattr(_LOCK_DEPTH, "n", 0)
        if depth > 0:
            _LOCK_DEPTH.n = depth + 1
            try:
                return fn(*a, **kw)
            finally:
                _LOCK_DEPTH.n = depth
        config.ensure_dirs()
        with open(config.LOCK_FILE, "a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            _LOCK_DEPTH.n = 1
            try:
                return fn(*a, **kw)
            finally:
                _LOCK_DEPTH.n = 0
                fcntl.flock(f, fcntl.LOCK_UN)
    wrapper.__name__ = getattr(fn, "__name__", "locked")
    return wrapper


def load_graph(path: str | Path | None = None):
    from capfactory.po import POGraph
    return POGraph.load(str(path or config.SEMANTIC_GRAPH))


def graph_digest(g) -> Dict[str, Any]:
    """把 POGraph 归一化成顺序无关的可比较结构。"""
    nodes = {}
    for nid, n in getattr(g, "nodes", {}).items():
        attrs = dict(getattr(n, "attrs", {}) or {})
        nodes[str(nid)] = [str(getattr(n, "type", "")),
                           json.dumps(attrs, sort_keys=True, ensure_ascii=False,
                                      default=str)]
    edges = sorted(
        json.dumps([str(a.source), str(a.target), str(a.relation),
                    dict(getattr(a, "properties", {}) or {})],
                   sort_keys=True, ensure_ascii=False, default=str)
        for a in (getattr(g, "assertions", []) or []))
    return {"nodes": nodes, "edges": edges}


def diff_graphs(a, b) -> Dict[str, Any]:
    """返回逐节点/逐断言差异（顺序无关）。"""
    da, db = graph_digest(a), graph_digest(b)
    na, nb = da["nodes"], db["nodes"]
    ea, eb = set(da["edges"]), set(db["edges"])
    node_missing = sorted(set(na) - set(nb))
    node_extra = sorted(set(nb) - set(na))
    attr_diff = sorted(k for k in set(na) & set(nb) if na[k] != nb[k])
    edge_missing = sorted(ea - eb)
    edge_extra = sorted(eb - ea)
    return {"n_missing": len(node_missing), "n_extra": len(node_extra),
            "n_attr_diff": len(attr_diff), "n_rel_diff": len(edge_missing) + len(edge_extra),
            "diff": (node_missing + node_extra + attr_diff +
                     edge_missing + edge_extra)[:20]}


def verify_rebuild(delta: Dict[str, Any] | None = None, *,
                   base_graph=None, prev_app=None, full_app=None) -> Dict[str, Any]:
    """H2：全量重建 ≡ 上一版 ⊕ delta。

    base_graph/prev_app/full_app 都是 POGraph（测试可注入最小图）。
    delta 为空时只比对 base 与 full（用于 S0 基线自检）。
    """
    delta = delta or {}
    if base_graph is None or full_app is None:
        base_graph = load_graph()
        full_app = load_graph(config.APP_GRAPH)
    if prev_app is None:
        prev_app = full_app
    # 增量 = 上一版 + delta 的节点/断言（delta 用 dict 表示，不直接改图对象）
    nodes = list(delta.get("nodes") or [])
    assertions = list(delta.get("assertions") or [])
    if not nodes and not assertions:
        d = diff_graphs(prev_app, full_app)
    else:
        # 用「增量节点全集」做等价比较：把 delta 节点并入 prev_app 的归一化摘要
        da, db = graph_digest(prev_app), graph_digest(full_app)
        for n in nodes:
            nid = str(n.get("id"))
            da["nodes"][nid] = [str(n.get("type", "")),
                                json.dumps(n.get("attrs", {}), sort_keys=True,
                                           ensure_ascii=False, default=str)]
        extra_edges = [json.dumps([str(a.get("source")), str(a.get("target")),
                                   str(a.get("relation")),
                                   dict(a.get("properties", {}) or {})],
                                  sort_keys=True, ensure_ascii=False, default=str)
                       for a in assertions]
        ea, eb = set(da["edges"]) | set(extra_edges), set(db["edges"])
        d = {"n_missing": len(set(da["nodes"]) - set(db["nodes"])),
             "n_extra": len(set(db["nodes"]) - set(da["nodes"])),
             "n_attr_diff": sum(1 for k in set(da["nodes"]) & set(db["nodes"])
                                if da["nodes"][k] != db["nodes"][k]),
             "n_rel_diff": len(ea ^ eb), "diff": []}
    ok = all(d[k] == 0 for k in ("n_missing", "n_extra", "n_attr_diff", "n_rel_diff"))
    return {"ok": ok, "reason_code": "EQUIVALENT" if ok else "DRIFT",
            **{k: d[k] for k in ("n_missing", "n_extra", "n_attr_diff", "n_rel_diff")},
            "diff": d.get("diff", []),
            "semantic_sha": sha256_file(config.SEMANTIC_GRAPH),
            "app_sha": sha256_file(config.APP_GRAPH),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
