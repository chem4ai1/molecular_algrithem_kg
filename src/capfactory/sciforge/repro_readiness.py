"""把多阶段抽取结果接进代码复现，量化「抽取 → 复现」的实际增益。"""
from __future__ import annotations
import json, time
from pathlib import Path
from typing import Any, Dict

from ..po import POGraph
from .reproflow import ReproductionFlow


def load_extraction(extraction_dir: str | Path) -> Dict[str, Any]:
    d = Path(extraction_dir)
    def rd(name: str) -> Dict[str, Any]:
        p = d / name
        if not p.exists():
            return {}
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    return {"method": rd("STAGE2_method.json"),
            "benchmark": rd("STAGE2_benchmark.json"),
            "related_work": rd("STAGE2_related_work.json"),
            "plan": rd("STAGE0_HEADING_PLAN.json")}


def to_modules(method: Dict[str, Any]) -> list:
    """抽取的 algorithm steps → MethodLock 模块清单。"""
    out = []
    for s in method.get("steps") or []:
        if not isinstance(s, dict) or not s.get("name"):
            continue
        out.append({"module_name": str(s["name"]),
                    "mechanism": str(s.get("mechanism") or ""),
                    "inputs": ["h_i", "x_i"], "outputs": ["h_i'", "x_i'"]})
    return out


def symbol_coverage(symbols: list, repo: str) -> Dict[str, Any]:
    from .tentacle import _ast_functions
    ast_syms = {f["name"] for f in _ast_functions(repo)}
    valid = set(symbols) & ast_syms
    return {"ast_symbols": len(ast_syms), "claimed": len(symbols),
            "valid": len(valid),
            "rate": round(len(valid) / max(len(symbols), 1), 3)}


def assess(*, arxiv_id: str, graph: POGraph, extraction_dir: str | Path,
           repo: str = "", out_dir: str | Path = "storage_cf/sciforge/repro_compare",
           run_flow: bool = True) -> Dict[str, Any]:
    ex = load_extraction(extraction_dir)
    method, bench = ex["method"], ex["benchmark"]
    steps = method.get("steps") or []
    mods = to_modules(method)
    syms = sorted({s for st in steps for s in (st.get("code_symbols") or [])})
    inv_text = str(method.get("invariant") or "")
    obs = bench.get("observations") or []
    benches = bench.get("benchmarks") or []
    rep: Dict[str, Any] = {
        "arxiv_id": arxiv_id,
        "extraction": {"n_steps": len(steps), "n_modules": len(mods),
                       "n_code_symbols": len(syms),
                       "n_formula_refs": sum(1 for s in steps
                                             if s.get("formula_ref")),
                       "n_benchmarks": len(benches),
                       "n_observations": len(obs),
                       "invariant": inv_text[:120],
                       "observed_metrics": sorted({str(o.get("metric"))
                                                   for o in obs})[:12]},
        "symbol_coverage": symbol_coverage(syms, repo),
        "baseline": {}, "with_extraction": {},
    }
    if not run_flow:
        return rep
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    try:
        a = ReproductionFlow(graph, arxiv_id=arxiv_id, mode="de_novo",
                             run_id=f"cmp_base_{arxiv_id}",
                             out_root=str(out / "base")).run()
        s = a.get("repro_summary", {})
        rep["baseline"] = {"ok": a["final"]["verdict"] == "PASS",
                           "seconds": round(time.time() - t0, 1),
                           "n_modules": s.get("n_modules"),
                           "invariant": s.get("invariant"),
                           "reproduce": s.get("reproduce")}
    except Exception as exc:  # noqa: BLE001
        rep["baseline"] = {"ok": False, "error": str(exc)[:180]}

    t0 = time.time()
    try:
        b = ReproductionFlow(graph, arxiv_id=arxiv_id, mode="de_novo",
                             external_modules=mods,
                             external_invariant=inv_text,
                             external_symbols=syms,
                             external_steps=steps,
                             run_id=f"cmp_extr_{arxiv_id}",
                             out_root=str(out / "extr")).run()
        s = b.get("repro_summary", {})
        reg = (out / "extr" / f"cmp_extr_{arxiv_id}" /
               "METHOD_REGISTRY.json")
        gen = (out / "extr" / f"cmp_extr_{arxiv_id}" / "generated" /
               "repro_impl.py")
        gen_syms = set()
        if gen.exists():
            import ast as _ast
            try:
                tree = _ast.parse(gen.read_text(encoding="utf-8"))
                gen_syms = {n.name for n in _ast.walk(tree)
                            if isinstance(n, (_ast.FunctionDef, _ast.ClassDef))}
            except SyntaxError:
                pass
        rep["generated_code_alignment"] = {
            "generated_symbols": sorted(gen_syms)[:12],
            "claimed_symbols": len(syms),
            "overlap": len(set(syms) & gen_syms),
            "rate": round(len(set(syms) & gen_syms) / max(len(syms), 1), 3),
            "note": "模板生成的是解析解 toy；多步实现需按抽取 steps 分派"}
        rep["with_extraction"] = {
            "ok": b["final"]["verdict"] == "PASS",
            "seconds": round(time.time() - t0, 1),
            "n_modules": s.get("n_modules"),
            "invariant": s.get("invariant"),
            "reproduce": s.get("reproduce"),
            "module_source": "multistage_extraction",
            "registry_exists": reg.exists()}
    except Exception as exc:  # noqa: BLE001
        rep["with_extraction"] = {"ok": False, "error": str(exc)[:180]}

    rep["gain"] = {
        "modules_delta": (rep["with_extraction"].get("n_modules") or 0) -
                         (rep["baseline"].get("n_modules") or 0),
        "both_pass": bool(rep["baseline"].get("ok") and
                          rep["with_extraction"].get("ok")),
        "extraction_adds_structure": len(mods) > 0 and len(syms) > 0,
    }
    (out / f"REPRO_COMPARE_{arxiv_id}.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    return rep
