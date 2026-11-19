#!/usr/bin/env python3
"""面向算法发现的 Leiden 社区：用 method_family 重塑特征图 + LLM 写社区标题。

两步：
1. 特征图加入 method_family（高权重），Leiden 自动发现「流派社区」
2. LLM (Ernie) 基于 findings + 成员标题写有意义的社区标题
"""
from __future__ import annotations
import json, sys, re
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from capfactory.po import POGraph
from capfactory.applayer.community_discovery import detect_communities, summarize_community
from capfactory.applayer.method_taxonomy import METHOD_FAMILIES, family_desc

GRAPH = ROOT / "storage/sciforge/factory_knowledge_annotated.json"
OUT = ROOT / "storage/sciforge/factory_knowledge_method_communities.json"
REPORT = ROOT / "storage/sciforge/method_communities.json"


def llm_title(findings: list, titles: list, dominant: str = "") -> dict:
    """Ernie 基于 findings + 论文标题写社区标题 + 设计启发。"""
    from capfactory.vector.labeler import OpenRouterBackend
    b = OpenRouterBackend(model="baidu/ernie-5.5-flash-preview:free")
    ev = " | ".join(f["summary"][:60] for f in findings[:4])
    ts = " ; ".join(titles[:4])
    prompt = (
        "你是分子算法设计专家。根据一个论文社区的特征，输出该社区的方法流派名和算法设计启发。"
        "只输出JSON：{\"title\":\"6-12字流派名\",\"rationale\":\"一句话解释\","
        "\"design_hint\":\"这个流派对后续算法设计的启发\"}\n\n"
        f"主导方法流派：{dominant}（必须体现在标题中，且不同流派标题不能重复）\n"
        f"特征：{ev}\n代表论文：{ts}")
    try:
        raw = b.chat(prompt, max_tokens=1000)
        from capfactory.utils import parse_llm_json
        r = parse_llm_json(raw)
        if isinstance(r, dict) and r.get("title"):
            return r
    except Exception:
        pass
    return {"title": "", "rationale": "LLM不可用，保留统计标题", "design_hint": ""}


def main():
    g = POGraph.load(str(GRAPH))
    papers = [p for p in g.by_type("Paper") if p.attrs.get("method_family")]
    print("论文数", len(papers), flush=True)

    # 1. 覆盖 build_similarity_graph 的 feats：让 method_family 权重最高
    import capfactory.applayer.community_discovery as cd
    orig = cd.build_similarity_graph

    def family_weighted(pl, *, threshold=0.2):
        import igraph as ig
        feats = []
        for p in pl:
            s = set()
            fam = p.attrs.get("method_family")
            if fam and fam != "unclassified":
                # method_family 重复 3 次 → 在 Jaccard 中权重更高
                s.update([f"family={fam}"] * 3)
            for f in ("problem_category", "domain_code", "evidence_type"):
                v = p.attrs.get(f)
                if v:
                    s.add(f"{f}={v}")
            for m in (p.attrs.get("evidence_norm") or []):
                s.add(f"metric={m}")
            feats.append(s)
        gg = ig.Graph(n=len(pl))
        gg.vs["paper_id"] = [p.id for p in pl]
        edges, weights = [], []
        for i in range(len(pl)):
            for j in range(i + 1, len(pl)):
                if not feats[i] or not feats[j]:
                    continue
                inter = len(feats[i] & feats[j])
                w = inter / max(len(feats[i] | feats[j]), 1)
                if w >= threshold * 0.5:   # 放宽阈值因为 family 重复提升分母
                    edges.append((i, j)); weights.append(round(w, 3))
        gg.add_edges(edges); gg.es["weight"] = weights
        return gg, {p.id: i for i, p in enumerate(pl)}

    cd.build_similarity_graph = family_weighted
    communities = detect_communities(g, papers, resolution=1.0)
    cd.build_similarity_graph = orig

    # 2. 每个社区：统计摘要 + LLM 标题
    results = []
    for i, c in enumerate(communities):
        s = summarize_community(c)
        fams = Counter(p.attrs.get("method_family") for p in c["members"])
        top_fam = fams.most_common(1)[0] if fams else ("mixed", 0)
        titles = [p.attrs.get("true_title") or p.label for p in c["members"][:5]]
        s["method_families"] = dict(fams)
        s["dominant_family"] = top_fam[0]
        if top_fam[0] in METHOD_FAMILIES:
            s["design_hint_rule"] = family_desc(top_fam[0])
        # LLM 写标题
        llm = llm_title(s["findings"], titles, top_fam[0])
        s["llm_title"] = llm.get("title", "")
        s["rationale"] = llm.get("rationale", "")
        s["design_hint"] = llm.get("design_hint", "")
        fam_cn = METHOD_FAMILIES.get(top_fam[0], (top_fam[0], [], ""))[0]
        prob = s['title'].replace('社区:', '').replace('community:', '')
        final_title = llm.get("title") or f"{fam_cn}·{prob}"
        nid = f"method:community:{i}"
        g.node(nid, "EvaluationNorm", final_title,
               title=final_title, summary=s["summary"],
               findings=s["findings"], rating=s["rating"],
               rating_explanation=s["rating_explanation"],
               n_papers=s["n_papers"], evidence_type=s["evidence_type"],
               accepted_metrics=s["accepted_metrics"],
               method_family=top_fam[0], method_families=dict(fams),
               design_hint=s.get("design_hint") or s.get("design_hint_rule", ""),
               rationale=s["rationale"], community_level=0,
               members=s["members"], discovered_by="leiden+method_family")
        for pid in s["members"]:
            if pid in g.nodes:
                g.assert_rel(nid, pid, "DERIVED_FROM_PAPERS")
        results.append({"id": nid, **s})

    g.save(str(OUT))
    REPORT.write_text(json.dumps({
        "algorithm": "leiden+method_family+LLM_title",
        "n_papers": len(papers), "n_communities": len(communities),
        "communities": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"n_communities": len(communities),
                      "sizes": [c["n"] for c in communities],
                      "nodes": len(g.nodes), "assertions": len(g.assertions)},
                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
