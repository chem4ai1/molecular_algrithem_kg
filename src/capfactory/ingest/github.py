"""GitHub 仓库接入：克隆、代码索引、数据集发现.

设计取舍
--------
- 使用 ``git clone --depth=1`` 而非 GitHub API：不受 60 次/小时 的匿名限流影响；
- 代码索引只保留实现类文件（.py/.ipynb 转换），并对单文件做体积上限保护；
- 数据集发现采用「表头嗅探」，兼容 CSV/TSV/FASTA 三种常见格式。
"""

from __future__ import annotations

import csv
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config import Settings, get_settings
from ..utils import ensure_dir, human_bytes, read_text, slugify

logger = logging.getLogger(__name__)

CODE_EXTS = {".py", ".cfg", ".toml", ".yaml", ".yml", ".json", ".sh", ".md", ".txt", ".r"}
SEQ_COL_HINTS = ("sequence", "seq", "peptide", "smiles", "protein")
LABEL_COL_HINTS = ("label", "class", "target", "toxic", "activity", "y", "outcome", "hemolytic")


@dataclass
class RepoInfo:
    """仓库摘要信息。"""

    url: str = ""
    path: str = ""
    name: str = ""
    readme: str = ""
    files: List[str] = field(default_factory=list)
    datasets: List[Dict[str, Any]] = field(default_factory=list)
    requirements: List[str] = field(default_factory=list)
    entry_points: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url, "path": self.path, "name": self.name,
            "files": self.files, "datasets": self.datasets,
            "requirements": self.requirements, "entry_points": self.entry_points,
        }


def repo_slug(url: str) -> str:
    """``https://github.com/owner/name`` → ``owner_name``。"""
    parts = url.rstrip("/").replace(".git", "").split("/")
    return slugify("_".join(parts[-2:]) if len(parts) >= 2 else parts[-1])


def download_tarball(url: str, target: Path, timeout: int = 420) -> Optional[Path]:
    """通过 codeload 下载仓库 tar.gz（git 协议被墙/超时时的可靠回退）。"""
    import io
    import shutil
    import tarfile

    import requests

    parts = url.rstrip("/").replace(".git", "").split("/")
    if len(parts) < 2:
        return None
    owner, repo = parts[-2], parts[-1]
    target = Path(target)
    for branch in ("main", "master"):
        api = f"https://codeload.github.com/{owner}/{repo}/tar.gz/refs/heads/{branch}"
        logger.info("尝试 tarball 下载：%s", api)
        try:
            resp = requests.get(api, timeout=timeout, stream=True)
            if resp.status_code != 200:
                continue
            buf = io.BytesIO()
            for chunk in resp.iter_content(chunk_size=1 << 16):
                if chunk:
                    buf.write(chunk)
            buf.seek(0)
            tmp_dir = target.parent / f".tmp_{target.name}"
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)
            tmp_dir.mkdir(parents=True, exist_ok=True)
            with tarfile.open(fileobj=buf, mode="r:gz") as tar:
                members = [m for m in tar.getmembers() if m.isfile()]
                top = {m.name.split("/")[0] for m in members}
                root = top.pop() if len(top) == 1 else ""
                for m in members:
                    rel = m.name[len(root) + 1:] if root and m.name.startswith(root + "/") else m.name
                    if not rel or rel.startswith("."):
                        continue
                    dest = tmp_dir / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    src = tar.extractfile(m)
                    if src:
                        dest.write_bytes(src.read())
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            tmp_dir.rename(target)
            logger.info("tarball 解压完成：%s（%d 文件）", target, len(members))
            return target
        except Exception as exc:
            logger.warning("tarball 下载失败 %s：%s", api, exc)
    return None


def clone_repo(url: str, dest_root: Path, timeout: int = 45) -> Optional[Path]:
    """获取仓库（本地目录 > 浅克隆 > tarball）。已存在则直接复用。"""
    local = Path(url)
    if local.exists() and local.is_dir():
        logger.info("使用本地仓库目录：%s", local)
        return local
    dest_root = ensure_dir(Path(dest_root))
    target = dest_root / repo_slug(url)
    if target.exists() and any(target.iterdir()):
        logger.info("仓库已存在，复用：%s", target)
        return target
    token = os.getenv("GITHUB_TOKEN", "").strip()
    clone_url = url
    if token and "github.com" in url and "@" not in url:
        clone_url = url.replace("https://", f"https://{token}@")
    cmd = ["git", "clone", "--depth", "1", "--single-branch", clone_url, str(target)]
    logger.info("克隆仓库：%s", url)
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout, text=True)
        if proc.returncode == 0:
            if token:
                subprocess.run(["git", "-C", str(target), "remote", "set-url", "origin", url],
                               capture_output=True)
            return target
        logger.warning("克隆失败 %s: %s", url, (proc.stderr or "")[:200])
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("克隆超时/异常 %s：%s，回退 tarball", url, exc)
    # 清掉半成品目录
    if target.exists():
        import shutil

        shutil.rmtree(target, ignore_errors=True)
    return download_tarball(url, target)


