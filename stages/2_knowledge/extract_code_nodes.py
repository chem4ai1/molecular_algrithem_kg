#!/usr/bin/env python3
"""从 data3 代码仓库抽取代码语义节点与应用层代码节点。

- manifest.json 的 paper.reason 里 [owner/repo] → repo.local
- 语义层：Paper --HAS_CODE--> CodeRepository --HAS_FUNCTION--> CodeFunction
- 应用层：CodeArtifact / CodeUnit / CodeSymbol / Dependency / EntryPoint / EnvSpec / TestUnit
"""
from __future__ import annotations
import argparse, ast, json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from capfactory.po import POGraph

DATA3 = ROOT / "data/data3"
MANIFEST = DATA3 / "manifest.json"
BASE = ROOT / "storage/sciforge/factory_knowledge_rules.json"
OUT = ROOT / "storage/sciforge/factory_knowledge_data3_code.json"
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "build", "dist"}

APP_CODE = {"CodeArtifact", "CodeUnit", "CodeSymbol", "Dependency",
            "EntryPoint", "EnvSpec", "TestUnit"}


def _add(g, nid, typ, label, *, layer, **attrs):
    if nid in g.nodes:
        return False
    attrs.setdefault("layer", layer)
    attrs.setdefault("miner", "code_extract")
    if layer == "application" and not attrs.get("source"):
        attrs["source"] = "data3/code AST"
    g.node(nid, typ, label, **attrs)
    return True


def _rel(g, s, r, t):
    if s in g.nodes and t in g.nodes:
        g.assert_rel(s, t, r)


def _pick_py(repo_dir: Path, max_files: int):
    files = [p for p in repo_dir.rglob("*.py")
             if not any(d in SKIP_DIRS for d in p.parts)]
    def rank(p):
        n = p.name.lower()
        bonus = 0
        if n in ("main.py", "train.py", "run.py", "setup.py"): bonus -= 10
        if "model" in n or "graph" in n or "onto" in n: bonus -= 5
        if "test" in n: bonus -= 2
        if "example" in p.parts or "demo" in p.parts: bonus += 5
        return (bonus, len(p.parts), str(p))
    return sorted(files, key=rank)[:max_files]


