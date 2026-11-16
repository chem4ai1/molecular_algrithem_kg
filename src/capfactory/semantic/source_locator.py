"""把图节点回溯到论文原文（md）的具体行。

背景：md 里的表格已被拆成「每行一个单元格」的线性文本，
结构信息丢失，因此定位分两级：

  high   —— 找到表格块 + 模型名行 + 按表头指标序数数到该值，且字符串完全一致
  medium —— 只在表格块内找到「包含该值」的行
  low    —— 只能在全文按值/标签模糊命中

不做的事：不猜行列坐标、不在结构缺失时假装精确。
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

_TABLE_RE = re.compile(r"^\s*Table\s+(S?\d+)\s*[:.]", re.I)
_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?%?$")


@dataclass
class TableBlock:
    idx: int          # 第几个表（从 1 开始，与 table_extract:N 对应）
    label: str        # "1" / "S1"
    start: int        # 标题行号（1-based）
    end: int          # 块末行号（含）
    header: List[str] = field(default_factory=list)   # 表头词
    rows: List[int] = field(default_factory=list)     # 纯数值行号


def _read_lines(md: Path) -> List[str]:
    raw = md.read_bytes().decode("utf-8", errors="replace")
    return raw.replace("\x00", "").splitlines()


def _blocks(lines: List[str]) -> List[TableBlock]:
    """按 "Table N:" 标题切块，块到下一个标题或连续空行结束。"""
    starts = []
    for i, ln in enumerate(lines):
        m = _TABLE_RE.match(ln)
        if m and len(ln.strip()) >= 20:   # 真标题有描述，正文引用没有
            starts.append((i, m.group(1)))
    out: List[TableBlock] = []
    for k, (i, label) in enumerate(starts):
        end = starts[k + 1][0] - 1 if k + 1 < len(starts) else min(
            len(lines) - 1, i + 120)
        body = list(range(i, end + 1))
        header, rows = [], []
        for j in body:
            s = lines[j].strip()
            if not s:
                continue
            if _NUM_RE.match(s):
                rows.append(j + 1)
            elif len(s) <= 24 and not s.endswith((".", ";")):
                header.append(s)
        out.append(TableBlock(idx=k + 1, label=label, start=i + 1,
                              end=end + 1, header=header, rows=rows))
    return out


def _metric_pos(header: List[str], metric: str) -> Optional[int]:
    """在表头里找指标的位置（0-based）。支持别名与包含匹配。"""
    m = metric.lower().replace("_", " ")
    alias = {"validity": ("valid",), "uniqueness": ("unique",),
             "novelty": ("novel",), "diversity": ("divers",),
             "frag_ratio": ("frag",), "hit rate": ("hit",),
             "fold-enrichment": ("enrich",), "wasserstein distance": ("wasser",)}
    keys = alias.get(m, (m.split()[0] if m else "",))
    for i, h in enumerate(header):
        hl = h.lower()
        if any(k and k in hl for k in keys):
            return i
    return None


def _locate_cell(lines: List[str], blk: TableBlock, model: str,
                 metric: str, value: str) -> Optional[Dict[str, Any]]:
    """在表块内定位单元格：模型名行 + 表头序数 → 第 k 个数值行。"""
    v = str(value).strip().rstrip("%")
    mnorm = model.strip().lower().replace("(ours)", "").strip()
    anchor = None
    for j in range(blk.start - 1, blk.end):
        s = lines[j].strip().lower()
        if not s or len(s) > 60:
            continue
        if mnorm and (s == mnorm or mnorm in s):
            anchor = j
            break
    if anchor is None:
        # 模型名没在块内独立成行（竖排表/多级表头）：退化为块内值匹配
        for j in range(blk.start - 1, blk.end):
            if lines[j].strip().rstrip("%") == v:
                return {"line": j + 1, "confidence": "medium",
                        "snippet": lines[j].strip(),
                        "context": lines[max(0, j - 2):j + 3],
                        "table": f"Table {blk.label}", "table_start": blk.start,
                        "metric_pos": None, "reason": "value_only_in_block"}
        return None
    k = _metric_pos(blk.header, metric)
    nums = []
    for j in range(anchor + 1, min(anchor + 40, blk.end + 1)):
        s = lines[j].strip()
        if _NUM_RE.match(s):
            nums.append(j)
        elif s and nums:
            break
    if not nums:
        return None
    pick = None
    if k is not None and k < len(nums):
        cand = nums[k]
        if lines[cand].strip().rstrip("%") == v:
            pick = (cand, "high")
    if pick is None:
        for j in nums:
            if lines[j].strip().rstrip("%") == v:
                pick = (j, "medium")
                break
    if pick is None:
        return None
    ln, conf = pick
    return {"line": ln + 1, "confidence": conf,
            "snippet": lines[ln].strip(),
            "context": lines[max(0, ln - 2):ln + 3],
            "table": f"Table {blk.label}",
            "table_start": blk.start, "metric_pos": (k + 1) if k is not None else None}


def _locate_label(lines: List[str], label: str, limit: int = 12
                  ) -> List[Dict[str, Any]]:
    """按标签整词/包含匹配，返回命中行（含上下文）。"""
    key = label.strip().lower()
    if len(key) < 3:
        return []
    out = []
    for i, ln in enumerate(lines):
        if key and key in ln.lower():
            out.append({"line": i + 1, "confidence": "low",
                        "snippet": ln.strip()[:180],
                        "context": lines[max(0, i - 1):i + 2]})
            if len(out) >= limit:
                break
    return out


def _paper_of(graph, node_id: str, trace_out: Dict[str, Any]) -> str:
    for r in trace_out.get("relation_rows") or []:
        pass
    for r in trace_out.get("relations") or []:
        if r.get("arxiv_id"):
            return str(r["arxiv_id"])
    n = graph.nodes.get(node_id)
    if n is not None and n.attrs.get("paper_id"):
        return str(n.attrs["paper_id"]).split(":")[-1]
    if n is not None and n.attrs.get("arxiv_id"):
        return str(n.attrs["arxiv_id"])
    return ""


def locate(graph, node_id: str, *, md_dir: Any = "data/docx",
           reports: Optional[Dict[str, Any]] = None,
           max_hits: int = 8) -> Dict[str, Any]:
    """节点 → 原文行号。返回 {"paper","md","hits","unresolved"}。"""
    from .provenance import trace
    tr = trace(graph, node_id, reports if reports is not None else _empty())
    if not tr.get("found"):
        return {"node_id": node_id, "found": False, "hits": [],
                "unresolved": ["node_not_in_graph"]}
    n = graph.nodes[node_id]
    aid = _paper_of(graph, node_id, tr)
    md = Path(md_dir) / (aid + ".md")
    if not aid or not md.exists():
        return {"node_id": node_id, "found": True, "type": n.type,
                "label": n.label, "paper": aid, "md": str(md),
                "hits": [], "unresolved": ["md_missing"]}
    lines = _read_lines(md)
    blocks = _blocks(lines)
    hits: List[Dict[str, Any]] = []
    unresolved: List[str] = []
    cells = tr.get("cells") or []
    for c in cells[:max_hits]:
        prov = str(c.get("provenance") or "")
        m = re.match(r"table_extract:(\d+)", prov)
        if not m:
            unresolved.append(f"no_table_ref:{c.get('cell_id')}")
            continue
        k = int(m.group(1)) - 1
        model = str(c.get("model") or "")
        metric = str(c.get("metric") or "")
        value = str(c.get("value") or "")
        # 指定块优先；序号对不上 md 时退化为全块搜索（三元组匹配）
        cands = ([blocks[k]] if k < len(blocks) else []) + \
                [b for i, b in enumerate(blocks) if i != k]
        hit, used = None, None
        for blk in cands:
            try:
                got = _locate_cell(lines, blk, model, metric, value)
            except Exception:  # noqa: BLE001
                got = None
            if got:
                hit, used = got, blk
                break
        if hit:
            hit["table"] = f"Table {used.label}"
            hits.append({**hit, "kind": "cell", "cell_id": c.get("cell_id"),
                         "model": c.get("model"), "metric": c.get("metric"),
                         "value": c.get("value")})
        else:
            vtxt = str(c.get("value") or "")
            unresolved.append(
                f"cell_unresolved:{c.get('cell_id')}"
                f"|value_in_text={1 if vtxt and vtxt in chr(10).join(lines) else 0}")
    if not hits:
        hits = _locate_label(lines, n.label, limit=max_hits)
        for h in hits:
            h.update({"kind": "label", "match": n.label})
    return {"node_id": node_id, "found": True, "type": n.type,
            "label": n.label, "paper": aid, "md": str(md),
            "n_lines": len(lines), "n_tables": len(blocks),
            "n_cells": len(cells), "hits": hits, "unresolved": unresolved}


def _empty() -> Dict[str, Any]:
    return {}
