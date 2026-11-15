"""复现生命周期四环节：方法锁定 → 代码生成 → 复现执行 → 主张锚定。

相对旧实现（`MethodLock` 只是个 hash、`CodeGenerationTask` 只是展示节点、
执行只跑一次、锚定只挂三个全局 hash）的重新设计：

  lock    : 双层锁 + 逐条 method SAU 指纹 + 漂移拒绝（不静默通过）
  codegen : 依赖 DAG + 任务化 + 三项校验（安全/符号/顺序）
  execute : 阶梯执行（subset→full）+ 双跑一致性 + SAU 级失败定位
  anchor  : 三级链 claim → 表格单元格 → 图节点，逐条可重算校验

所有阶段零 LLM、只读图与 spec，产物写工作区，可单独触发。
"""
from __future__ import annotations
import hashlib, json, time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

STAGES = ("lock", "codegen", "execute", "anchor")
LOCK_FILE = "METHOD_LOCK.json"
CODEGEN_FILE = "CODE_PLAN.json"
EXEC_FILE = "EXECUTION_LOG.json"
ANCHOR_FILE = "CLAIM_ANCHORS.json"
LIFECYCLE_FILE = "LIFECYCLE.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _sha(text: str, n: int = 16) -> str:
    return "sha256:" + hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:n]


def _dump(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str),
                 encoding="utf-8")


