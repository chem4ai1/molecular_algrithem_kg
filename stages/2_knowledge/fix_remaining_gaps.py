#!/usr/bin/env python3
"""修正剩余缺口：
1. data_modality 原文判定（不再默认 text）
2. P7 消融粒度：模块级 → 模块+超参级
3. P5 baseline：从 MethodLineage 查同 task_type 的具体方法名
"""
from __future__ import annotations
import json, re, sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from capfactory.po import POGraph

GRAPH = ROOT / "storage/sciforge/factory_knowledge_final.json"
OUT = ROOT / "storage/sciforge/factory_knowledge_v3.json"
MD = ROOT / "data/docx"

MODALITY_PAT = [
    ("smiles", re.compile(r"\bSMILES\b", re.I)),
    ("graph", re.compile(r"\b(molecular graph|2D graph|graph neural|GNN|message passing)\b", re.I)),
    ("3d", re.compile(r"\b(3D conformer|3D coordinat|conformer|point cloud)\b", re.I)),
    ("sequence", re.compile(r"\b(amino acid sequence|protein sequence|FASTA)\b", re.I)),
    ("text", re.compile(r"\b(natural language|text description|prompt)\b", re.I)),
]
HYPERPARAM_PAT = re.compile(
    r"\b(number of iterations|number of steps|temperature|top-?k|sampling budget|"
    r"learning rate|batch size|number of samples|oracle budget|beam size)\b", re.I)


def detect_modality(text: str, current: str) -> tuple[str, str]:
    hits = Counter()
    for name, pat in MODALITY_PAT:
        n = len(pat.findall(text))
        if n:
            hits[name] += n
    if not hits:
        return current, "kept"
    top = hits.most_common(1)[0][0]
    return top, f"text_hits={dict(hits)}"


def detect_hyperparams(text: str, limit: int = 6) -> list:
    found = []
    for m in HYPERPARAM_PAT.finditer(text):
        ctx = text[max(0, m.start() - 40): m.end() + 60].replace("\n", " ")
        found.append({"param": m.group(0).lower(), "context": ctx.strip()[:100]})
        if len(found) >= limit:
            break
    return found


def main():
    g = POGraph.load(str(GRAPH))
    papers = g.by_type("Paper")
    modality_fixed, hyper_added, baseline_added = 0, 0, 0

    # 流派 → 该 task_type 下的方法（用于 P5 baseline）
    by_task = {}
    for a in g.by_type("Algorithm"):
        tt = a.attrs.get("task_type")
        if tt:
            by_task.setdefault(tt, []).append(a.attrs.get("name") or a.id)

    for p in papers:
        aid = p.attrs.get("arxiv_id") or p.id.split(":")[-1]
        md = MD / f"{aid}.md"
        text = md.read_text(encoding="utf-8", errors="replace") if md.exists() else ""
        # 1) 模态原文判定
        cur = p.attrs.get("data_modality") or ""
        new, why = detect_modality(text, cur)
        if new != cur:
            p.attrs["data_modality"] = new
            p.attrs["data_modality_source"] = why
            modality_fixed += 1
        # 2) 超参级消融对象
        hp = detect_hyperparams(text)
        if hp:
            p.attrs["ablation_hyperparams"] = hp
            hyper_added += 1
        # 3) P5 baseline 候选（同 task_type 的其它方法）
        cats = []
        for a in g.outgoing(p.id):
            if a.relation == "PROPOSES_METHOD" and a.target in g.nodes:
                cats.append(g.nodes[a.target].attrs.get("task_type"))
        pool = []
        for c in set(x for x in cats if x):
            pool += [m for m in by_task.get(c, []) if m not in
                     [g.nodes[x].attrs.get("name") for x in
                      [a.target for a in g.outgoing(p.id) if a.relation == "PROPOSES_METHOD"
                       and a.target in g.nodes] if x in g.nodes]]
        if pool:
            p.attrs["baseline_candidates"] = list(dict.fromkeys(pool))[:8]
            baseline_added += 1

    g.save(str(OUT))
    print(json.dumps({
        "modality_fixed": modality_fixed,
        "hyperparam_annotated": hyper_added,
        "baseline_annotated": baseline_added,
        "modality_dist": dict(Counter(p.attrs.get("data_modality") for p in papers)),
        "out": str(OUT)}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
