"""P2 · 数据构造：从论文抽取 DatasetSpec + 真实去泄漏检查。

两部分：
1. extract_dataset_spec(md)  从论文正文抽数据源/去泄漏规则/划分（可跑 52 篇）
2. check_leakage(train, test) 用 RDKit Morgan 指纹真算 Tanimoto（需 rdkit）
"""
from __future__ import annotations
import re
from typing import Any, Dict, List, Optional

DB_PATTERNS = [
    ("ZINC", r"\bZINC\b"), ("ChEMBL", r"\bChEMBL\b"), ("PubChem", r"\bPubChem\b"),
    ("Enamine", r"\bEnamine\b"), ("USPTO", r"\bUSPTO\b"), ("GEOM", r"\bGEOM\b"),
    ("QM9", r"\bQM9\b"), ("GuacaMol", r"\bGuacaMol\b"), ("MoleculeNet", r"\bMoleculeNet\b"),
    ("CrossDocked", r"\bCrossDocked\b"), ("BindingDB", r"\bBindingDB\b"),
    ("PDB", r"\bPDB\b"), ("ChemCoTBench", r"\bChemCoTBench\b"),
]
DEDUP_PATTERNS = [
    re.compile(r"Tanimoto[^.]{0,120}?([01]\.\d+)", re.I),
    re.compile(r"([01]\.\d+)[^.]{0,40}?Tanimoto", re.I),
    re.compile(r"similarity[^.]{0,60}?(?:below|less than|<|≥|>=)\s*([01]\.\d+)", re.I),
    re.compile(r"sequence identity[^.]{0,40}?([0-9]{2})\s*%", re.I),
    re.compile(r"scaffold split", re.I),
]
SPLIT_PATTERNS = [
    re.compile(r"(?:split|ratio)[^.]{0,40}?(\d{2,3})\s*[/:：]\s*(\d{1,2})\s*[/:：]\s*(\d{1,2})", re.I),
    re.compile(r"(?:train|training)[^.]{0,30}?(\d{2,3})\s*%[^.]{0,40}?(?:valid|test)", re.I),
]


def _normalize_pdf_text(t: str) -> str:
    """修复 PDF 转文字把小数拆开的问题：'0 _._ 6' → '0.6'。"""
    t = re.sub(r"(\d)\s*[_\s]*\.\s*[_\s]*(\d)", r"\1.\2", t)
    return t


def extract_dataset_spec(md_text: str) -> Dict[str, Any]:
    """从论文正文抽数据构造要点（确定性，不调 LLM）。"""
    text = _normalize_pdf_text(md_text or "")
    sources = [name for name, pat in DB_PATTERNS if re.search(pat, text, re.I)]
    dedup = ""
    for pat in DEDUP_PATTERNS:
        m = pat.search(text)
        if m:
            dedup = m.group(0)[:100]
            break
    split = ""
    for pat in SPLIT_PATTERNS:
        m = pat.search(text)
        if m:
            split = m.group(0)[:60]
            break
    # 规模：抓 "N molecules/samples/examples"
    size_m = re.search(r"([0-9][0-9,\.]{2,})\s*(?:molecules|samples|examples|compounds|pairs)",
                       text, re.I)
    return {"sources": sources, "dedup_rule": dedup, "split": split,
            "size_hint": size_m.group(0) if size_m else "",
            "has_dedup": bool(dedup)}


# ---------- 真实去泄漏（RDKit） ----------
def _fp(smiles: str):
    from rdkit import Chem
    from rdkit.Chem import rdFingerprintGenerator as rg
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    gen = rg.GetMorganGenerator(radius=2, fpSize=2048)
    return gen.GetFingerprint(mol)


def check_leakage(train_smiles: List[str], test_smiles: List[str],
                  *, threshold: float = 0.6) -> Dict[str, Any]:
    """真算 Tanimoto：返回泄漏样本与统计。"""
    from rdkit import DataStructs
    train_fps = [(s, _fp(s)) for s in train_smiles]
    train_fps = [(s, f) for s, f in train_fps if f is not None]
    leaked, checked, invalid = [], 0, 0
    for s in test_smiles:
        f = _fp(s)
        if f is None:
            invalid += 1
            continue
        checked += 1
        best, best_s = 0.0, ""
        for ts, tf in train_fps:
            sim = DataStructs.TanimotoSimilarity(f, tf)
            if sim > best:
                best, best_s = sim, ts
        if best >= threshold:
            leaked.append({"test": s, "train": best_s, "tanimoto": round(best, 3)})
    return {"n_train": len(train_fps), "n_test": checked, "n_invalid": invalid,
            "threshold": threshold, "n_leaked": len(leaked),
            "leak_rate": round(len(leaked) / max(checked, 1), 3),
            "examples": leaked[:5],
            "pass": len(leaked) == 0}
