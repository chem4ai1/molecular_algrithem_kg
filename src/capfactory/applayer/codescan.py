"""代码域扫描：把本地仓库变成 CodeUnit / CodeSymbol / Dependency / EntryPoint / TestUnit / EnvSpec。

纯 AST + 文件系统，零 LLM。粒度停在符号级（不做行级、不做字段级），
理由见 docs/schema/CODE_DOMAIN.md §1。
"""
from __future__ import annotations
import ast
import hashlib
import re
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

ROLE_RULES = (
    (re.compile(r"(^|/)(tests?|testing)/|(^|/)test_.*\.py$|_test\.py$"), "test"),
    (re.compile(r"(^|/)(setup\.py|pyproject\.toml|requirements.*\.txt|"
                r"environment\.ya?ml|Dockerfile)$"), "config"),
    (re.compile(r"(^|/)(main|run|train|eval|inference|demo|app)\.py$"), "entry"),
    (re.compile(r"(^|/)(docs?|examples?|scripts?)/"), "auxiliary"),
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _role(rel: str) -> str:
    for pat, role in ROLE_RULES:
        if pat.search(rel):
            return role
    return "lib"


def _slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", str(s or "")).strip("_")[:60]


def scan_repo(repo_dir: Path, *, repo_id: str = "") -> Dict[str, Any]:
    """扫一个仓库，返回 {units, symbols, deps, entries, tests, env, stats}。"""
    repo_dir = Path(repo_dir)
    rid = repo_id or _slug(repo_dir.name)
    units: List[Dict[str, Any]] = []
    symbols: List[Dict[str, Any]] = []
    deps: Dict[str, Dict[str, Any]] = {}
    entries: List[Dict[str, Any]] = []
    tests: List[Dict[str, Any]] = []
    env = {"python": None, "cuda": None, "packages": [], "device": None}
    py_files = sorted(repo_dir.rglob("*.py"))
    for f in py_files:
        if any(p in f.parts for p in ("__pycache__", ".git", "build", "dist")):
            continue
        rel = str(f.relative_to(repo_dir))
        try:
            src = f.read_text(encoding="utf-8", errors="replace")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = ast.parse(src)
        except (OSError, SyntaxError):
            continue
        uid = f"codeunit:{rid}:{_slug(rel)}"
        role = _role(rel)
        units.append({"id": uid, "path": rel, "lang": "python", "role": role,
                      "loc": len(src.splitlines()), "sha256": _sha(f)})
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                sid = f"codesymbol:{rid}:{_slug(rel)}:{_slug(node.name)}"
                symbols.append({"id": sid, "name": node.name, "kind": "class",
                                "signature": f"class {node.name}",
                                "qualname": node.name, "loc": getattr(node, "lineno", 0),
                                "unit": uid,
                                "bases": [getattr(b, "id", getattr(b, "attr", ""))
                                          for b in node.bases]})
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                parent = ""
                for c in ast.walk(tree):
                    if isinstance(c, ast.ClassDef) and node in c.body:
                        parent = c.name + "."
                        break
                kind = "method" if parent else "function"
                sid = f"codesymbol:{rid}:{_slug(rel)}:{_slug(parent + node.name)}"
                args = [a.arg for a in node.args.args][:6]
                symbols.append({"id": sid, "name": node.name, "kind": kind,
                                "signature": f"{node.name}({', '.join(args)})",
                                "qualname": parent + node.name,
                                "loc": getattr(node, "lineno", 0), "unit": uid})
            elif isinstance(node, ast.Import):
                for a in node.names:
                    root = a.name.split(".")[0]
                    deps.setdefault(root, {"name": root, "declared_in": rel})
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                deps.setdefault(root, {"name": root, "declared_in": rel})
        if '__name__' in src and '__main__' in src:
            entries.append({"id": f"entry:{rid}:{_slug(rel)}", "path": rel,
                            "cmd": f"python {rel}", "cwd": str(repo_dir)})
        if role == "test" or f.name.startswith("test_"):
            tests.append({"id": f"test:{rid}:{_slug(rel)}", "name": f.stem,
                          "path": rel, "covers": []})
    # requirements / setup.py 里的依赖
    for name in ("requirements.txt", "requirements-dev.txt"):
        p = repo_dir / name
        if p.exists():
            for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
                ln = ln.strip()
                if not ln or ln.startswith("#"):
                    continue
                m = re.match(r"([A-Za-z0-9_.\-]+)\s*([=<>!~]=?\s*[\w.]+)?", ln)
                if m:
                    key = m.group(1).lower()
                    deps.setdefault(key, {"name": key,
                                          "version": (m.group(2) or "").strip(),
                                          "declared_in": name})
    return {"repo_id": rid, "root": str(repo_dir), "units": units,
            "symbols": symbols,
            "deps": [{"id": f"dep:{rid}:{_slug(k)}", **v} for k, v in deps.items()],
            "entries": entries, "tests": tests, "env": env,
            "stats": {"units": len(units), "symbols": len(symbols),
                      "deps": len(deps), "entries": len(entries),
                      "tests": len(tests), "py_files": len(py_files)}}
