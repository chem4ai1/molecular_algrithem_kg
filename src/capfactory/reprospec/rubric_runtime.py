"""把 RUBRIC_TREE.json 编译进单篇 app_repro_runtime.json。

- 每个 rubric 分支 → 一个 RubricNode(node_role=branch)
- 每条 SAU       → 一个 RubricNode(node_role=leaf)
- branch -HAS_SAU-> leaf
- 分支之间的父子关系用 parent_id 属性表达，不新增关系类型
- 只改单篇运行时图；app_reproduction.json / 语义层图均不触碰
- 幂等：重跑先清掉旧的 RubricNode 与 HAS_SAU 边
"""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any, Dict

RUNS = Path("storage_cf/repro_runs")


def _key(s: str) -> str:
    return hashlib.md5(str(s).encode("utf-8")).hexdigest()[:10]


def _run_id(g: Any) -> str:
    for n in g.nodes.values():
        r = n.attrs.get("run_id")
        if r:
            return str(r)
    return "rubric"


def attach(run_dir: Path, *, persist: bool = True) -> Dict[str, Any]:
    from ..po import POGraph
    d = Path(run_dir)
    tf, rf = d / "RUBRIC_TREE.json", d / "app_repro_runtime.json"
    if not tf.exists() or not rf.exists():
        return {"skipped": True, "reason": "missing_tree_or_runtime",
                "dir": str(d)}
    tree = json.loads(tf.read_text(encoding="utf-8"))
    g = POGraph.from_dict(json.loads(rf.read_text(encoding="utf-8")))
    sf = d / "RUBRIC_TREE_SCORES.json"
    scores = {}
    if sf.exists():
        try:
            scores = {x["path"]: x["score"] for x in
                      json.loads(sf.read_text(encoding="utf-8"))
                      .get("by_branch", [])}
        except Exception:  # noqa: BLE001
            pass
    # ---- 幂等清理 ----
    g.nodes = {k: v for k, v in g.nodes.items()
               if v.type != "RubricNode"}
    g.assertions = [a for a in g.assertions if a.relation != "HAS_SAU"]
    g._keys = {(a.source, a.target, a.relation) for a in g.assertions}
    rid = _run_id(g)
    base = f"reprorun:{rid}:rubric"
    common = {"layer": "application", "task": "reproduction",
              "miner": "repro_runtime", "producer": "rubric_tree",
              "run_id": rid,
              "derived_from": [tree.get("root", "")],
              "spec_hash": tree.get("spec_hash", "")}

    root_id = base + ":root"
    g.node(root_id, "RubricNode", "Rubric 根",
           node_role="root", path=tree.get("root", ""), depth=0,
           parent_id="", n_leaves=tree.get("n_leaves", 0),
           score=(json.loads(sf.read_text(encoding="utf-8"))["root_score"]
                  if sf.exists() else None), **common)
    # ---- 分支节点 ----
    branch_ids: Dict[str, str] = {}
    for b in tree.get("branches", []):
        bid = base + ":b:" + _key(b["path"])
        parent = root_id
        parts = str(b["path"]).split("/")
        if len(parts) > 2:
            parent = branch_ids.get("/".join(parts[:2]) + "/" + parts[2]
                                    if len(parts) > 3 else root_id, root_id)
        g.node(bid, "RubricNode", b.get("label", b["path"])[:80],
               node_role="branch", path=b["path"], depth=b.get("depth", 1),
               parent_id=b.get("parent_id", ""),
               n_leaves=len(b.get("sau_ids") or []),
               score=scores.get(b["path"]), **common)
        branch_ids[b["path"]] = bid
    # ---- 叶子节点 + HAS_SAU ----
    n_edges = 0
    for lf in tree.get("leaves", []):
        lid = base + ":l:" + _key(lf["id"])
        g.node(lid, "RubricNode", str(lf["id"])[-48:],
               node_role="leaf", path=lf.get("path", ""),
               depth=lf.get("depth", 3), parent_id=lf.get("parent_id", ""),
               sau_id=lf.get("id", ""), kind=lf.get("kind", ""),
               required=bool(lf.get("required", True)),
               weight=lf.get("weight", 1.0), **common)
        bid = branch_ids.get(lf.get("path", ""), root_id)
        if g.assert_rel(bid, lid, "HAS_SAU",
                        layer="application", task="reproduction"):
            n_edges += 1
    out = {"dir": str(d), "run_id": rid,
           "n_branch_nodes": len(branch_ids) + 1,
           "n_leaf_nodes": len(tree.get("leaves", [])),
           "n_has_sau": n_edges,
           "n_nodes": len(g.nodes), "n_assertions": len(g.assertions)}
    if persist:
        rf.write_text(json.dumps(g.to_dict(), ensure_ascii=False, indent=2),
                      encoding="utf-8")
        out["path"] = str(rf)
    return out


def attach_all(*, runs: Path = RUNS, persist: bool = True) -> Dict[str, Any]:
    rows = []
    for tf in sorted(runs.rglob("RUBRIC_TREE.json")):
        r = attach(tf.parent, persist=persist)
        if not r.get("skipped"):
            rows.append(r)
    return {"runs": len(rows),
            "total_branch_nodes": sum(x["n_branch_nodes"] for x in rows),
            "total_leaf_nodes": sum(x["n_leaf_nodes"] for x in rows),
            "total_has_sau": sum(x["n_has_sau"] for x in rows),
            "rows": rows}


if __name__ == "__main__":
    print(json.dumps(attach_all(), ensure_ascii=False, indent=2))
