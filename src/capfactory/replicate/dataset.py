"""数据集归一化：把仓库里的「野生」数据整理成可验证的标准格式.

输出目录结构::

    <workspace>/datasets/<name>/
        dataset.json      # 元信息 + train/test 划分
        train.csv         # sequence,label
        test.csv          # sequence,label
        summary.md        # 人读摘要

支持的输入：CSV / TSV / FASTA。标签自动映射到 {0,1}。
"""

from __future__ import annotations

import csv
import logging
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..utils import ensure_dir, read_text, write_json

logger = logging.getLogger(__name__)

AA_RE = re.compile(r"^[ACDEFGHIKLMNPQRSTVWY]+$")
POSITIVE_TOKENS = ("toxin", "toxic", "amp", "antimicrobial", "hemolytic", "positive", "active", "1", "yes", "true")
NEGATIVE_TOKENS = ("non", "negative", "inactive", "0", "no", "false", "nontoxic", "non-toxic")


def _normalise_label(raw: Any) -> Optional[int]:
    """把各种标签写法映射为 0/1，无法判定返回 None。"""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    try:
        val = float(s)
        return 1 if val >= 0.5 else 0
    except ValueError:
        pass
    # 按分隔符切成词，避免 "unknown" 误命中 "no"
    tokens = [t for t in re.split(r"[^a-z0-9]+", s) if t]
    negatives = {"non", "negative", "neg", "inactive", "no", "false", "nontoxic",
                 "nontoxin", "nonamp", "non-toxic", "non_toxic"}
    positives = {"toxin", "toxic", "toxicity", "amp", "antimicrobial", "hemolytic",
                 "positive", "pos", "active", "yes", "true"}
    if any(t in negatives for t in tokens) or s in {"nontoxic", "nontoxin", "nonamp"}:
        return 0
    if any(t in positives for t in tokens):
        return 1
    return None


def load_csv(path: Path, seq_col: str, label_col: str) -> List[Tuple[str, int]]:
    """读取 CSV/TSV，返回 (sequence, label) 列表。"""
    rows: List[Tuple[str, int]] = []
    delimiter = "\t" if path.suffix.lower() in {".tsv", ".txt"} else ","
    with open(path, "r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        if not reader.fieldnames:
            return rows
        seq_key = next((k for k in reader.fieldnames if k.strip().lower() == seq_col.lower()), None)
        label_key = next((k for k in reader.fieldnames if k.strip().lower() == label_col.lower()), None)
        if seq_key is None:
            return rows
        for row in reader:
            seq = (row.get(seq_key) or "").strip().upper()
            label = _normalise_label(row.get(label_key) if label_key else None)
            if seq and label is not None:
                rows.append((seq, label))
    return rows


def load_fasta(path: Path, positive_hint: str = "") -> List[Tuple[str, int]]:
    """读取 FASTA；标签从 header 关键词或文件名推断。"""
    text = read_text(path)
    rows: List[Tuple[str, int]] = []
    header, buf = "", []
    default_label = None
    name = path.stem.lower()
    if any(t in name for t in ("non", "neg")):
        default_label = 0
    elif any(t in name for t in ("toxin", "toxic", "pos", "amp")):
        default_label = 1

    def flush() -> None:
        if not buf:
            return
        seq = "".join(buf).upper()
        label = default_label
        low = header.lower()
        if "non-toxin" in low or "non_toxin" in low or "negative" in low:
            label = 0
        elif "toxin" in low or "positive" in low or "amp" in low:
            label = 1
        if label is not None and seq:
            rows.append((seq, label))

    for line in text.splitlines():
        if line.startswith(">"):
            flush()
            header, buf = line[1:], []
        elif line.strip():
            buf.append(re.sub(r"[^A-Za-z]", "", line.strip()))
    flush()
    return rows


def clean_rows(rows: List[Tuple[str, int]], min_len: int = 3, max_len: int = 200) -> Tuple[List[Tuple[str, int]], Dict[str, int]]:
    """清洗：去非法字符、长度过滤、去重、冲突消解。"""
    stats = {"raw": len(rows), "invalid": 0, "too_short": 0, "too_long": 0, "duplicates": 0, "conflicts": 0}
    seen: Dict[str, int] = {}
    conflicts = set()
    cleaned: List[Tuple[str, int]] = []
    for seq, label in rows:
        seq = re.sub(r"[^ACDEFGHIKLMNPQRSTVWY]", "", seq.upper())
        if not AA_RE.match(seq or ""):
            stats["invalid"] += 1
            continue
        if len(seq) < min_len:
            stats["too_short"] += 1
            continue
        if len(seq) > max_len:
            stats["too_long"] += 1
            continue
        if seq in seen:
            if seen[seq] != label:
                conflicts.add(seq)
                stats["conflicts"] += 1
            else:
                stats["duplicates"] += 1
            continue
        seen[seq] = label
        cleaned.append((seq, label))
    cleaned = [(s, l) for s, l in cleaned if s not in conflicts]
    stats["kept"] = len(cleaned)
    stats["positives"] = sum(l for _, l in cleaned)
    stats["negatives"] = len(cleaned) - stats["positives"]
    return cleaned, stats


def stratified_split(rows: List[Tuple[str, int]], test_size: float = 0.3,
                     seed: int = 42) -> Tuple[List[Tuple[str, int]], List[Tuple[str, int]]]:
    """分层划分；某一类过少时退化为随机划分。"""
    rng = random.Random(seed)
    pos = [r for r in rows if r[1] == 1]
    neg = [r for r in rows if r[1] == 0]
    if len(pos) < 4 or len(neg) < 4:
        shuffled = rows[:]
        rng.shuffle(shuffled)
        cut = max(1, int(len(shuffled) * (1 - test_size)))
        return shuffled[:cut], shuffled[cut:]
    train, test = [], []
    for group in (pos, neg):
        group = group[:]
        rng.shuffle(group)
        cut = max(1, int(len(group) * (1 - test_size)))
        train.extend(group[:cut])
        test.extend(group[cut:])
    rng.shuffle(train)
    rng.shuffle(test)
    return train, test


def load_sequence_list(path: Path, label: int, min_len: int = 3) -> List[Tuple[str, int]]:
    """读取「一行一条序列」的纯文本/CSV（无表头），并赋予统一标签。"""
    rows: List[Tuple[str, int]] = []
    text = read_text(path)
    for line in text.splitlines():
        seq = line.strip().split(",")[0].strip().upper()
        if not seq or seq.startswith(">"):
            continue
        seq = re.sub(r"[^ACDEFGHIKLMNPQRSTVWY]", "", seq)
        if len(seq) >= min_len:
            rows.append((seq, label))
    return rows


def materialise_with_split(train_rows: List[Tuple[str, int]], test_rows: List[Tuple[str, int]],
                           out_dir: Path, name: str, source: str = "") -> Optional[Dict[str, Any]]:
    """按「论文原始训练/测试集」落盘，保留原始划分，保证评测可比。"""
    train, stats_tr = clean_rows(train_rows)
    test, stats_te = clean_rows(test_rows)
    if len(train) < 20 or len(test) < 10:
        logger.warning("训练/测试样本不足（%d/%d），跳过 %s", len(train), len(test), name)
        return None
    if not any(l == 1 for _, l in test) or not any(l == 0 for _, l in test):
        logger.warning("测试集缺少某一类别，退回分层划分：%s", name)
        return materialise(train + test, out_dir, name, source=source)
    out_dir = ensure_dir(Path(out_dir))

    def dump(path: Path, data: List[Tuple[str, int]]) -> None:
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["sequence", "label"])
            writer.writerows(data)

    dump(out_dir / "train.csv", train)
    dump(out_dir / "test.csv", test)
    total = len(train) + len(test)
    pos = stats_tr["positives"] + stats_te["positives"]
    meta = {
        "name": name, "source": source, "split": "paper_original",
        "n_train": len(train), "n_test": len(test), "n_total": total,
        "stats": {"train": stats_tr, "test": stats_te},
        "train_path": str(out_dir / "train.csv"),
        "test_path": str(out_dir / "test.csv"),
        "positive_rate": round(pos / max(total, 1), 4),
    }
    write_json(out_dir / "dataset.json", meta)
    (out_dir / "summary.md").write_text(
        f"# 数据集：{name}\n\n- 来源：{source}\n- 划分：沿用仓库原始 train/test\n"
        f"- train {len(train)}（正例 {stats_tr['positives']}）/ test {len(test)}（正例 {stats_te['positives']}）\n"
        f"- 正例率：{meta['positive_rate']:.1%}\n", encoding="utf-8")
    logger.info("数据集（原始划分）已生成：%s（train=%d, test=%d）", name, len(train), len(test))
    return meta


