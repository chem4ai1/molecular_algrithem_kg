"""知识底座盘点：扫描 ``data/`` 下的论文、代码库、关联与元数据，产出可复算清单.

只读文件，不联网、不改数据。统计口径全部来自实际落盘文件：
- ``papers/papers.csv``（论文条目）、``papers/pdf/``（已下载 PDF）、``papers/abstracts/``；
- ``repos/repos.csv``（仓库条目）、``repos/src/``（已下载代码）；
- ``links.csv``（论文↔代码关联）、``knowledge_base.json``（既有汇总）。

PDF 页数**抽样**统计（全量打开 783 个 PDF 需要数十秒且无必要），
其余指标均为全量精确值；输出里会标注 ``sampled``。
"""

from __future__ import annotations

import csv
import json
import math
import random
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..utils import now_iso

CODE_EXTS = {
    ".py": "Python", ".ipynb": "Jupyter", ".js": "JavaScript", ".ts": "TypeScript",
    ".java": "Java", ".c": "C", ".h": "C/C++ header", ".cpp": "C++", ".cc": "C++",
    ".cu": "CUDA", ".rs": "Rust", ".go": "Go", ".rb": "Ruby", ".jl": "Julia",
    ".R": "R", ".sh": "Shell", ".m": "MATLAB/ObjC", ".scala": "Scala", ".lua": "Lua",
}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build"}


