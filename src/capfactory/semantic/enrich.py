"""语义层补齐（Stage3 确定性，不调 LLM）：把迁移后缺失的属性/关系填上。

覆盖 EXTRACTION_ARCHITECTURE.md §4 的 8 个缺口中的 6 个：
  repo_url / license · HAS_FUNCTION · Paper.keywords · SUBCLASS_OF ·
  Algorithm 级 EVALUATED_ON · Algorithm.applicable_to/limitations
（CodeFunction 4 属性与 func_type 由 ontology/modules.py 的 AST 产出，不在本模块）
"""
from __future__ import annotations
import os
import collections, re
from pathlib import Path
from typing import Any, Dict, List

MD_DIR = Path(os.environ.get("CAPFACTORY_PAPERS_DIR", "data/docx"))
URL_PAT = re.compile(
    r"https?://github\.com/([A-Za-z0-9_.\-]+)/([A-Za-z0-9_.\-]+)")
STOP = set("""a an the of and or for to in on with by from as at is are be this
that these those we our it its using used use based via which such can may
method methods model models paper results show shows propose proposed""".split())


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s or "").lower())


def _urls_of(arxiv_id: str) -> List[str]:
    p = MD_DIR / f"{arxiv_id}.md"
    if not p.exists():
        return []
    txt = p.read_text(encoding="utf-8", errors="replace")
    return [f"https://github.com/{a}/{b.rstrip('.')}"
            for a, b in URL_PAT.findall(txt)]


def fill_repo_url(g: Any) -> Dict[str, int]:
    """按 repo_name 与原文 GitHub URL 归一匹配填 repo_url。"""
    cache: Dict[str, List[str]] = {}
    n = 0
    for p in g.by_type("Paper"):
        aid = str(p.attrs.get("arxiv_id") or "")
        if not aid:
            continue
        urls = cache.setdefault(aid, _urls_of(aid))
        if not urls:
            continue
        repos = [a.target for a in g.outgoing(p.id)
                 if a.relation == "HAS_CODE" and a.target in g.nodes]
        for rid in repos:
            r = g.nodes[rid]
            key = _norm(r.attrs.get("repo_name") or r.label)
            for u in urls:
                cand = _norm(u.replace("https://github.com/", ""))
                if key and (key in cand or cand.endswith(key) or
                            key.endswith(cand)):
                    if not r.attrs.get("repo_url"):
                        r.attrs["repo_url"] = u
                        n += 1
                    break
    return {"repo_url_filled": n}


def fill_license(g: Any) -> Dict[str, int]:
    """从仓库本地目录的 LICENSE 首行填 license（无本地目录则留空）。"""
    n = 0
    for r in g.by_type("CodeRepository"):
        lp = r.attrs.get("local_path") or ""
        if not lp:
            continue
        d = Path(lp)
        if not d.exists():
            continue
        for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"):
            f = d / name
            if f.exists():
                first = f.read_text(encoding="utf-8",
                                     errors="replace").strip().split("\n")[0]
                if first:
                    r.attrs["license"] = first[:80]
                    n += 1
                break
    return {"license_filled": n}


def _repo_of(func_path: str, repos: List[Any]) -> str:
    """按 module_path 判断函数属于哪个本地仓库。"""
    p = str(func_path or "")
    best, best_len = "", 0
    for r in repos:
        lp = str(r.attrs.get("local_path") or "")
        if lp and p.startswith(lp.rstrip("/") + "/") and len(lp) > best_len:
            best, best_len = r.id, len(lp)
    return best


def refine_code_functions(g: Any, *, max_files: int = 40,
                          max_symbols: int = 300) -> Dict[str, int]:
    """用 AST 重新解析本地仓库，回填 CodeFunction 的 4 个语义属性 + func_type。"""
    from ..ontology.modules import code_structure
    repos = g.by_type("CodeRepository")
    index: Dict[str, Dict[str, Any]] = {}
    owner: Dict[str, str] = {}
    for r in repos:
        lp = r.attrs.get("local_path") or ""
        if not lp or not Path(lp).exists():
            continue
        try:
            st = code_structure(lp, max_files=max_files,
                                max_symbols=max_symbols)
        except Exception:  # noqa: BLE001
            continue
        for sym in st.get("symbols") or []:
            for key in (sym.get("qualified"), sym.get("name")):
                if key:
                    index.setdefault(str(key), sym)
                    owner.setdefault(str(key), r.id)
    n = 0
    for f in g.by_type("CodeFunction"):
        name = str(f.attrs.get("name") or f.label)
        sym = index.get(name)
        if not sym:
            continue
        doc = (sym.get("doc") or "").strip()
        f.attrs["purpose"] = (doc.split(".")[0][:80] or f"实现 {name} 逻辑")
        f.attrs["comment"] = doc
        f.attrs["params"] = sym.get("params", "")
        f.attrs["returns"] = sym.get("returns", "")
        f.attrs["func_type"] = sym.get("func_type", "helper")
        f.attrs["lineno"] = sym.get("lineno", 0)
        f.attrs["module_path"] = sym.get("file", "")
        rid = owner.get(name)
        if rid:
            g.assert_rel(rid, f.id, "HAS_FUNCTION")
        n += 1
    return {"codefunction_ast_refined": n}


