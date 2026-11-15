"""论文表格抽取器：从 `Table N` 的拍平文本还原「方法 × 指标」矩阵。

PDF→MD 后表格通常被拍平成一行一个单元格，三种常见形态：

A 指标在前（MolMiner）
    Validity (%) / Frag. (%) / Uniqueness (%) / Novelty (%) / Diversity
    MolMiner (ours) / 100.0 / 0.00 / 98.5 / 99.9 / 0.8919
B 模型在前（Lingo3DMol）
    Random Test / Pocket2Mol / TargetDiff / Lingo3DMol (ours)
    Mean QED (↑) / 0.69 / 0.46 / 0.50 / 0.51
C 两列键值（AMP）
    Type / Percentage / UniProt / 4.58% / Prompt / 61.8% ...

判定靠「重复模式 (NAME, NUM×k)」+ 指标词表，不猜语义。
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

NUM_RE = re.compile(
    r"^[<>≤≥~±]?\s*\d+(?:[.,]\d+)*\s*(?:%|‰)?$|"
    r"^(?:n/?a|–|—|-|\$-\$)$", re.I)
UNIT_RE = re.compile(r"[(（]\s*(%|↑|↓|kcal/mol|Å|eV|%\))?\s*[)）]", re.I)

METRIC_WORDS = {
    "validity": "validity", "valid": "validity", "uniqueness": "uniqueness",
    "novelty": "novelty", "diversity": "diversity", "qed": "QED",
    "mae": "MAE", "rmse": "RMSE", "rmsd": "RMSD", "frag.": "frag_ratio",
    "frag": "frag_ratio", "hit rate": "hit_rate", "pass rate": "pass_rate",
    "accuracy": "accuracy", "precision": "precision", "recall": "recall",
    "f1": "F1", "auc": "AUC", "auprc": "AUPRC", "spearman": "spearman",
    "pearson": "pearson_r", "r2": "R2", "r²": "R2", "perplexity": "perplexity",
    "percentage": "percentage", "logp": "logP", "sas": "SAS",
    "improvement": "improvement", "# of molecules": "n_molecules",
}
MODEL_HINTS = re.compile(
    r"ours|baseline|random|prompt|target|pocket|diff|mol|jtnn|hier|g-sch|gdss|"
    r"lingo|vae|gan|flow|transformer|chem|graph|model|uniprot|class|cfps|"
    r"fine-?tun|distill|condition", re.I)

CAPTION_RE = re.compile(r"^\s*Table\s*[S]?(\d+)\s*[:：|]\s*(.+)$", re.I)


def _is_num(s: str) -> bool:
    return bool(NUM_RE.match(s.strip()))


def _num(s: str) -> Optional[float]:
    t = re.sub(r"[<>≤≥~±\s%‰,]", "", s).strip()
    try:
        return float(t)
    except ValueError:
        return None


def _clean_metric(s: str) -> Tuple[str, str]:
    """返回 (规范化名, 单位)。"""
    raw = s.strip().strip("|").strip()
    unit = ""
    m = re.search(r"[(（]\s*([^)）]{0,12})\s*[)）]", raw)
    if m:
        u = m.group(1).strip()
        if u in ("%", "‰", "↑", "↓", "kcal/mol", "Å", "eV"):
            unit = "%" if u in ("%", "‰") else u
        raw = raw[:m.start()].strip()
    low = raw.lower().strip()
    for k, v in METRIC_WORDS.items():
        if low.startswith(k):
            return v, unit or ("%" if "%" in s else "")
    name = re.sub(r"\b(mean|median|avg|average)\b", " ", raw, flags=re.I)
    name = re.sub(r"[^A-Za-z0-9 _\-.]", " ", name).strip()
    name = re.sub(r"\s+", " ", name)
    return (name or raw)[:40], unit or ("%" if "%" in s else "")


def _looks_metric(s: str) -> bool:
    low = s.lower()
    return any(k in low for k in METRIC_WORDS) or bool(
        re.search(r"[(（](%|↑|↓|kcal|Å|eV)", s)) or bool(
        re.search(r"\b(mae|rmse|rmsd|qed|auc|f1|r2)\b", low))


def _name_ok(s: str) -> bool:
    """单元格名：短、无句末标点、词数少。说明句一律不进 token。"""
    t = s.strip().strip("|").strip()
    if not t or _is_num(t):
        return False
    if len(t) > 40 or t.count(" ") >= 6:
        return False
    if re.search(r"[.;。]$", t) and len(t) > 12:
        return False
    return True


def _short(t: str) -> bool:
    """表格单元格：短、词少。"""
    t = t.strip()
    return bool(t) and len(t) <= 40 and t.count(" ") <= 6


def _block(lines: Sequence[str], start: int) -> List[str]:
    """caption 之后：跳过说明段 → 收短行 → 连续两行长行/两个空行即止。"""
    out: List[str] = []
    started, long_run, blank = False, 0, 0
    for j in range(start + 1, min(start + 150, len(lines))):
        t = lines[j].strip()
        if CAPTION_RE.match(t):
            break
        if not t:
            blank += 1
            if started and blank >= 2:
                break
            continue
        blank = 0
        if not started:
            if _short(t) and not re.search(r"[.;。]$", t):
                started = True
                out.append(t)
            continue
        if _short(t):
            out.append(t)
            long_run = 0
        else:
            long_run += 1
            if long_run >= 2:
                break
        if len(out) >= 160:
            break
    return out


def _tokens(rows: Sequence[str]) -> List[Tuple[str, str]]:
    toks: List[Tuple[str, str]] = []
    for t in rows:
        if _is_num(t):
            toks.append(("V", t))
        elif _name_ok(t):
            toks.append(("N", t.strip()))
    return toks


def parse_block(toks: Sequence[Tuple[str, str]]) -> Optional[Dict[str, Any]]:
    """把 token 序列还原成 {metrics, models[{name, values}]}。

    关键：第一个 VALUE 之前有 k+1 个名字（k 个表头 + 第一个行标签），
    所以先用「首个连续 VALUE 段长度」定 k，再判表头是指标还是模型。
    """
    first_v = next((i for i, t in enumerate(toks) if t[0] == "V"), None)
    if first_v is None or first_v < 2:
        return None
    names = [t[1] for t in toks[:first_v]]
    rest = list(toks[first_v:])
    vals0: List[str] = []
    while rest and rest[0][0] == "V":
        vals0.append(rest.pop(0)[1])
    k = len(vals0)
    if k == 0 or len(names) < k:
        return None
    headers = names[:k]
    first_label = names[k] if len(names) > k else ""
    models: List[Dict[str, Any]] = []
    if first_label:
        models.append({"name": first_label, "values": vals0})
    i = 0
    while i < len(rest):
        if rest[i][0] != "N":
            i += 1
            continue
        name = rest[i][1]
        vals: List[str] = []
        j = i + 1
        while j < len(rest) and rest[j][0] == "V":
            vals.append(rest[j][1])
            j += 1
        if len(vals) == k:
            models.append({"name": name, "values": vals})
        i = j
    if not models:
        return None

    # 两列键值（k=1）：names = [列头, 指标列头, 首个行标签]
    if k == 1:
        metric = first_label if _looks_metric(first_label) else (
            headers[-1] if headers else "value")
        first_row = names[k + 1] if len(names) > k + 1 else ""
        rows = []
        if first_row:
            rows.append({"name": first_row, "values": vals0})
        rows += [{"name": m["name"], "values": m["values"]}
                 for m in models if m["name"] != first_label]
        if not rows:
            return None
        return {"metrics": [_clean_metric(metric)[0]], "models": rows,
                "shape": "kv"}

    hdr_metric = sum(1 for h in headers if _looks_metric(h))
    hdr_model = sum(1 for h in headers if MODEL_HINTS.search(h))
    # A：表头是指标，行标签是模型
    if hdr_metric >= hdr_model:
        metrics = [_clean_metric(h)[0] for h in headers]
        return {"metrics": metrics, "models": models, "shape": "A"}
    # B：表头是模型，行标签是指标（值需按列重排）
    if len(models) < 1:
        return None
    labels = ([first_label] if first_label else []) + [
        m["name"] for m in models[1:]]
    table = [m["values"] for m in models]        # 行=指标, 列=模型
    n_models = len(headers)
    rows_m = []
    for ci, mname in enumerate(headers):
        vals = [row[ci] for row in table if len(row) > ci]
        rows_m.append({"name": mname, "values": vals})
    clean_labels = [lab for lab in labels
                    if lab and not re.match(
                        r"^(type|model|method|model name|methods?)$", lab, re.I)]
    return {"metrics": [_clean_metric(lab)[0] for lab in clean_labels[:n_models]]
            or [_clean_metric(lab)[0] for lab in labels],
            "models": rows_m, "shape": "B"}


BAD_METRIC = re.compile(
    r"^(id|name|model|method|type|filter|constraints?|part|std|mean|"
    r"random|molecules in|anchor|batch|hidden|encoder|decoder|"
    r"feed-forward|learning rate|epochs?|layers?)\b", re.I)


KNOWN_MODELS = re.compile(
    r"^(molgen|limo|mars|graphdf|moldqn|jtnn|hiervae|gdss|pocket2mol|"
    r"targetdiff|chemformer|chemvae|schnet|g-schnet|g-sch-net|random|"
    r"lingo3?d?mol|molminer|so3lr)$", re.I)
RANK_TOKEN = re.compile(r"^(1st|2nd|3rd|first|second|third)$", re.I)


def _usable(t: Dict[str, Any]) -> bool:
    """只保留真正的「方法 × 指标」表；拦截维度错位。"""
    ms = [m for m in t.get("metrics") or [] if m]
    models = t.get("models") or []
    if len(ms) < 1 or len(models) < 2:
        return False
    # 错位：指标列里出现大量模型名，或模型列里出现 1st/2nd/3rd 排名标记
    if sum(1 for m in ms if KNOWN_MODELS.match(m.strip())) >= 2:
        return False
    if sum(1 for m in models if RANK_TOKEN.match(m["name"].strip())) >= 2:
        return False
    if any(BAD_METRIC.match(m) for m in ms):
        return False
    hits = sum(1 for m in ms if _looks_metric(m))
    return hits >= 1 or len(ms) >= 3


def parse_tables(md: str) -> List[Dict[str, Any]]:
    lines = md.splitlines()
    out: List[Dict[str, Any]] = []
    for i, l in enumerate(lines):
        m = CAPTION_RE.match(l.strip())
        if not m:
            continue
        rows = _block(lines, i)
        parsed = parse_block(_tokens(rows))
        if not parsed or not _usable(parsed):
            continue
        out.append({"table_no": m.group(1), "caption": m.group(2)[:240],
                    **parsed})
    return out