def _parse_py(path: Path, rel: str):
    text = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(text)
    symbols, deps, has_main = [], set(), False
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = (ast.get_docstring(node) or "").splitlines()
            symbols.append({"name": node.name,
                            "purpose": doc[0][:160] if doc else "",
                            "params": [a.arg for a in node.args.args][:12],
                            "returns": getattr(node.returns, "id", "") if node.returns else "",
                            "func_type": "test" if node.name.startswith("test_") else "function"})
        elif isinstance(node, ast.ClassDef):
            doc = (ast.get_docstring(node) or "").splitlines()
            symbols.append({"name": node.name,
                            "purpose": doc[0][:160] if doc else "",
                            "params": [b.id for b in node.bases if isinstance(b, ast.Name)][:8],
                            "returns": "", "func_type": "class"})
        elif isinstance(node, ast.Import):
            deps.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            deps.add(node.module.split(".")[0])
        if isinstance(node, ast.If):
            src = ast.unparse(node.test)
            if "__name__" in src and "__main__" in src:
                has_main = True
    return symbols, sorted(deps), has_main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 篇论文（0=全部）")
    ap.add_argument("--max-files", type=int, default=15)
    a = ap.parse_args()

    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    repos = {r["repo"]: r for r in man["repos"]}
    g = POGraph.load(str(BASE))
    before = (len(g.nodes), len(g.assertions))
    stat = {"papers": 0, "repos": 0, "functions": 0,
            "codeunits": 0, "symbols": 0, "deps": 0, "entrypoints": 0, "env": 0}

    papers = man["papers"]
    if a.limit:
        papers = papers[:a.limit]

    for p in papers:
        m = re.search(r"\[([^\]]+)\]", p.get("reason") or "")
        if not m:
            continue
        repo_id = m.group(1).strip()
        meta = repos.get(repo_id)
        if not meta or not meta.get("downloaded"):
            continue
        repo_dir = DATA3 / "code" / meta["local"]
        if not repo_dir.exists():
            continue
        aid = p["id"]
        paper_id = f"paper:{aid}"
        if paper_id not in g.nodes:
            _add(g, paper_id, "Paper", p["title"][:100], layer="semantic",
                 arxiv_id=aid, title=p["title"], from_data3=True,
                 source="data/data3/manifest.json")
        repo_nid = f"coderepo:{repo_id.replace('/', ':')}"
        license_file = next(iter(list(repo_dir.glob("LICENSE*")) + list(repo_dir.glob("COPYING*"))), None)
        _add(g, repo_nid, "CodeRepository", repo_id, layer="semantic",
             repo_name=repo_id.split("/")[-1], repo_url=meta.get("github", ""),
             local_path=str(repo_dir.relative_to(ROOT)),
             license=(license_file.name if license_file else ""),
             is_original_repo=meta.get("category") in ("B", "C"),
             source="data/data3/manifest.json")
        _rel(g, paper_id, "HAS_CODE", repo_nid)
        stat["papers"] += 1; stat["repos"] += 1

        # 应用层 CodeArtifact
        art_id = f"codeartifact:{repo_id.replace('/', ':')}"
        _add(g, art_id, "CodeArtifact", repo_id, layer="application", task="writing",
             run_id="data3", repo=repo_id, source="data3/code AST",
             modules=[], entrypoints=[], deps=[], smoke_test="pending")
        files = _pick_py(repo_dir, a.max_files)
        all_deps = set()
        entry_ids = []
        for path in files:
            rel = str(path.relative_to(repo_dir))
            try:
                syms, deps, has_main = _parse_py(path, rel)
            except SyntaxError:
                continue
            all_deps.update(deps)
            uid = f"codeunit:{repo_id.replace('/', ':')}:{re.sub(r'[^A-Za-z0-9]+','_',rel)}"
            if _add(g, uid, "CodeUnit", rel, layer="application", task="writing",
                    run_id="data3", repo=repo_id, path=rel,
                    source="data3/code AST"):
                stat["codeunits"] += 1
            for s in syms:
                sid = f"codesymbol:{repo_id.replace('/', ':')}:{s['name']}"
                if _add(g, sid, "CodeSymbol", s["name"], layer="application",
                        task="writing", run_id="data3", **s):
                    _rel(g, uid, "CONTAINS", sid)
                    stat["symbols"] += 1
                fid = f"codefunction:{repo_id.replace('/', ':')}:{s['name']}"
                if _add(g, fid, "CodeFunction", s["name"], layer="semantic",
                        name=s["name"], purpose=s["purpose"], params=s["params"],
                        returns=s["returns"], func_type=s["func_type"],
                        source=f"data3/code/{meta['local']}/{rel}"):
                    _rel(g, repo_nid, "HAS_FUNCTION", fid)
                    stat["functions"] += 1
            for d in deps:
                did = f"dependency:{d}"
                if _add(g, did, "Dependency", d, layer="application",
                        task="writing", run_id="data3", package=d):
                    _rel(g, uid, "DEPENDS_ON", did)
                    stat["deps"] += 1
            if has_main or path.name.lower() in ("main.py", "train.py", "run.py"):
                eid = f"entrypoint:{repo_id.replace('/', ':')}:{re.sub(r'[^A-Za-z0-9]+','_',rel)}"
                if _add(g, eid, "EntryPoint", rel, layer="application",
                        task="writing", run_id="data3", repo=repo_id, path=rel):
                    _rel(g, eid, "IN_UNIT", uid)
                    entry_ids.append(eid)
                    stat["entrypoints"] += 1
            if path.name.startswith("test_") or any(s["func_type"] == "test" for s in syms):
                tid = f"testunit:{repo_id.replace('/', ':')}:{re.sub(r'[^A-Za-z0-9]+','_',rel)}"
                if _add(g, tid, "TestUnit", rel, layer="application",
                        task="writing", run_id="data3", path=rel):
                    _rel(g, tid, "TEST_IN", uid)
        env_files = [x.name for x in repo_dir.iterdir()
                     if x.name in ("requirements.txt", "environment.yml", "pyproject.toml", "setup.py")]
        if env_files:
            vid = f"envspec:{repo_id.replace('/', ':')}"
            _add(g, vid, "EnvSpec", ", ".join(env_files), layer="application",
                 task="writing", run_id="data3", files=env_files)
            for eid in entry_ids:
                _rel(g, eid, "USES_ENV", vid)
            stat["env"] += 1
        if art_id in g.nodes:
            g.nodes[art_id].attrs.update({
                "modules": [n.id for n in g.nodes.values()
                            if n.attrs.get("repo") == repo_id and n.type == "CodeUnit"],
                "entrypoints": entry_ids,
                "deps": sorted(all_deps)[:30]})

    g.save(str(OUT))
    print(json.dumps({"before": {"nodes": before[0], "assertions": before[1]},
                      "after": {"nodes": len(g.nodes), "assertions": len(g.assertions)},
                      "stat": stat, "out": str(OUT)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
