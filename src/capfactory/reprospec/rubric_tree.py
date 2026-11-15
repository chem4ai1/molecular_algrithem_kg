"""层次化 rubric 树：把扁平 SAU 挂回「语义层 + reproduction 应用层」骨架。

设计要点：
  - 不新增语义层类；树是 reproduction 任务层派生视图。
  - 复用已有关系当骨架：PROPOSES_METHOD / HAS_MODULE /
    MODULE_IMPLEMENTED_BY / EVALUATED_ON，应用层用 derived_from 反查。
  - 确定性、零 LLM；SAU 的 spec_hash 不受影响（树字段不参与 stable_key）。
  - 叶子仍是原来的 SAU verdict；父节点做加权聚合，支持只重跑失败子树。
"""
from __future__ import annotations
import json, re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SEM = Path("storage_cf/sciforge/batch10_semantic_v4.json")
APP = Path("storage_cf/sciforge/app_reproduction.json")
RUNS = Path("storage_cf/repro_runs")

MODULE_PREFIXES = ("algorithmmodule:", "algorithmstep:")
APP_PREFIXES = ("applb:", "appmetric:", "appcontract:")


def _load(sem_g=None, app_g=None):
    from ..po import POGraph
    return (sem_g if sem_g is not None else POGraph.load(str(SEM)),
            app_g if app_g is not None else (
                POGraph.load(str(APP)) if APP.exists() else POGraph("empty")))


def _node(g: Any, nid: str):
    return g.nodes.get(nid)


def _type(g: Any, nid: str) -> str:
    n = _node(g, nid)
    return n.type if n else ""


def _label(g: Any, nid: str) -> str:
    n = _node(g, nid)
    return (n.label[:60] if n else nid[:60])


def _parents(sem_g: Any, app_g: Any, nid: str) -> Tuple[str, str]:
    """返回 (L1 父 id, L2 父 id)。L1 是 Algorithm/Benchmark，L2 是 Module/契约节点。"""
    if nid.startswith(MODULE_PREFIXES):
        for a in sem_g.incoming(nid, "HAS_MODULE"):
            return a.source, nid
        return "", nid
    if nid.startswith("codefunction:"):
        for a in sem_g.incoming(nid, "MODULE_IMPLEMENTED_BY"):
            mod = a.source
            for b in sem_g.incoming(mod, "HAS_MODULE"):
                return b.source, mod
            return "", mod
        for a in sem_g.incoming(nid, "HAS_FUNCTION"):
            return "", a.source
        return "", ""
    if nid.startswith("benchmark:"):
        return nid, ""
    if nid.startswith("algorithm:"):
        return nid, ""
    if nid.startswith(APP_PREFIXES):
        n = app_g.nodes.get(nid)
        derived = list((n.attrs.get("derived_from") or [])) if n else []
        for d in derived:
            if str(d).startswith("benchmark:"):
                return str(d), ""
        # 兜底：appcontract:benchmark_zinc → benchmark:zinc
        m = re.match(r"app(?:lb|metric|contract):benchmark_([a-z0-9_]+)", nid)
        if m:
            return "benchmark:" + m.group(1), ""
        return "", ""
    return "", ""


def _pick_anchor(src_ids: List[str]) -> str:
    """按优先级挑最能定位父节点的 source_node_id。"""
    for pref in ("codefunction:", "algorithmmodule:", "algorithmstep:"):
        for x in src_ids:
            if str(x).startswith(pref):
                return str(x)
    for pref in ("applb:", "appmetric:", "appcontract:"):
        for x in src_ids:
            if str(x).startswith(pref):
                return str(x)
    for x in reversed(src_ids or []):
        if str(x).startswith(("benchmark:", "algorithm:")):
            return str(x)
    return str(src_ids[-1]) if src_ids else ""


def build_rubric_tree(sau_list: List[Dict[str, Any]], *,
                      sem_g: Any = None, app_g: Any = None,
                      paper_id: str = "", arxiv_id: str = "",
                      spec_hash: str = "") -> Dict[str, Any]:
    """把扁平 SAU 列表挂成层次化树。返回可直接写 RUBRIC_TREE.json 的 dict。"""
    sem_g, app_g = _load(sem_g, app_g)
    root = paper_id or ("paper:" + arxiv_id if arxiv_id else "paper:unknown")
    branches: Dict[str, Dict[str, Any]] = {}
    leaves: List[Dict[str, Any]] = []
    mounted = 0
    for s in sau_list:
        src = [str(x) for x in (s.get("source_node_ids") or [])]
        anchor = _pick_anchor(src)
        l1, l2 = _parents(sem_g, app_g, anchor) if anchor else ("", "")
        if not l1 and not l2:
            l1, l2 = "", ""          # 挂根节点
            parent = root
            path = root
            depth = 1
        elif l1 and l2:
            parent = l2
            path = root + "/" + l1 + "/" + l2
            depth = 3
        else:
            parent = l1
            path = root + "/" + l1
            depth = 2
        g = sem_g if parent in sem_g.nodes else app_g
        bkey = path
        if bkey not in branches:
            branches[bkey] = {
                "path": path, "parent_id": parent,
                "label": _label(g, parent) if parent != root else root,
                "depth": depth - 1, "sau_ids": [], "n_required": 0}
        branches[bkey]["sau_ids"].append(s.get("id"))
        branches[bkey]["n_required"] += 1 if s.get("required", True) else 0
        w = 2.0 if s.get("required", True) else 1.0
        leaves.append({"id": s.get("id"), "kind": s.get("kind"),
                       "parent_id": parent, "path": path, "depth": depth,
                       "weight": w, "required": bool(s.get("required", True))})
        mounted += 1
    return {"paper_id": root, "arxiv_id": arxiv_id, "spec_hash": spec_hash,
            "root": root, "n_leaves": len(sau_list),
            "n_mounted": mounted, "n_unmounted": len(sau_list) - mounted,
            "n_branches": len(branches),
            "depth_max": max((x["depth"] for x in leaves), default=0),
            "branches": sorted(branches.values(), key=lambda x: x["path"]),
            "leaves": leaves}


