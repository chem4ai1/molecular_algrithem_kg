#!/usr/bin/env python3
"""从 data3 全量论文/代码建代码语义节点与应用层代码节点。

- 31 篇 paper 全部建 Paper proxy
- 48 个本地 repo 全部建 CodeRepository + 代码 AST 节点
- paper-repo 关联优先用 reason 中 [owner/repo]，否则用标题 token 弱匹配并标记
- 尝试对齐已有 Algorithm/AlgorithmModule 与 CodeFunction/CodeSymbol
"""
from __future__ import annotations
import argparse, ast, json, re, shutil, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from capfactory.po import POGraph

DATA3 = ROOT / "data/data3"
MANIFEST = DATA3 / "manifest.json"
DEFAULT_GRAPH = ROOT / "storage/sciforge/factory_knowledge_main.json"
DEFAULT_OUT = ROOT / "storage/sciforge/factory_knowledge_main_with_code.json"
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
        return True
    return False


def _pick_py(repo_dir: Path, max_files: int):
    files = [p for p in repo_dir.rglob("*.py")
             if not any(d in SKIP_DIRS for d in p.parts)]
    def rank(p):
        n = p.name.lower()
        bonus = 0
        if n in ("main.py", "train.py", "run.py", "setup.py"): bonus -= 10
        if any(k in n for k in ("model", "graph", "onto", "schema", "learn")): bonus -= 5
        if "test" in n: bonus -= 2
        if "example" in p.parts or "demo" in p.parts: bonus += 5
        return (bonus, len(p.parts), str(p))
    return sorted(files, key=rank)[:max_files]