def build_has_function(g: Any) -> Dict[str, int]:
    """仓库 → 函数：按 module_path 归属到对应本地仓库。"""
    repos = g.by_type("CodeRepository")
    n = 0
    for f in g.by_type("CodeFunction"):
        rid = _repo_of(f.attrs.get("module_path") or "", repos)
        if rid:
            g.assert_rel(rid, f.id, "HAS_FUNCTION")
            n += 1
    return {"has_function": n}


def fill_keywords(g: Any, *, top: int = 8) -> Dict[str, int]:
    """规则 TF-IDF（词频 × 逆文档频率）填 Paper.keywords，不需要 LLM。"""
    papers = g.by_type("Paper")
    docs, df = {}, collections.Counter()
    for p in papers:
        text = " ".join(str(p.attrs.get(k) or "") for k in
                        ("title", "research_question", "why_hard",
                         "problem_category"))
        toks = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", text.lower())
                if w not in STOP]
        docs[p.id] = toks
        for w in set(toks):
            df[w] += 1
    n = 0
    for p in papers:
        toks = docs.get(p.id) or []
        if not toks:
            continue
        tf = collections.Counter(toks)
        import math
        scored = [(w, c * math.log((1 + len(papers)) / (1 + df[w])))
                  for w, c in tf.items()]
        scored.sort(key=lambda x: -x[1])
        kws = [w for w, _ in scored[:top]]
        if kws:
            p.attrs["keywords"] = kws
            n += 1
    return {"keywords_filled": n}


def build_subclass_of(g: Any) -> Dict[str, int]:
    """算法改进链：Paper 的 RELATED_TO 里指向 Algorithm 的边 → SUBCLASS_OF。"""
    n = 0
    for p in g.by_type("Paper"):
        algs = [a.target for a in g.outgoing(p.id)
                if a.relation == "RELATED_TO" and a.target in g.nodes
                and g.nodes[a.target].type == "Algorithm"]
        own = [a.target for a in g.outgoing(p.id)
               if a.relation == "PROPOSES_METHOD" and a.target in g.nodes]
        for src in own:
            for base in algs:
                if src == base:
                    continue
                g.assert_rel(src, base, "SUBCLASS_OF")
                n += 1
    return {"subclass_of": n}


def derive_algorithm_evaluated_on(g: Any) -> Dict[str, int]:
    """算法级 EVALUATED_ON：Paper-EVALUATED_ON->Benchmark + PROPOSES_METHOD 派生。"""
    n = 0
    for p in g.by_type("Paper"):
        algs = [a.target for a in g.outgoing(p.id)
                if a.relation == "PROPOSES_METHOD" and a.target in g.nodes]
        bms = [a.target for a in g.outgoing(p.id)
               if a.relation == "EVALUATED_ON" and a.target in g.nodes]
        for alg in algs:
            for bm in bms:
                g.assert_rel(alg, bm, "EVALUATED_ON")
                n += 1
    return {"algorithm_evaluated_on": n}


def fill_algorithm_attrs(g: Any, legacy: Any = None) -> Dict[str, int]:
    """applicable_to / limitations 从旧图同名算法节点补（有则带过来）。"""
    if legacy is None:
        return {"skipped": "no_legacy"}
    src = {n.label.strip().lower(): n for n in legacy.by_type("Algorithm")}
    n = 0
    for a in g.by_type("Algorithm"):
        old = src.get(a.label.strip().lower())
        if not old:
            continue
        for k in ("applicable_to", "limitations", "why_it_works"):
            v = old.attrs.get(k)
            if v and k not in a.attrs:
                a.attrs[k] = v
                n += 1
    return {"algorithm_attrs_filled": n}


def enrich(g: Any, *, legacy: Any = None) -> Dict[str, Any]:
    rep: Dict[str, Any] = {}
    for fn in (fill_repo_url, fill_license, refine_code_functions,
               fill_keywords, build_subclass_of,
               derive_algorithm_evaluated_on):
        try:
            rep.update(fn(g))
        except Exception as exc:  # noqa: BLE001
            rep[fn.__name__] = f"error:{type(exc).__name__}:{exc}"[:120]
    try:
        rep.update(fill_algorithm_attrs(g, legacy))
    except Exception as exc:  # noqa: BLE001
        rep["fill_algorithm_attrs"] = f"error:{type(exc).__name__}"
    return rep