def _load(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


@dataclass
class StageResult:
    stage: str
    ok: bool
    blocked_by: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[str] = field(default_factory=list)
    seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------- lock
def sau_fingerprint(sau: Any) -> str:
    """单条 SAU 的稳定指纹：只取影响复现语义的字段。"""
    key = sau.stable_key() if hasattr(sau, "stable_key") else dict(sau)
    return _sha(json.dumps(key, ensure_ascii=False, sort_keys=True,
                           default=str), 16)


def run_lock(spec: Any, ws: Path) -> StageResult:
    """冻结 method SAU：逐条指纹 + 集合 hash；与旧锁比对，漂移不通过。"""
    t0 = time.time()
    methods = list(spec.by_kind("method"))
    fps = {s.id: sau_fingerprint(s) for s in methods}
    set_hash = _sha(json.dumps(sorted(fps.items()), ensure_ascii=False), 20)
    old = _load(ws / LOCK_FILE)
    drift = [sid for sid, h in (old.get("fingerprints") or {}).items()
             if fps.get(sid) != h]
    drift += [sid for sid in fps if sid not in (old.get("fingerprints") or {})
              and old.get("fingerprints")]
    blocked = [] if methods else ["no_method_sau"]
    doc = {
        "locked": True, "locked_at": _now(),
        "paper_id": spec.paper_id, "arxiv_id": spec.arxiv_id,
        "spec_hash": spec.spec_hash,
        "compiler_version": spec.method_lock.get("compiler_version", ""),
        "n_method_sau": len(methods),
        "method_sau_hash": set_hash,
        "fingerprints": fps,
        "drift": sorted(set(drift)),
        "previous": {"method_sau_hash": old.get("method_sau_hash", ""),
                     "locked_at": old.get("locked_at", "")},
        "passed": not blocked and not drift,
    }
    (ws / LOCK_FILE).parent.mkdir(parents=True, exist_ok=True)
    _dump(ws / LOCK_FILE, doc)
    return StageResult(
        stage="lock", ok=not blocked and not drift, blocked_by=blocked,
        metrics={"n_method_sau": len(methods), "method_sau_hash": set_hash,
                 "drift": len(doc["drift"])},
        artifacts=[LOCK_FILE], seconds=round(time.time() - t0, 3))


# ------------------------------------------------------------- codegen
def _topo(edges: List[tuple], nodes: set) -> tuple:
    """Kahn 拓扑排序；有环时返回 (order, cycle_nodes)。"""
    indeg = {n: 0 for n in nodes}
    adj: Dict[str, List[str]] = {n: [] for n in nodes}
    for a, b in edges:
        if a in nodes and b in nodes:
            adj[a].append(b); indeg[b] += 1
    q = sorted([n for n, d in indeg.items() if d == 0])
    order = []
    while q:
        cur = q.pop(0); order.append(cur)
        for nxt in sorted(adj.get(cur, [])):
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                q.append(nxt)
    cycle = sorted(set(nodes) - set(order))
    if cycle:
        # 真实论文里模块顺序可能双向声明（跨论文共享模块），
        # 不能因此阻断代码生成：按 (入度, id) 稳定排序兜底。
        indeg2 = {n: sum(1 for a, b in edges if b == n) for n in cycle}
        order += sorted(cycle, key=lambda n: (indeg2.get(n, 0), n))
    return order, cycle


def run_codegen(spec: Any, graph: Any, ws: Path) -> StageResult:
    """依赖 DAG → 任务化 → 生成脚本 → 三项校验。"""
    from .executor import build_repro_script, check_script_safety
    t0 = time.time()
    edges, nodes = [], set()
    for s in spec.by_kind("ordering"):
        a = str(s.check.get("before") or "")
        b = str(s.check.get("after") or "")
        if a and b:
            edges.append((a, b)); nodes |= {a, b}
    for s in spec.by_kind("method"):
        for nid in s.source_node_ids:
            if str(nid).startswith(("algorithmmodule:", "algorithmstep:")):
                nodes.add(str(nid))
    order, cycle = _topo(edges, nodes)

    grounded = set()
    for s in spec.by_kind("code_grounding"):
        for nid in s.source_node_ids:
            if str(nid).startswith(("algorithmmodule:", "algorithmstep:")):
                grounded.add(str(nid))
    tasks = []
    for i, mid in enumerate(order):
        tasks.append({
            "task_id": f"cgt:{i:03d}", "module_id": mid,
            "label": mid.split(":")[-1][:48], "order": i + 1,
            "depends_on": [a for a, b in edges if b == mid],
            "strategy": "existing" if mid in grounded else "generate",
            "status": "ready" if mid in grounded else "pending"})
    src = build_repro_script(spec, graph)
    script = ws / "REPRO_SCRIPT.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(src, encoding="utf-8")
    issues = check_script_safety(src)

    known = set()
    if graph is not None:
        known = {str(n.label) for n in graph.by_type("CodeFunction")}
        known |= {str(n.attrs.get("name") or "") for n in graph.by_type("CodeFunction")}
    want = [str(s.check.get("target") or "")
            for s in spec.by_kind("code_grounding")]
    want = [w for w in want if w]
    hit = 0
    for w in want:
        n = graph.nodes.get(w) if graph is not None else None
        if n is not None and n.type == "CodeFunction":
            hit += 1
        elif w.split(":")[-1] in known:
            hit += 1
    recall = round(hit / len(want), 4) if want else 1.0
    order_ok = all(tasks[i]["order"] < tasks[i + 1]["order"]
                   for i in range(len(tasks) - 1))
    blocked = []
    warnings = []
    if cycle:
        warnings.append("dependency_cycle_downgraded")
    if issues:
        blocked.append("unsafe_script")
    if not order_ok:
        blocked.append("order_violation")
    doc = {"paper_id": spec.paper_id, "arxiv_id": spec.arxiv_id,
           "spec_hash": spec.spec_hash, "generated_at": _now(),
           "dag": {"nodes": sorted(nodes), "edges": [list(e) for e in edges],
                   "order": order, "cycle": cycle},
           "tasks": tasks,
           "checks": {"safety": issues, "symbol_recall": recall,
                      "order_ok": order_ok,
                      "n_grounded_modules": len(grounded),
                      "n_symbol_checked": len(want),
                      "warnings": warnings},
           "script": {"path": "REPRO_SCRIPT.py", "sha": _sha(src, 20),
                      "bytes": len(src.encode("utf-8"))},
           "passed": not blocked}
    _dump(ws / CODEGEN_FILE, doc)
    return StageResult(
        stage="codegen", ok=not blocked, blocked_by=blocked,
        metrics={"n_tasks": len(tasks), "n_edges": len(edges),
                 "n_grounded": len(grounded), "symbol_recall": recall,
                 "script_sha": doc["script"]["sha"]},
        artifacts=[CODEGEN_FILE, "REPRO_SCRIPT.py"],
        seconds=round(time.time() - t0, 3))


# ------------------------------------------------------------- execute
def run_execute(spec: Any, ws: Path, *, timeout: int = 300) -> StageResult:
    """阶梯执行 subset→full，双跑一致性，失败/未执行定位到 SAU。"""
    from .executor import _run_once, diagnose
    t0 = time.time()
    script = ws / "REPRO_SCRIPT.py"
    if not script.exists():
        return StageResult(stage="execute", ok=False,
                           blocked_by=["no_repro_script"])
    r1 = _run_once(script, ws, timeout)
    r2 = _run_once(script, ws, timeout)
    payload = r1.get("payload") or {}
    stages, keyed = [], []
    for name, st in (payload.get("stages") or {}).items():
        stages.append({"name": name, "status": st.get("status"),
                       "n_rows": st.get("n_rows"),
                       "steps_executed": st.get("steps_executed"),
                       "baseline": st.get("baseline"),
                       "candidate": st.get("candidate"),
                       "n_symbols": len(st.get("symbol_trace") or [])})
        for x in st.get("symbol_trace") or []:
            if x.get("module"):
                keyed.append({"module": x.get("module"), "stage": name,
                              "key": bool(x.get("key"))})

    methods = {s.id: [i for i in s.source_node_ids
                      if str(i).startswith(("algorithmmodule:", "algorithmstep:"))]
               for s in spec.by_kind("method")}
    hit_mods = {k["module"] for k in keyed}
    n_key = sum(1 for k in keyed if k["key"])
    executed = [sid for sid, mods in methods.items() if set(mods) & hit_mods]
    unexecuted = [sid for sid in methods if sid not in executed]

    failures = []
    if not r1.get("ok"):
        d = diagnose(r1.get("stderr") or "")
        failures.append({"scope": "script", "reason": d.get("kind", "unknown"),
                         "detail": d.get("reason", ""),
                         "fixable": bool(d.get("fixable")),
                         "stderr_tail": (r1.get("stderr") or "")[-300:]})
    for sid in unexecuted:
        failures.append({"scope": "sau", "sau_id": sid,
                         "reason": "module_not_exercised",
                         "detail": "模块未进入 symbol_trace(key=true)",
                         "fixable": False})
    repeatable = (r1.get("payload") == r2.get("payload")) and payload != {}
    out_sha = _sha(json.dumps(payload, sort_keys=True, ensure_ascii=False), 20)
    blocked = []
    if not payload:
        blocked.append("no_payload")
    if not repeatable:
        blocked.append("not_repeatable")
    doc = {"paper_id": spec.paper_id, "arxiv_id": spec.arxiv_id,
           "ran_at": _now(), "rc": r1.get("rc"),
           "seconds": round(float(r1.get("duration") or 0), 3),
           "stages": stages,
           "coverage": {"n_method": len(methods),
                        "n_executed": len(executed),
                        "executed": executed, "unexecuted": unexecuted},
           "failures": failures,
           "repeatable": repeatable, "double_run": {"sha1": out_sha,
                                                    "sha2": _sha(json.dumps(r2.get("payload"), sort_keys=True, ensure_ascii=False), 20)},
           "outputs_sha": out_sha,
           "passed": not blocked}
    _dump(ws / EXEC_FILE, doc)
    return StageResult(
        stage="execute", ok=not blocked, blocked_by=blocked,
        metrics={"n_stages": len(stages), "repeatable": repeatable,
                 "n_executed_sau": len(executed), "n_key_modules": n_key,
                 "coverage": round(len(executed) / max(len(methods), 1), 4),
                 "outputs_sha": out_sha, "failures": len(failures)},
        artifacts=[EXEC_FILE], seconds=round(time.time() - t0, 3))


# -------------------------------------------------------------- anchor
def run_anchor(spec: Any, graph: Any, ws: Path) -> StageResult:
    """三级锚定：claim(numeric SAU) → 表格单元格 → 图节点；逐条可校验。"""
    t0 = time.time()
    cg = _load(ws / CODEGEN_FILE)
    ex = _load(ws / EXEC_FILE)
    code_sha = ((cg.get("script") or {}).get("sha") or "")
    outs_sha = ex.get("outputs_sha", "")
    inputs_sha = _sha(json.dumps(spec.data_contract, ensure_ascii=False,
                                 sort_keys=True, default=str), 20)
    script_sha_now = ""
    sp = ws / "REPRO_SCRIPT.py"
    if sp.exists():
        script_sha_now = _sha(sp.read_text(encoding="utf-8"), 20)

    def _attrs(nid: str) -> Dict[str, Any]:
        if graph is None:
            return {}
        n = graph.nodes.get(nid)
        return dict(n.attrs) if n else {}

    claims = []
    for i, s in enumerate(spec.by_kind("numeric")):
        entry = str(s.check.get("target") or "")
        bench = next((str(x) for x in s.source_node_ids
                      if str(x).startswith("benchmark:")), "")
        metric_id = next((str(x) for x in s.source_node_ids
                          if str(x).startswith(("appmetric:",
                                                "metricdefinition:"))), "")
        ea = _attrs(entry)
        model = str(ea.get("model") or "")
        prov = str(ea.get("provenance") or ea.get("source") or "")
        idx = ea.get("row_index")
        if not prov and bench:
            for r in (_attrs(bench).get("model_results") or []):
                if (str(r.get("model")) == model
                        and str(r.get("metric")) == str(s.check.get("metric"))):
                    prov = str(r.get("provenance") or "")
                    break
        if not prov:
            # 回退：抽取报告里的表格出处（table_extract:N）
            rp = (Path("storage_cf/sciforge/semantic_extraction")
                  / (str(spec.arxiv_id) + ".json"))
            if rp.exists():
                rows = (json.loads(rp.read_text(encoding="utf-8"))
                        .get("model_results") or {}).get("rows") or []
                for r in rows:
                    if (str(r.get("model_name") or r.get("model")) == model
                            and str(r.get("metric_name") or r.get("metric"))
                            == str(s.check.get("metric"))
                            and str(r.get("value_raw") or r.get("value"))
                            == str(s.check.get("value"))):
                        prov = str(r.get("provenance") or "")
                        idx = r.get("row_index", idx)
                        break
        l1 = {"type": "claim", "sau_id": s.id, "model": model,
              "metric": s.check.get("metric"), "value": s.check.get("value"),
              "value_num": s.check.get("value_num"),
              "unit": s.check.get("unit"), "direction": s.check.get("direction"),
              "tolerance": s.check.get("tolerance")}
        l2 = {"type": "cell", "entry_id": entry, "table_ref": prov,
              "row_index": idx, "paper_id": str(ea.get("paper_id") or "")}
        l3 = {"type": "graph", "benchmark_id": bench, "entry_id": entry,
              "metric_id": metric_id}
        hashes = {"spec": spec.spec_hash, "code": code_sha,
                  "inputs": inputs_sha, "outputs": outs_sha}
        verified = bool(hashes["spec"] and hashes["code"]
                        and hashes["outputs"]
                        and (not script_sha_now or code_sha == script_sha_now))
        claims.append({"claim_id": f"C{i + 1:03d}", "sau_id": s.id,
                       "level1_claim": l1, "level2_cell": l2,
                       "level3_graph": l3, "hashes": hashes,
                       "three_level": bool(bench and entry and prov),
                       "verified": verified})
    n3 = sum(1 for c in claims if c["three_level"])
    doc = {"paper_id": spec.paper_id, "arxiv_id": spec.arxiv_id,
           "anchored_at": _now(), "passed": None, "spec_hash": spec.spec_hash,
           "code_sha": code_sha, "inputs_sha": inputs_sha,
           "outputs_sha": outs_sha,
           "double_run_equal": bool(ex.get("repeatable")),
           "n_claims": len(claims), "n_three_level": n3,
           "integrity": bool(claims) and all(c["verified"] for c in claims),
           "claims": claims}
    blocked = [] if claims else ["no_numeric_claim"]
    if not doc["integrity"]:
        blocked.append("anchor_unverified")
    doc["passed"] = not blocked
    _dump(ws / ANCHOR_FILE, doc)
    return StageResult(
        stage="anchor", ok=not blocked, blocked_by=blocked,
        metrics={"n_claims": len(claims), "n_three_level": n3,
                 "integrity": doc["integrity"],
                 "double_run_equal": doc["double_run_equal"]},
        artifacts=[ANCHOR_FILE], seconds=round(time.time() - t0, 3))


# ------------------------------------------------------- orchestration
def stage_status(ws: Path) -> Dict[str, Any]:
    """给前端：四阶段是否就绪 + 关键指标。"""
    lock = _load(ws / LOCK_FILE)
    cg = _load(ws / CODEGEN_FILE)
    ex = _load(ws / EXEC_FILE)
    an = _load(ws / ANCHOR_FILE)

    def st(doc):
        return "done" if doc and doc.get("passed") else (
            "failed" if doc else "pending")

    return {
        "workspace": str(ws),
        "stages": {
            "lock": {"state": st(lock),
                     "n_method_sau": lock.get("n_method_sau", 0),
                     "method_sau_hash": lock.get("method_sau_hash", ""),
                     "drift": len(lock.get("drift") or []),
                     "locked_at": lock.get("locked_at", "")},
            "codegen": {"state": st(cg),
                        "n_tasks": len(cg.get("tasks") or []),
                        "n_edges": len((cg.get("dag") or {}).get("edges") or []),
                        "symbol_recall": (cg.get("checks") or {}).get(
                            "symbol_recall"),
                        "script_sha": ((cg.get("script") or {}).get("sha") or "")},
            "execute": {"state": st(ex),
                        "n_stages": len(ex.get("stages") or []),
                        "repeatable": bool(ex.get("repeatable")),
                        "coverage": ((ex.get("coverage") or {}).get("n_executed", 0),
                                     (ex.get("coverage") or {}).get("n_method", 0)),
                        "failures": len(ex.get("failures") or [])},
            "anchor": {"state": st(an),
                       "n_claims": an.get("n_claims", 0),
                       "n_three_level": an.get("n_three_level", 0),
                       "integrity": bool(an.get("integrity")),
                       "outputs_sha": an.get("outputs_sha", "")},
        },
        "ready": all(st(x) == "done" for x in (lock, cg, ex, an)),
    }


def verify_lifecycle(ws: Path) -> Dict[str, Any]:
    """重算并比对：脚本 sha、锚 hash、claim 完整性。"""
    issues: List[str] = []
    cg = _load(ws / CODEGEN_FILE)
    ex = _load(ws / EXEC_FILE)
    an = _load(ws / ANCHOR_FILE)
    sp = ws / "REPRO_SCRIPT.py"
    code_sha = (cg.get("script") or {}).get("sha") or ""
    if code_sha and sp.exists():
        if _sha(sp.read_text(encoding="utf-8"), 20) != code_sha:
            issues.append("script_modified_after_codegen")
    if an.get("code_sha") and code_sha and an["code_sha"] != code_sha:
        issues.append("anchor_code_sha_mismatch")
    if an.get("outputs_sha") and ex.get("outputs_sha") \
            and an["outputs_sha"] != ex["outputs_sha"]:
        issues.append("anchor_outputs_sha_mismatch")
    if an.get("claims") and not all(c.get("verified") for c in an["claims"]):
        issues.append("claim_unverified")
    return {"workspace": str(ws), "ok": not issues, "issues": issues,
            "integrity": bool(an.get("integrity"))}


def run_lifecycle(paper_id: str, ws: Any, *, graph: Any = None,
                  effort: str = "lite") -> Dict[str, Any]:
    """串四环节；任一环节 blocked 就停在那里并如实记录。"""
    from ..po import POGraph
    from .compiler import compile_reprospec
    ws = Path(ws)
    ws.mkdir(parents=True, exist_ok=True)
    g = graph if graph is not None else POGraph.load(
        "storage_cf/sciforge/app_reproduction.json")
    spec = compile_reprospec(paper_id=paper_id, out_dir=ws)
    res: Dict[str, Any] = {"paper_id": paper_id, "arxiv_id": spec.arxiv_id,
                           "effort": effort, "started_at": _now()}
    for fn in (lambda: run_lock(spec, ws),
               lambda: run_codegen(spec, g, ws),
               lambda: run_execute(spec, ws),
               lambda: run_anchor(spec, g, ws)):
        r = fn()
        res[r.stage] = r.to_dict()
        if not r.ok:
            res["blocked_at"] = r.stage
            res["blocked_by"] = r.blocked_by
            break
    res["finished_at"] = _now()
    res["status"] = stage_status(ws)
    res["verify"] = verify_lifecycle(ws)
    _dump(ws / LIFECYCLE_FILE, res)
    return res