def _parse_py(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    symbols, deps, has_main = [], set(), False
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = (ast.get_docstring(node) or "").splitlines()
            symbols.append({"name": node.name, "purpose": doc[0][:160] if doc else "",
                            "params": [a.arg for a in node.args.args][:12],
                            "returns": getattr(node.returns, "id", "") if node.returns else "",
                            "func_type": "test" if node.name.startswith("test_") else "function"})
        elif isinstance(node, ast.ClassDef):
            doc = (ast.get_docstring(node) or "").splitlines()
            symbols.append({"name": node.name, "purpose": doc[0][:160] if doc else "",
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


def _tokens(s: str):
    return {t for t in re.findall(r"[a-z0-9]{4,}", (s or "").lower())}


def _match_repo(paper, repos):
    reason = paper.get("reason") or ""
    m = re.search(r"\[([^\]]+)\]", reason)
    if m and m.group(1) in repos:
        return m.group(1), "manifest_bracket"
    title_tok = _tokens(paper.get("title"))
    best, score = None, 0
    for rid, meta in repos.items():
        rtok = _tokens(rid.replace("/", " ").replace("-", " ").replace("_", " "))
        s = len(title_tok & rtok)
        if s > score:
            best, score = rid, s
    if best and score >= 2:
        return best, "title_token_weak"
    return None, "unmatched"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", default=str(DEFAULT_GRAPH))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--max-files", type=int, default=10)
    a = ap.parse_args()

    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    repos = {r["repo"]: r for r in man["repos"]}
    g = POGraph.load(a.graph)
    before = (len(g.nodes), len(g.assertions))
    stat = {"papers_all": 0, "repos_all": 0, "links_exact": 0,
            "links_weak": 0, "links_unmatched": 0,
            "functions": 0, "codeunits": 0, "symbols": 0,
            "deps": 0, "entrypoints": 0, "env": 0,
            "aligned_modules": 0}

    # 1) 全部 Paper proxy
    for p in man["papers"]:
        aid = p["id"]
        pid = f"paper:{aid}"
        if _add(g, pid, "Paper", p["title"][:110], layer="semantic",
                arxiv_id=aid, title=p["title"], from_data3=True,
                extraction_status="proxy",
                source="data/data3/manifest.json"):
            stat["papers_all"] += 1

    # 2) 全部 repo + 代码 AST 节点
    symbol_index = {}
    for repo_id, meta in repos.items():
        if not meta.get("downloaded"):
            continue
        repo_dir = DATA3 / "code" / meta["local"]
        if not repo_dir.exists():
            continue
        stat["repos_all"] += 1
        license_file = next(iter(list(repo_dir.glob("LICENSE*")) + list(repo_dir.glob("COPYING*"))), None)
        repo_nid = f"coderepo:{repo_id.replace('/', ':')}"
        _add(g, repo_nid, "CodeRepository", repo_id, layer="semantic",
             repo_name=repo_id.split("/")[-1], repo_url=meta.get("github", ""),
             local_path=str(repo_dir.relative_to(ROOT)),
             license=(license_file.name if license_file else ""),
             is_original_repo=meta.get("category") in ("B", "C"),
             source="data/data3/manifest.json")

        art_id = f"codeartifact:{repo_id.replace('/', ':')}"
        _add(g, art_id, "CodeArtifact", repo_id, layer="application", task="writing",
             run_id="data3", repo=repo_id, source="data3/code AST",
             modules=[], entrypoints=[], deps=[], smoke_test="pending")
        all_deps, entry_ids = set(), []
        for path in _pick_py(repo_dir, a.max_files):
            rel = str(path.relative_to(repo_dir))
            try:
                syms, deps, has_main = _parse_py(path)
            except SyntaxError:
                continue
            all_deps.update(deps)
            uid = f"codeunit:{repo_id.replace('/', ':')}:{re.sub(r'[^A-Za-z0-9]+','_',rel)}"
            if _add(g, uid, "CodeUnit", rel, layer="application", task="writing",
                    run_id="data3", repo=repo_id, path=rel, source="data3/code AST"):
                stat["codeunits"] += 1
            for s in syms:
                sid = f"codesymbol:{repo_id.replace('/', ':')}:{s['name']}"
                if _add(g, sid, "CodeSymbol", s["name"], layer="application",
                        task="writing", run_id="data3", source="data3/code AST", **s):
                    _rel(g, uid, "CONTAINS", sid)
                    stat["symbols"] += 1
                    symbol_index.setdefault(s["name"].lower(), []).append((repo_id, sid))
                fid = f"codefunction:{repo_id.replace('/', ':')}:{s['name']}"
                if _add(g, fid, "CodeFunction", s["name"], layer="semantic",
                        name=s["name"], purpose=s["purpose"], params=s["params"],
                        returns=s["returns"], func_type=s["func_type"],
                        source=f"data3/code/{meta['local']}/{rel}"):
                    _rel(g, repo_nid, "HAS_FUNCTION", fid)
                    stat["functions"] += 1
            for d in deps:
                did = f"dependency:{d}"
                if _add(g, did, "Dependency", d, layer="application", task="writing",
                        run_id="data3", source="data3/code AST", package=d):
                    _rel(g, uid, "DEPENDS_ON", did)
                    stat["deps"] += 1
            if has_main or path.name.lower() in ("main.py", "train.py", "run.py"):
                eid = f"entrypoint:{repo_id.replace('/', ':')}:{re.sub(r'[^A-Za-z0-9]+','_',rel)}"
                if _add(g, eid, "EntryPoint", rel, layer="application", task="writing",
                        run_id="data3", source="data3/code AST", repo=repo_id, path=rel):
                    _rel(g, eid, "IN_UNIT", uid)
                    entry_ids.append(eid)
                    stat["entrypoints"] += 1
            if path.name.startswith("test_") or any(s["func_type"] == "test" for s in syms):
                tid = f"testunit:{repo_id.replace('/', ':')}:{re.sub(r'[^A-Za-z0-9]+','_',rel)}"
                if _add(g, tid, "TestUnit", rel, layer="application", task="writing",
                        run_id="data3", source="data3/code AST", path=rel):
                    _rel(g, tid, "TEST_IN", uid)
        env_files = [x.name for x in repo_dir.iterdir()
                     if x.name in ("requirements.txt", "environment.yml", "pyproject.toml", "setup.py")]
        if env_files:
            vid = f"envspec:{repo_id.replace('/', ':')}"
            _add(g, vid, "EnvSpec", ", ".join(env_files), layer="application",
                 task="writing", run_id="data3", source="data3/code AST", files=env_files)
            for eid in entry_ids:
                _rel(g, eid, "USES_ENV", vid)
            stat["env"] += 1
        if art_id in g.nodes:
            g.nodes[art_id].attrs.update({
                "modules": [n.id for n in g.nodes.values()
                            if n.attrs.get("repo") == repo_id and n.type == "CodeUnit"],
                "entrypoints": entry_ids, "deps": sorted(all_deps)[:30]})

    # 3) paper-repo 关联
    for p in man["papers"]:
        pid = f"paper:{p['id']}"
        rid, status = _match_repo(p, repos)
        if not rid:
            stat["links_unmatched"] += 1
            continue
        repo_nid = f"coderepo:{rid.replace('/', ':')}"
        if _rel(g, pid, "HAS_CODE", repo_nid):
            stat["links_exact" if status == "manifest_bracket" else "links_weak"] += 1
            if pid in g.nodes:
                g.nodes[pid].attrs["code_match_status"] = status
                g.nodes[pid].attrs["code_repo"] = rid

    # 4) Algorithm/AlgorithmModule 对齐
    for p in g.by_type("Paper"):
        aid = p.attrs.get("arxiv_id") or ""
        alg_ids = [a.target for a in g.outgoing(p.id) if a.relation == "PROPOSES_METHOD"]
        if not alg_ids:
            continue
        for alg_id in alg_ids:
            mods = [a.target for a in g.outgoing(alg_id) if a.relation == "HAS_MODULE"]
            if alg_id not in g.nodes:
                continue
            for mid in mods:
                if mid not in g.nodes:
                    continue
                mname = str(g.nodes[mid].attrs.get("name") or g.nodes[mid].label).lower()
                cands = []
                for name, lst in symbol_index.items():
                    if name and (name in mname or mname in name):
                        cands.extend(lst)
                if not cands:
                    continue
                repo_id = p.attrs.get("code_repo")
                repo_cands = [x for x in cands if x[0] == repo_id]
                chosen_repo, sid = (repo_cands or cands)[0]
                fid = f"codefunction:{chosen_repo.replace('/', ':')}:{sid.rsplit(':',1)[-1]}"
                _rel(g, mid, "MODULE_IMPLEMENTED_BY", fid)
                _rel(g, mid, "IMPLEMENTED_BY", sid)
                g.nodes[mid].attrs["implementation_match"] = {
                    "repo": chosen_repo, "symbol": sid, "function": fid}
                stat["aligned_modules"] += 1

    g.save(a.out)
    shutil.copy(a.out, a.graph)
    print(json.dumps({"before": {"nodes": before[0], "assertions": before[1]},
                      "after": {"nodes": len(g.nodes), "assertions": len(g.assertions)},
                      "stat": stat, "out": a.out}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
