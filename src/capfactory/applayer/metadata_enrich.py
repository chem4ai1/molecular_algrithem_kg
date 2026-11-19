"""D5 venue + D6 artifact_protocol 的确定性补全（不调 LLM）。

D5: 从 PDF 转出的 md 页眉/版权行解析 venue；失败保留 unknown。
D6: 从论文是否提到代码仓库/是否 benchmark/是否纯理论 判定交付协议层级。
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any, Dict, Optional

VENUE_PATTERNS = [
    ("nature_family", re.compile(r"nature (machine intelligence|communications|chemistry|medicine)|science advances|cell reports", re.I)),
    ("neurips", re.compile(r"advances in neural information processing systems|neurips", re.I)),
    ("iclr", re.compile(r"international conference on learning representations|iclr", re.I)),
    ("icml", re.compile(r"international conference on machine learning|icml", re.I)),
    ("acl", re.compile(r"proceedings of the (acl|association for computational linguistics)|acl 20", re.I)),
    ("jmlr", re.compile(r"journal of machine learning research|jmlr", re.I)),
    ("ieee_vis", re.compile(r"ieee (vis|transactions on visualization)", re.I)),
    ("bioinformatics", re.compile(r"bioinformatics|ismb", re.I)),
    ("arxiv_preprint", re.compile(r"arxiv:|preprint|under (review|consideration)", re.I)),
]

CODE_PAT = re.compile(
    r"github\.com|gitlab\.com|code (is|will be) (available|released)|"
    r"source code|open[- ]source|https?://\S*(repo|code)", re.I)
BENCH_PAT = re.compile(
    r"benchmark|dataset (we|is) (introduc|releas)|evaluation suite|leaderboard", re.I)
THEORY_PAT = re.compile(
    r"we (prove|show that for all)|theorem \d|proof of theorem|formal (proof|semantics)", re.I)
SURVEY_PAT = re.compile(r"a survey|review of|systematic review", re.I)


def detect_venue(md_text: str) -> tuple[str, str]:
    """返回 (venue_bucket, evidence_snippet)。"""
    head = "\n".join(md_text.splitlines()[:60])
    for name, pat in VENUE_PATTERNS:
        m = pat.search(head)
        if m:
            return name, m.group(0)[:60]
    return "unknown", ""


def detect_artifact(md_text: str) -> tuple[str, Dict[str, bool]]:
    """返回 (protocol_tier, evidence_flags)。"""
    flags = {
        "has_code": bool(CODE_PAT.search(md_text)),
        "has_benchmark": bool(BENCH_PAT.search(md_text)),
        "is_theory": bool(THEORY_PAT.search(md_text)),
        "is_survey": bool(SURVEY_PAT.search(md_text)),
    }
    if flags["has_code"] and flags["has_benchmark"]:
        tier = "code+data"
    elif flags["has_code"]:
        tier = "code-only"
    elif flags["has_benchmark"]:
        tier = "benchmark-only"
    elif flags["is_theory"]:
        tier = "theory-only"
    elif flags["is_survey"]:
        tier = "survey"
    else:
        tier = "minimal"
    return tier, flags


def enrich(graph, papers, md_dir: str | Path):
    md_dir = Path(md_dir)
    stats = {"venue": {}, "artifact": {}}
    for p in papers:
        aid = p.attrs.get("arxiv_id") or p.id.split(":")[-1]
        md = md_dir / f"{aid}.md"
        text = md.read_text(encoding="utf-8", errors="replace") if md.exists() else ""
        # D5
        venue, snip = detect_venue(text)
        p.attrs["venue"] = venue if venue != "unknown" else p.attrs.get("venue")
        p.attrs["venue_evidence"] = snip
        stats["venue"][venue] = stats["venue"].get(venue, 0) + 1
        # D6
        tier, flags = detect_artifact(text)
        p.attrs["artifact_protocol"] = tier
        p.attrs["artifact_flags"] = flags
        stats["artifact"][tier] = stats["artifact"].get(tier, 0) + 1
    return stats


FORM_TO_MODALITY = {
    "smiles": "smiles", "3d坐标": "3d", "图": "graph", "序列": "sequence",
    "向量": "vector", "文本": "text", "标量": "table", "分布": "table",
}


def detect_data_modality(graph) -> dict:
    """D7：从 Paper 关联的 Benchmark.input_form 推断数据模态。"""
    from collections import Counter
    stats = Counter()
    for p in graph.by_type("Paper"):
        forms = []
        for a in graph.outgoing(p.id):
            if a.relation == "EVALUATED_ON" and a.target in graph.nodes:
                f = graph.nodes[a.target].attrs.get("input_form")
                if f:
                    forms.append(FORM_TO_MODALITY.get(str(f).strip(), "text"))
        if forms:
            p.attrs["data_modality"] = Counter(forms).most_common(1)[0][0]
        else:
            p.attrs.setdefault("data_modality", "smiles")
        stats[p.attrs["data_modality"]] += 1
    return dict(stats)