def tree_score(tree: Dict[str, Any],
               verdicts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """叶子 verdict 沿树加权聚合；输出失败分支供子树重跑。"""
    import collections
    vmap = {str(v.get("sau_id")): v for v in (verdicts or [])}
    by_path: Dict[str, List[Tuple[Dict[str, Any], bool]]] = \
        collections.defaultdict(list)
    for leaf in tree.get("leaves", []):
        v = vmap.get(str(leaf["id"])) or {}
        by_path[leaf["path"]].append((leaf, v.get("verdict") == "aligned"))

    def agg(pairs):
        den = sum(x[0].get("weight", 1.0) for x in pairs)
        num = sum(x[0].get("weight", 1.0) for x in pairs if x[1])
        return round(num / max(den, 1e-9), 4)

    branches = []
    l1: Dict[str, List[float]] = collections.defaultdict(list)
    for path, pairs in sorted(by_path.items()):
        sc = agg(pairs)
        branches.append({"path": path, "score": sc,
                         "n_leaves": len(pairs),
                         "n_aligned": sum(1 for _, ok in pairs if ok),
                         "failed": sc < 1.0})
        parts = path.split("/")
        l1[parts[1] if len(parts) > 1 else tree["root"]].append(sc)
    l1_scores = {k: round(sum(v) / len(v), 4) for k, v in l1.items()}
    all_pairs = [x for v in by_path.values() for x in v]
    return {"root_score": agg(all_pairs),
            "by_l1": l1_scores, "by_branch": branches,
            "failed_branches": [x["path"] for x in branches if x["failed"]],
            "n_leaves": len(all_pairs),
            "n_aligned": sum(1 for _, ok in all_pairs if ok)}


def backfill_all(*, runs: Path = RUNS, persist: bool = True
                 ) -> Dict[str, Any]:
    """对已有 SAU_LIST.json 回填 RUBRIC_TREE.json（+ 树评分）。"""
    from ..po import POGraph
    files = sorted(runs.rglob("SAU_LIST.json"))
    if not files:
        return {"files": 0}
    sem_g, app_g = _load()
    out = []
    for p in files:
        d = p.parent
        sau_doc = json.loads(p.read_text(encoding="utf-8"))
        sau = sau_doc.get("sau") or []
        if not isinstance(sau, list) or not sau:
            continue
        tree = build_rubric_tree(
            sau, sem_g=sem_g, app_g=app_g,
            paper_id=sau_doc.get("paper_id", ""),
            arxiv_id=sau_doc.get("arxiv_id", ""),
            spec_hash=sau_doc.get("spec_hash", ""))
        # 回写 SAU 的树字段到 SAU_LIST（不改 spec_hash 相关字段）
        idx = {x["id"]: x for x in tree["leaves"]}
        for s in sau:
            t = idx.get(s.get("id"))
            if t:
                s.update({"parent_id": t["parent_id"], "path": t["path"],
                          "depth": t["depth"], "weight": t["weight"]})
        row = {"dir": str(d), "arxiv_id": sau_doc.get("arxiv_id", ""),
               "n_leaves": tree["n_leaves"],
               "n_branches": tree["n_branches"],
               "depth_max": tree["depth_max"]}
        vp = d / "SAU_VERDICTS.json"
        if vp.exists():
            try:
                v = json.loads(vp.read_text(encoding="utf-8")).get("verdicts") or []
                sc = tree_score(tree, v)
                row["root_score"] = sc["root_score"]
                row["failed_branches"] = len(sc["failed_branches"])
                if persist:
                    (d / "RUBRIC_TREE_SCORES.json").write_text(
                        json.dumps(sc, ensure_ascii=False, indent=2),
                        encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
        if persist:
            (d / "RUBRIC_TREE.json").write_text(
                json.dumps(tree, ensure_ascii=False, indent=2),
                encoding="utf-8")
            p.write_text(json.dumps(sau_doc, ensure_ascii=False, indent=2),
                         encoding="utf-8")
        out.append(row)
    return {"files": len(out), "rows": out,
            "total_leaves": sum(x["n_leaves"] for x in out)}


if __name__ == "__main__":
    print(json.dumps(backfill_all(), ensure_ascii=False, indent=2))


def attach_to_final_evaluation(*, runs: Path = RUNS,
                               persist: bool = True) -> Dict[str, Any]:
    """把树评分以 ``rubric_tree`` 字段并入 FINAL_EVALUATION.json。
    只新增字段，不改原有 evaluation / align_rubric / anchors 结构。
    """
    out = []
    for sp in sorted(runs.rglob("RUBRIC_TREE_SCORES.json")):
        f = sp.parent / "FINAL_EVALUATION.json"
        if not f.exists():
            continue
        try:
            sc = json.loads(sp.read_text(encoding="utf-8"))
            doc = json.loads(f.read_text(encoding="utf-8"))
            doc["rubric_tree"] = {
                "root_score": sc["root_score"],
                "by_l1": sc["by_l1"],
                "failed_branches": sc["failed_branches"],
                "n_leaves": sc["n_leaves"],
                "n_aligned": sc["n_aligned"]}
            if persist:
                f.write_text(json.dumps(doc, ensure_ascii=False, indent=2),
                             encoding="utf-8")
            out.append(str(f))
        except Exception:  # noqa: BLE001
            pass
    return {"updated": len(out), "files": out}
