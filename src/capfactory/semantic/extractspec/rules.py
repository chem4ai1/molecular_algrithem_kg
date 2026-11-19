"""声明式规则引擎：YAML 声明字段→规则类型，Python 只实现规则类型。

支持的规则类型：
- db_names       数据源名（ZINC/ChEMBL/...）
- regex          正则捕获（patterns + group）
- hyperparam_list 超参名+值
- md_tables      markdown 表格 → [{label,columns,rows}]
- num_list       数值列表

YAML 用法：
  rules:
    preprocess: normalize_pdf      # 可选：先修 PDF 拆字
    data_sources: {type: db_names}
    dedup_rule:   {type: regex, patterns: ["Tanimoto[^.]{0,120}?([01]\\.\\d+)"], group: 0}
    hyperparams:  {type: hyperparam_list, max_items: 6}
    result_tables:{type: md_tables, max_tables: 3}
"""
from __future__ import annotations
import re
from typing import Any, Dict, List

DB_NAMES = ("ZINC", "ChEMBL", "PubChem", "Enamine", "USPTO", "GEOM", "QM9",
            "GuacaMol", "MoleculeNet", "CrossDocked", "BindingDB", "PDB",
            "ChemCoTBench", "SIDER", "Tox21", "FreeSolv", "Lipophilicity")

_HP_KW = (r"number of iterations|number of steps|max(?:imum)? steps|temperature|"
          r"top-?k|learning rate|batch size|number of samples|sampling budget|"
          r"oracle budget|beam size|threshold|epochs")

_NUMISH = re.compile(r"^[\*_\s]*[+-]?\d+(\.\d+)?\s*[%MKkGmBb\*_\s]*$")


def normalize_pdf(text: str) -> str:
    """修 PDF 转文字把小数拆开：'0 _._ 6' → '0.6'。"""
    return re.sub(r"(\d)\s*[_\s]*\.\s*[_\s]*(\d)", r"\1.\2", text or "")


def _db_names(text: str, cfg: Dict[str, Any]) -> List[str]:
    return [n for n in (cfg.get("candidates") or DB_NAMES)
            if re.search(rf"\b{re.escape(n)}\b", text, re.I)]


def _regex(text: str, cfg: Dict[str, Any]) -> str:
    for pat in cfg.get("patterns") or []:
        m = re.search(pat, text, re.I | re.S)
        if m:
            g = int(cfg.get("group") or 0)
            try:
                return (m.group(g) or "").strip()[:cfg.get("max_chars", 120)]
            except (IndexError, AttributeError):
                return m.group(0).strip()[:cfg.get("max_chars", 120)]
    return ""


def _hyperparam_list(text: str, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    pat = re.compile(rf"\b({_HP_KW})\b[^.]{{0,60}}?([0-9]+(?:\.[0-9]+)?%?)", re.I)
    out = []
    for m in pat.finditer(text):
        out.append({"param": m.group(1).lower(), "value": m.group(2),
                    "context": text[max(0, m.start() - 30):m.end()].replace("\n", " ")[:100]})
        if len(out) >= int(cfg.get("max_items") or 6):
            break
    return out


def _md_tables(text: str, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    max_tables = int(cfg.get("max_tables") or 3)
    lines = text.splitlines()
    tables, i = [], 0
    while i < len(lines) and len(tables) < max_tables:
        ln = lines[i]
        if ln.strip().startswith("|") and i + 1 < len(lines) \
                and re.match(r"^\s*\|[\s\-:|]+\|?\s*$", lines[i + 1]):
            header = [c.strip() for c in ln.strip().strip("|").split("|")]
            text_cols = sum(1 for h in header if not _NUMISH.match(h))
            if len(header) < 2 or text_cols < len(header) / 2:
                i += 1
                continue
            rows, j = [], i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                if len(cells) == len(header):
                    rows.append(cells)
                j += 1
            if rows:
                label = ""
                for k in range(max(0, i - 8), i):
                    m = re.search(r"(Table\s+\d+[^.\n]{0,60})", lines[k])
                    if m:
                        label = m.group(1).strip()
                        break
                tables.append({"label": label or f"table_{len(tables)+1}",
                               "columns": header, "rows": rows[:int(cfg.get('max_rows') or 30)]})
            i = j
        else:
            i += 1
    return tables


ENGINE = {"db_names": _db_names, "regex": _regex,
          "hyperparam_list": _hyperparam_list, "md_tables": _md_tables}


def apply_rules(spec_rules: Dict[str, Any], text: str) -> Dict[str, Any]:
    """按 YAML 的 rules 段执行，返回 {字段: 值}。"""
    if not spec_rules:
        return {}
    if spec_rules.get("preprocess") == "normalize_pdf":
        text = normalize_pdf(text)
    out: Dict[str, Any] = {}
    for field, cfg in spec_rules.items():
        if field == "preprocess" or not isinstance(cfg, dict):
            continue
        fn = ENGINE.get(cfg.get("type") or "")
        if fn is None:
            continue
        try:
            val = fn(text, cfg)
        except Exception:  # noqa: BLE001
            val = None
        if val:
            out[field] = val
    return out