def _iter_files(root: Path, exts: set, max_files: int, max_bytes: int) -> List[Tuple[Path, int]]:
    out: List[Tuple[Path, int]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__", "node_modules", ".ipynb_checkpoints"}]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix.lower() not in exts:
                continue
            try:
                size = p.stat().st_size
            except OSError:
                continue
            if size > max_bytes:
                continue
            out.append((p, size))
            if len(out) >= max_files:
                return out
    return out


def sniff_dataset(path: Path, max_rows: int = 3) -> Optional[Dict[str, Any]]:
    """嗅探数据文件，返回 ``{path, format, columns, seq_col, label_col, n_rows}``.

    支持三种形态：
    1. 带表头的 CSV/TSV（含序列列、标签列）；
    2. 无表头的单列序列文件（每行一条肽序列，标签由文件名 pos/neg 推断）；
    3. FASTA。
    """
    suffix = path.suffix.lower()
    if suffix in {".fasta", ".fa"}:
        text = read_text(path, 4000)
        n = len(re.findall(r"^>", text, re.MULTILINE))
        return {"path": str(path), "format": "fasta", "columns": [], "seq_col": "sequence",
                "label_col": "", "n_rows": n, "size": human_bytes(path.stat().st_size)}
    if suffix not in {".csv", ".tsv", ".txt"}:
        return None
    if path.stat().st_size == 0:
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="ignore", newline="") as f:
            sample = f.read(4000)
            f.seek(0)
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;") if ("," in sample or "\t" in sample or ";" in sample) else csv.excel
            reader = csv.reader(f, dialect)
            first = next(reader, [])
            rows = [r for _, r in zip(range(max_rows), reader)]
    except (csv.Error, OSError, StopIteration):
        return None
    if not first:
        return None

    header_text = ",".join(first).strip()
    looks_like_header = not re.fullmatch(r"[ACDEFGHIKLMNPQRSTVWYXBZUO,\t; ]+", header_text.upper())

    if looks_like_header and len(first) >= 2:
        header = first
        lower = [h.strip().lower() for h in header]
        seq_col = next((h for h in lower if any(k == h or k in h for k in SEQ_COL_HINTS)), "")
        label_col = next((h for h in lower if any(k == h or k in h for k in LABEL_COL_HINTS)), "")
        if seq_col and not label_col and len(lower) == 2:
            label_col = next(h for h in lower if h != seq_col)
        if not seq_col:
            longest = max(range(len(header)), key=lambda i: sum(len(r[i]) for r in rows if i < len(r)))
            if rows and all(re.fullmatch(r"[ACDEFGHIKLMNPQRSTVWYXBZUO]+", (r[longest] or "").strip().upper())
                            for r in rows if longest < len(r)):
                seq_col = lower[longest]
        if not seq_col:
            return None
        n_rows = 0
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                n_rows = sum(1 for _ in f) - 1
        except OSError:
            pass
        return {
            "path": str(path), "format": suffix.lstrip("."), "columns": header,
            "seq_col": seq_col, "label_col": label_col, "n_rows": max(n_rows, 0),
            "size": human_bytes(path.stat().st_size), "label_from_name": False,
        }

    # 无表头：单列序列文件（首行即数据）
    values = [row[0].strip().upper() for row in ([first] + rows) if row]
    if values and all(re.fullmatch(r"[ACDEFGHIKLMNPQRSTVWYXBZUO]{2,}", v) for v in values):
        n_rows = 0
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                n_rows = sum(1 for line in f if line.strip())
        except OSError:
            pass
        name = path.stem.lower()
        label_hint = ""
        if re.search(r"(^|[_\-.])pos|toxin|^pos", name) and "non" not in name:
            label_hint = "1"
        elif re.search(r"(^|[_\-.])neg|non|nontox", name):
            label_hint = "0"
        return {
            "path": str(path), "format": "seq_list", "columns": ["sequence"],
            "seq_col": "sequence", "label_col": "", "label_hint": label_hint,
            "n_rows": n_rows, "size": human_bytes(path.stat().st_size),
            "label_from_name": True,
        }
    return None