def materialise(rows: List[Tuple[str, int]], out_dir: Path, name: str,
                source: str = "", seq_col: str = "sequence", label_col: str = "label",
                test_size: float = 0.3) -> Optional[Dict[str, Any]]:
    """把 (sequence,label) 列表落盘为标准数据集，返回元信息。"""
    if not rows:
        return None
    cleaned, stats = clean_rows(rows)
    if len(cleaned) < 20:
        logger.warning("有效样本过少（%d），跳过数据集 %s", len(cleaned), name)
        return None
    train, test = stratified_split(cleaned, test_size=test_size)
    out_dir = ensure_dir(Path(out_dir))

    def dump(path: Path, data: List[Tuple[str, int]]) -> None:
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["sequence", "label"])
            writer.writerows(data)

    dump(out_dir / "train.csv", train)
    dump(out_dir / "test.csv", test)

    meta = {
        "name": name,
        "source": source,
        "seq_col": seq_col,
        "label_col": label_col,
        "n_train": len(train),
        "n_test": len(test),
        "n_total": len(cleaned),
        "stats": stats,
        "train_path": str(out_dir / "train.csv"),
        "test_path": str(out_dir / "test.csv"),
        "positive_rate": round(stats["positives"] / max(len(cleaned), 1), 4),
    }
    write_json(out_dir / "dataset.json", meta)

    summary = (
        f"# 数据集：{name}\n\n"
        f"- 来源：{source}\n"
        f"- 样本：{meta['n_total']}（正例 {stats['positives']} / 负例 {stats['negatives']}，"
        f"正例率 {meta['positive_rate']:.1%}）\n"
        f"- 划分：train {len(train)} / test {len(test)}\n"
        f"- 清洗：去重 {stats['duplicates']}，标签冲突 {stats['conflicts']}，"
        f"非法 {stats['invalid']}，过短 {stats['too_short']}，过长 {stats['too_long']}\n"
    )
    (out_dir / "summary.md").write_text(summary, encoding="utf-8")
    logger.info("数据集已生成：%s（train=%d, test=%d）", name, len(train), len(test))
    return meta
