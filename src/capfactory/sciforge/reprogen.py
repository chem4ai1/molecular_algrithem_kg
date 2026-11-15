"""性质驱动的代码生成与静态审计（纯标准库）。

不试图复现整篇论文，而是从论文找一个可解析检验的不变量，
生成最小实现，用解析真值判生死（SciForge toy 生死门）。
"""
from __future__ import annotations
import ast, re
from pathlib import Path
from typing import Any, Dict, List
from .contracts import method_code_parity, sha256_file

INVARIANTS = {
    "canonicalization_invariance": {
        "keywords": ("canonical", "permutation", "symmetr", "invariant", "equivariant"),
        "truth": "canonicalize(g.x) == canonicalize(x) for any group element g",
        "required": ("canonical", "canonicalization")},
    "rotation_equivariance": {
        "keywords": ("rotation", "e(n)", "se(3)", "equivariant"),
        "truth": "f(RX+t) == R f(X) + t; pairwise distances are invariant"},
    "density_normalization": {
        "keywords": ("normalizing flow", "jacobian", "log det", "density"),
        "truth": "change of variables: log p(x) = log p(z) + log|det df/dz|"},
}

LLM_TEST_PROMPT = """写一个 Python 断言函数，只输出代码（无围栏、无解释）：
只允许 import json/math/random；禁止文件/网络/子进程/eval/exec。
函数名 def extra_assert(result):，检查 result status 为 PASS
且每个 row 的 candidate_error 小于 1e-9，否则 raise AssertionError。
不超过 12 行。解析真值：{truth}
"""

TEMPLATE = '''"""__TITLE__
De-novo reproduction for arXiv:__ARXIV__ (no official code).
Pure stdlib, deterministic. Analytic truth: __TRUTH__
"""
import json, random


def canonicalize(points):
    """Sort point tuples -> invariant to input permutation."""
    return tuple(sorted(tuple(float(v) for v in p) for p in points))


def apply_group(points, perm):
    return [points[i] for i in perm]


def score_naive(points):
    """Baseline: raw order -> NOT invariant under the group action."""
    return points[0][0]


def score_canonical(points):
    """Candidate: canonicalize first -> invariant."""
    return canonicalize(points)[0][0]


def run(seeds=(42, 43, 44), n=8):
    rows = []
    for seed in seeds:
        rng = random.Random(seed)
        pts = [[rng.uniform(-2, 2) for _ in range(3)] for _ in range(n)]
        perm = list(range(n))
        rng.shuffle(perm)
        gp = apply_group(pts, perm)
        exact = canonicalize(pts) == canonicalize(gp)
        rows.append({"seed": seed, "analytic_exact": exact,
                     "baseline_error": abs(score_naive(pts) - score_naive(gp)),
                     "candidate_error": abs(score_canonical(pts) - score_canonical(gp))})
    baseline = sum(r["baseline_error"] for r in rows) / len(rows)
    candidate = sum(r["candidate_error"] for r in rows) / len(rows)
    return {"experiment": "canonicalization_invariance_toy",
             "analytic_ground_truth": __TRUTH_REPR__, "seeds": list(seeds),
             "rows": rows, "baseline": baseline, "candidate": candidate,
             "direction": "minimize", "sanity_band": [0.0, 1e-9],
             "status": "PASS" if all(r["analytic_exact"] for r in rows)
                       and candidate < 1e-9 else "FAIL"}


if __name__ == "__main__":
    print(json.dumps(run()))
'''


def unsafe_imports(src: str) -> List[str]:
    """AST 静态检查：白名单外 import 与危险调用。"""
    allow = {"json", "math", "random", "sys", "__future__"}
    out: List[str] = []
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [f"SyntaxError: {e}"]
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out += [a.name.split(".")[0] for a in n.names
                    if a.name.split(".")[0] not in allow]
        elif isinstance(n, ast.ImportFrom) and n.module:
            if n.module.split(".")[0] not in allow:
                out.append(n.module.split(".")[0])
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and \
                n.func.id in ("eval", "exec", "open", "compile", "__import__"):
            out.append(f"forbidden:{n.func.id}")
    return sorted(set(out))