def _rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _sample_pdf_pages(pdfs: List[Path], k: int = 20) -> Dict[str, Any]:
    """抽样估算 PDF 页数（不引入新依赖，用 PyMuPDF）。"""
    import random
    picked = random.Random(42).sample(pdfs, min(k, len(pdfs)))
    pages: List[int] = []
    try:
        import fitz  # PyMuPDF
    except Exception:
        return {"sampled": 0, "mean_pages": None, "note": "PyMuPDF 不可用"}
    for p in picked:
        try:
            with fitz.open(p) as doc:
                pages.append(doc.page_count)
        except Exception:
            continue
    if not pages:
        return {"sampled": 0, "mean_pages": None}
    return {"sampled": len(pages), "mean_pages": round(sum(pages) / len(pages), 2),
            "median_pages": sorted(pages)[len(pages) // 2],
            "estimated_total_pages": int(sum(pages) / len(pages) * len(pdfs))}


def _scan_code(root: Path) -> Dict[str, Any]:
    """遍历代码库，按扩展名统计语言与文件数（跳过 .git 等）。"""
    langs: Counter = Counter()
    n_files = 0
    n_repos = 0
    per_repo: List[Dict[str, Any]] = []
    if not root.is_dir():
        return {"n_repos": 0, "languages": {}, "repos": []}
    for repo in sorted(p for p in root.iterdir() if p.is_dir()):
        n_repos += 1
        files = 0
        repo_langs: Counter = Counter()
        for path in repo.rglob("*"):
            if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
                continue
            files += 1
            lang = CODE_EXTS.get(path.suffix)
            if lang:
                repo_langs[lang] += 1
                langs[lang] += 1
        per_repo.append({"repo": repo.name, "files": files,
                         "size_mb": round(sum(_size(f) for f in repo.rglob("*")
                                              if f.is_file()) / 1e6, 2),
                         "top_language": (repo_langs.most_common(1)[0][0]
                                          if repo_langs else "unknown")})
        n_files += files
    return {"n_repos": n_repos, "n_files": n_files,
            "languages": dict(langs.most_common(12)),
            "repos": sorted(per_repo, key=lambda x: -x["files"])[:90]}


def scan(data_dir: str | Path = "/home/zengshuxin/xKG-main/data") -> Dict[str, Any]:
    """盘点知识底座，返回结构化清单。"""
    root = Path(data_dir)
    papers = _rows(root / "papers/papers.csv")
    repos = _rows(root / "repos/repos.csv")
    links = _rows(root / "links.csv")
    pdf_dir = root / "papers/pdf"
    abs_dir = root / "papers/abstracts"
    pdfs = sorted(pdf_dir.glob("*.pdf")) if pdf_dir.is_dir() else []
    abstracts = {p.stem for p in abs_dir.glob("*.json")} if abs_dir.is_dir() else set()
    pdf_stems = {p.stem for p in pdfs}

    # 论文条目与已下载 PDF 的对齐
    by_arxiv = {r.get("arxiv_id", "").strip(): r for r in papers if r.get("arxiv_id")}
    matched = [a for a in pdf_stems if a in by_arxiv]
    orphan_pdfs = sorted(a for a in pdf_stems if a not in by_arxiv)
    with_pdf_rows = [r for r in papers if str(r.get("has_pdf", "")).strip() in ("1", "True", "true")]

    # 领域 / 算法 / 年份分布（来自 papers.csv）
    dom: Counter = Counter()
    algo: Counter = Counter()
    year: Counter = Counter()
    for r in papers:
        if r.get("domain"):
            dom[r["domain"]] += 1
        for a in (r.get("algorithms") or "").split(";"):
            if a.strip():
                algo[a.strip()] += 1
        if r.get("year", "").isdigit():
            year[r["year"]] += 1

    code = _scan_code(root / "repos/src")
    repo_status = Counter(r.get("download_status", "") for r in repos)
    domains_map, algos_map = {}, {}
    kb_path = root / "knowledge_base.json"
    if kb_path.exists():
        try:
            kb = json.loads(kb_path.read_text(encoding="utf-8"))
            domains_map = kb.get("domain_names") or {}
            algos_map = kb.get("algo_names") or {}
        except json.JSONDecodeError:
            pass

    pdf_bytes = sum(_size(p) for p in pdfs)
    code_bytes = sum(_size(f) for f in (root / "repos/src").rglob("*")
                     if f.is_file()) if (root / "repos/src").is_dir() else 0

    inv = {
        "generated_at": now_iso(),
        "root": str(root),
        "papers": {
            "n_rows": len(papers),
            "n_with_arxiv": sum(1 for r in papers if r.get("arxiv_id")),
            "n_with_code_url": sum(1 for r in papers if r.get("code_urls")),
            "n_has_pdf_flag": len(with_pdf_rows),
            "n_pdf_files": len(pdfs),
            "pdf_bytes": pdf_bytes,
            "pdf_human": _human(pdf_bytes),
            "n_abstracts": len(abstracts),
            "n_pdf_matched_to_row": len(matched),
            "n_pdf_orphan": len(orphan_pdfs),
            "orphan_examples": orphan_pdfs[:10],
            "n_pdf_without_abstract": len([a for a in pdf_stems if a not in abstracts]),
            "page_sampling": _sample_pdf_pages(pdfs),
        },
        "repos": {
            "n_rows": len(repos),
            "n_downloaded": code.get("n_repos", 0),
            "code_bytes": code_bytes,
            "code_human": _human(code_bytes),
            "n_files": code.get("n_files", 0),
            "languages": code.get("languages", {}),
            "status": dict(repo_status),
            "top_repos": code.get("repos", [])[:15],
            "n_with_license": sum(1 for r in repos if r.get("license")),
            "n_with_stars": sum(1 for r in repos if r.get("stars")),
        },
        "links": {"n_rows": len(links),
                  "n_unique_papers": len({r.get("paper_id") for r in links}),
                  "n_unique_repos": len({r.get("repo_id") for r in links})},
        "distribution": {
            "domains": {k: {"name": domains_map.get(k, k), "count": v}
                        for k, v in sorted(dom.items(), key=lambda kv: -kv[1])},
            "algorithms": {k: {"name": algos_map.get(k, k), "count": v}
                           for k, v in sorted(algo.items(), key=lambda kv: -kv[1])},
            "years": dict(sorted(year.items(), key=lambda kv: -int(kv[0]))[:12]),
        },
        "coverage": {},
    }
    # 覆盖缺口
    p = inv["papers"]
    inv["coverage"] = {
        "pdf_rate_of_records": round(p["n_pdf_files"] / max(p["n_rows"], 1), 4),
        "absolute_pdf_rate": round(p["n_pdf_files"] / max(len(with_pdf_rows), 1), 4),
        "abstract_rate_of_pdf": round(1 - p["n_pdf_without_abstract"] / max(p["n_pdf_files"], 1), 4),
        "repo_download_rate": round(inv["repos"]["n_downloaded"] / max(inv["repos"]["n_rows"], 1), 4),
        "link_rate": round(inv["links"]["n_rows"] / max(inv["papers"]["n_rows"], 1), 4),
    }
    return inv


def to_markdown(inv: Dict[str, Any]) -> str:
    p, r, d = inv["papers"], inv["repos"], inv["distribution"]
    ps = p["page_sampling"]
    lines = [
        "# 知识底座盘点", "",
        f"> 生成时间：{inv['generated_at']} ｜ 根目录 `{inv['root']}`", "",
        "## 1. 总览", "",
        "| 维度 | 值 |", "|---|---|",
        f"| 论文条目 | {p['n_rows']} |",
        f"| 已下载 PDF | {p['n_pdf_files']}（{p['pdf_human']}） |",
        f"| 已下载摘要 | {p['n_abstracts']} |",
        f"| 代码仓库条目 | {r['n_rows']} |",
        f"| 已下载代码库 | {r['n_downloaded']}（{r['code_human']}，{r['n_files']} 文件） |",
        f"| 论文↔代码关联 | {inv['links']['n_rows']} |",
        f"| 页数抽样 | {ps.get('sampled')} 篇，均值 {ps.get('mean_pages')} 页，"
        f"估算总页数 ≈ {ps.get('estimated_total_pages')} |", "",
        "## 2. 覆盖与缺口", "",
        "| 指标 | 值 |", "|---|---:|",
        f"| PDF / 条目 | {inv['coverage']['pdf_rate_of_records']:.2%} |",
        f"| PDF / 标记有 PDF 的条目 | {inv['coverage']['absolute_pdf_rate']:.2%} |",
        f"| 摘要 / PDF | {inv['coverage']['abstract_rate_of_pdf']:.2%} |",
        f"| 代码下载率 | {inv['coverage']['repo_download_rate']:.2%} |",
        f"| 关联 / 条目 | {inv['coverage']['link_rate']:.2%} |",
        f"| PDF 无对应条目 | {p['n_pdf_orphan']} |", "",
        "## 3. 领域分布（已标注）", "",
        "| 代码 | 领域 | 论文数 |", "|---|---|---:|",
    ]
    for k, v in list(d["domains"].items()):
        lines.append(f"| {k} | {v['name']} | {v['count']} |")
    lines += ["", "## 4. 算法族分布（已标注）", "",
              "| 代码 | 算法族 | 论文数 |", "|---|---|---:|"]
    for k, v in list(d["algorithms"].items()):
        lines.append(f"| {k} | {v['name']} | {v['count']} |")
    lines += ["", "## 5. 代码库语言分布", "", "| 语言 | 文件数 |", "|---|---:|"]
    for k, v in r["languages"].items():
        lines.append(f"| {k} | {v} |")
    lines += ["", "## 6. 最大的已下载仓库", "", "| 仓库 | 文件数 | 体积(MB) | 主语言 |",
              "|---|---:|---:|---|"]
    for x in r["top_repos"]:
        lines.append(f"| {x['repo']} | {x['files']} | {x['size_mb']} | {x['top_language']} |")
    lines += ["", "## 7. 年份分布", "", "| 年份 | 论文数 |", "|---|---:|"]
    for k, v in d["years"].items():
        lines.append(f"| {k} | {v} |")
    lines += ["", "> 说明：PDF 页数为抽样估计（种子 42），其余为全量精确值；"
              "未下载不等于不存在。"]
    return "\n".join(lines)


def write(inv: Optional[Dict[str, Any]] = None,
          data_dir: str | Path = "/home/zengshuxin/xKG-main/data",
          out_dir: str | Path = "storage_cf/catalog") -> Dict[str, str]:
    """扫描并落盘 ``inventory.json`` + ``INVENTORY.md``。"""
    inv = inv or scan(data_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    jp = out / "inventory.json"
    mp = out / "inventory.md"
    jp.write_text(json.dumps(inv, ensure_ascii=False, indent=2), encoding="utf-8")
    mp.write_text(to_markdown(inv), encoding="utf-8")
    return {"json": str(jp), "markdown": str(mp)}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="盘点 data/ 知识底座")
    ap.add_argument("--data", default="/home/zengshuxin/xKG-main/data")
    ap.add_argument("--out", default="storage_cf/catalog")
    a = ap.parse_args()
    print(json.dumps(write(None, a.data, a.out), ensure_ascii=False, indent=2))