def index_repo(repo_path: Path, settings: Optional[Settings] = None) -> RepoInfo:
    """建立仓库索引：README、代码文件、依赖、入口、数据集。"""
    settings = settings or get_settings()
    max_files = int(settings.ingest.get("max_repo_files", 400))
    max_bytes = int(settings.ingest.get("max_file_bytes", 200_000))

    info = RepoInfo(path=str(repo_path), name=repo_path.name)
    for name in ("README.md", "readme.md", "README.rst", "README.txt", "README"):
        p = repo_path / name
        if p.exists():
            info.readme = read_text(p, 6000)
            break

    for req in ("requirements.txt", "environment.yml", "setup.py", "pyproject.toml"):
        p = repo_path / req
        if p.exists():
            text = read_text(p, 4000)
            pkgs = re.findall(r"^\s*([A-Za-z0-9_\-]+)\s*(?:[=<>!~]=|$)", text, re.MULTILINE)
            info.requirements = sorted({p for p in pkgs if p.lower() not in {"python", "name", "version", "install_requires"}})[:20]

    files = _iter_files(repo_path, CODE_EXTS, max_files, max_bytes)
    info.files = [str(p.relative_to(repo_path)).replace("\\", "/") for p, _ in files]
    info.entry_points = [f for f in info.files if re.search(r"(main|train|predict|run|model)s?\.py$", f)][:10]

    dataset_candidates = _iter_files(repo_path, {".csv", ".tsv", ".fasta", ".fa", ".txt"}, 120, 60_000_000)
    seen = set()
    for p, _size in dataset_candidates:
        sniffed = sniff_dataset(p)
        if sniffed and sniffed["n_rows"] >= 20 and sniffed["path"] not in seen:
            sniffed["path"] = str(Path(sniffed["path"]).relative_to(repo_path)).replace("\\", "/")
            info.datasets.append(sniffed)
            seen.add(sniffed["path"])
    info.datasets.sort(key=lambda d: d.get("n_rows", 0), reverse=True)
    info.datasets = info.datasets[:8]
    logger.info("仓库索引完成：%s（%d 文件，%d 数据集）", repo_path.name, len(info.files), len(info.datasets))
    return info


def search_repos(query: str, limit: int = 5) -> List[str]:
    """通过 GitHub 搜索仓库（可能被限流，失败返回空列表）。"""
    import requests

    try:
        r = requests.get(
            "https://api.github.com/search/repositories",
            params={"q": query, "sort": "stars", "per_page": limit},
            timeout=30,
            headers={"Accept": "application/vnd.github+json"},
        )
        if r.status_code != 200:
            logger.info("GitHub 搜索不可用（HTTP %s），跳过", r.status_code)
            return []
        return [item["html_url"] for item in r.json().get("items", [])]
    except Exception as exc:
        logger.info("GitHub 搜索失败：%s", exc)
        return []


def code_context(repo: RepoInfo, repo_path: Path, keywords: List[str], max_chars: int = 6000) -> str:
    """抽取与关键词最相关的代码片段，作为代码生成的参考。"""
    if not repo_path or not Path(repo_path).exists():
        return ""
    scored: List[Tuple[int, Path]] = []
    for rel in repo_info_files(repo_path):
        text = read_text(repo_path / rel, 4000).lower()
        if not text:
            continue
        score = sum(text.count(k.lower()) for k in keywords if k)
        if score:
            scored.append((score, Path(rel)))
    scored.sort(key=lambda x: -x[0])
    chunks = []
    for score, rel in scored[:4]:
        body = read_text(repo_path / rel, max_chars // 3)
        chunks.append(f"### {rel} (score={score})\n```\n{body}\n```")
    return "\n\n".join(chunks)[:max_chars]


def group_sequence_datasets(datasets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把「pos/neg 分文件存储」的序列数据集按目录聚合成一个可训练数据集.

    典型形态（ToxinPred 系列仓库）::

        dataset/train_pos.csv  dataset/train_neg.csv
        dataset/test_pos.csv   dataset/test_neg.csv

    返回 ``[{"dir", "name", "train_pos", "train_neg", "test_pos", "test_neg", "pool": [...]}]``
    """
    groups: Dict[str, Dict[str, Any]] = {}
    for ds in datasets:
        if not (ds.get("label_from_name") or ds.get("format") == "fasta"):
            continue
        path = Path(ds["path"])
        stem = path.stem.lower()
        parent = str(path.parent)
        split = "pool"
        if re.search(r"train", stem):
            split = "train"
        elif re.search(r"test|valid|val", stem):
            split = "test"
        label = ds.get("label_hint", "")
        key = f"{split}_{'pos' if label == '1' else 'neg' if label == '0' else 'unk'}"
        g = groups.setdefault(parent, {"dir": parent, "name": Path(parent).name,
                                       "train_pos": [], "train_neg": [],
                                       "test_pos": [], "test_neg": [], "pool": [],
                                       "n_rows": 0})
        g.setdefault(key, []).append(ds)
        g["n_rows"] += int(ds.get("n_rows", 0))
    out = []
    for g in groups.values():
        if g["n_rows"] < 40:
            continue
        out.append({
            "dir": g["dir"], "name": g["name"], "n_rows": g["n_rows"],
            "train_pos": [d["path"] for d in g.get("train_pos", [])],
            "train_neg": [d["path"] for d in g.get("train_neg", [])],
            "test_pos": [d["path"] for d in g.get("test_pos", [])],
            "test_neg": [d["path"] for d in g.get("test_neg", [])],
            "pool": [d["path"] for d in g.get("pool", [])] + [d["path"] for d in g.get("train_unk", [])],
        })
    out.sort(key=lambda g: -g["n_rows"])
    return out


def repo_info_files(repo_path: Path) -> List[str]:
    """列出仓库内可读的代码文件（相对路径）。"""
    root = Path(repo_path)
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__", "node_modules"}]
        for fn in filenames:
            if Path(fn).suffix.lower() in {".py"}:
                out.append(str((Path(dirpath) / fn).relative_to(root)).replace("\\", "/"))
    return out[:200]