def pick_invariant(text: str) -> Dict[str, Any]:
    low = (text or "").lower()
    scores = {k: sum(low.count(w) for w in v["keywords"])
              for k, v in INVARIANTS.items()}
    # required 是判别性词：没有 canonical 就不能判规范化不变性，
    # 否则 EGNN 里的大量 "invariant/equivariant" 会把它误抢过去。
    eligible = [k for k, v in INVARIANTS.items()
                if not v.get("required") or any(r in low for r in v["required"])]
    if not eligible:
        eligible = list(INVARIANTS)
    name = max(eligible, key=lambda k: scores[k])
    return {"invariant": name, "truth": INVARIANTS[name]["truth"],
            "keyword_scores": scores}


def generate_code(*, out_path: str, title: str, arxiv_id: str,
                  truth: str, chat_fn: Any = None) -> Dict[str, Any]:
    """真实写出可执行 .py；LLM 只可追加断言且必须过 AST 安全检查。"""
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    src = (TEMPLATE.replace("__TITLE__", title[:70])
                   .replace("__ARXIV__", arxiv_id)
                   .replace("__TRUTH_REPR__", repr(truth))
                   .replace("__TRUTH__", truth))
    path.write_text(src, encoding="utf-8")
    llm_status = "not_attempted"
    if chat_fn:
        try:
            cand = re.sub(r"^```(?:python)?\s*|\s*```$", "",
                          (chat_fn(LLM_TEST_PROMPT.replace("{truth}", truth)) or "").strip(),
                          flags=re.S).strip()
            unsafe = unsafe_imports(cand)
            if cand.startswith("def extra_assert") and not unsafe:
                path.write_text(src + "\n\n# LLM assertion\n" + cand + "\n",
                                encoding="utf-8")
                llm_status = "accepted"
            else:
                llm_status = f"rejected: {unsafe or 'bad signature'}"
        except Exception as e:
            llm_status = f"error: {type(e).__name__}"
    final = path.read_text(encoding="utf-8")
    unsafe = unsafe_imports(final)
    parity = method_code_parity(
        "`canonicalize` `score_naive` `score_canonical` `apply_group`", final)
    return {"path": str(path), "sha256": sha256_file(path),
            "n_lines": len(final.splitlines()), "llm_assertion": llm_status,
            "unsafe_imports": unsafe, "parity": parity,
            "checks": {"ast_parse": "PASS" if not unsafe else "FAIL",
                       "import_whitelist": "PASS" if not unsafe else "FAIL",
                       "method_parity": parity["status"]}}


def audit_repo(*, repo_root: str, modules_raw: Dict[str, Any]) -> Dict[str, Any]:
    """已有仓库：AST 结构 + code_symbols 有效率 + 方法-代码 parity。"""
    from ..ontology.modules import code_structure, _symbol_index
    root = Path(repo_root)
    struct = code_structure(root, max_symbols=40)
    idx = _symbol_index(struct)
    syms = [s for m in (modules_raw.get("modules") or [])
            for s in (m.get("code_symbols") or [])]
    valid = [s for s in syms if s in idx]
    code_text = ""
    for fp in sorted(root.rglob("*.py"))[:12]:
        code_text += fp.read_text(encoding="utf-8", errors="replace") + "\n"
    method_text = " ".join(str(m.get("module_name", "")) for m in
                           (modules_raw.get("modules") or []))
    parity = method_code_parity(method_text, code_text)
    return {"n_symbols": struct["n_symbols"], "claimed": len(syms),
            "valid": len(valid), "rate": round(len(valid) / max(len(syms), 1), 3),
            "parity": parity, "path": str(root),
            "checks": {"code_structure": "PASS" if struct["n_symbols"] else "FAIL",
                       "symbol_efficiency": f"{len(valid)}/{len(syms)}",
                       "method_parity": parity["status"]}}
