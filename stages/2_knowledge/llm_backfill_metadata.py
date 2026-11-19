#!/usr/bin/env python3
"""分级 LLM 补元数据：只补规则无法确定的，且记录置信度。

策略（基于对照实验）：
- venue: 规则 unknown/None → LLM 补（LLM 能从摘要识别期刊，规则漏 29 篇）
- evidence_type: 仅当 source=family_mode（众数填充，低可信）→ LLM 校验
- 规则强信号（PDF页眉/strong_rule）保留，不被 LLM 覆盖
"""
from __future__ import annotations
import json, re, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from capfactory.po import POGraph
from capfactory.vector.labeler import OpenRouterBackend
from capfactory.utils import parse_llm_json

GRAPH = ROOT / "storage/sciforge/factory_knowledge_complete.json"
OUT = ROOT / "storage/sciforge/factory_knowledge_final.json"
MD = ROOT / "data/docx"


def extract_abstract(text: str) -> str:
    m = re.search(r"(?is)(?:abstract|abstract:)\s*(.{100,900}?)(?:\n\s*#|introduction|\Z)", text[:4000])
    return (m.group(1) if m else text[:400]).strip()[:500]


def main():
    g = POGraph.load(str(GRAPH))
    papers = g.by_type("Paper")
    b = OpenRouterBackend(model="baidu/ernie-5.5-flash-preview:free")
    if not b.ok:
        print("Ernie 不可用，跳过 LLM 补全"); return
    stats = {"venue_filled": 0, "ev_rechecked": 0, "llm_fail": 0, "kept_rule": 0}
    for p in papers:
        aid = p.attrs.get("arxiv_id") or p.id.split(":")[-1]
        need_venue = not p.attrs.get("venue")
        need_ev = p.attrs.get("evidence_type_source") == "family_mode"
        if not need_venue and not need_ev:
            stats["kept_rule"] += 1
            continue
        md = MD / f"{aid}.md"
        text = md.read_text(encoding="utf-8", errors="replace") if md.exists() else ""
        title = p.attrs.get("true_title") or p.label
        prompt = (
            '你是论文元数据专家。只输出JSON：'
            '{"venue":"会议/期刊全名或unknown","evidence_type":'
            '"experimental|simulational|derivational|interpretive","confidence":0-1}\n'
            f"标题：{title[:120]}\n摘要：{extract_abstract(text)}")
        try:
            raw = b.chat(prompt, max_tokens=600)
            r = parse_llm_json(raw) or {}
        except Exception:
            stats["llm_fail"] += 1
            continue
        if not isinstance(r, dict):
            stats["llm_fail"] += 1
            continue
        conf = float(r.get("confidence") or 0)
        # venue：LLM 给具体值且置信度 >=0.5 才采用
        if need_venue and r.get("venue") and r["venue"].lower() != "unknown" and conf >= 0.5:
            p.attrs["venue"] = str(r["venue"])[:100]
            p.attrs["venue_source"] = "llm"
            p.attrs["venue_confidence"] = conf
            stats["venue_filled"] += 1
        # evidence_type：只在众数填充且 LLM 高置信且不同才改
        if need_ev and r.get("evidence_type") in (
                "experimental", "simulational", "derivational", "interpretive") and conf >= 0.7:
            if r["evidence_type"] != p.attrs.get("evidence_type"):
                p.attrs["evidence_type"] = r["evidence_type"]
                p.attrs["evidence_type_source"] = "llm_corrected"
                p.attrs["evidence_type_confidence"] = conf
            stats["ev_rechecked"] += 1
    g.save(str(OUT))
    print(json.dumps({"stats": stats, "out": str(OUT)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
