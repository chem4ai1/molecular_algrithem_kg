"""Leiden 社区发现：自动发现 B 类图谱的社区（GraphRAG 范式）。

当前 B 类靠预设 5 类 + Counter 聚合；这里改为：
1. 从 Paper 属性构造特征加权图（论文之间的相似度边）
2. Leiden 社区检测自动发现社区数与边界
3. 每个社区产出标准 B 节点（title/summary/findings/rating）
"""
from __future__ import annotations
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

# 特征权重：领域规范相关属性
FEATURE_FIELDS = ("evidence_type", "problem_category", "domain_code",
                  "venue", "paradigm")
METRIC_FIELD = "evidence_norm"


def build_similarity_graph(papers: List[Any], *, threshold: float = 0.2):
    """构造论文相似度图，返回 (igraph.Graph, index_map)。

    边权 = 共享特征值数 / 特征字段数；只保留 >= threshold 的边。
    """
    import igraph as ig
    feats = []
    for p in papers:
        s = set()
        for f in FEATURE_FIELDS:
            v = p.attrs.get(f)
            if v:
                s.add(f"{f}={v}")
        for m in (p.attrs.get(METRIC_FIELD) or []):
            s.add(f"metric={m}")
        feats.append(s)

    g = ig.Graph(n=len(papers))
    g.vs["paper_id"] = [p.id for p in papers]
    edges, weights = [], []
    for i in range(len(papers)):
        for j in range(i + 1, len(papers)):
            if not feats[i] or not feats[j]:
                continue
            inter = len(feats[i] & feats[j])
            union = len(feats[i] | feats[j])
            w = inter / max(union, 1)
            if w >= threshold:
                edges.append((i, j))
                weights.append(round(w, 3))
    g.add_edges(edges)
    g.es["weight"] = weights
    return g, {p.id: i for i, p in enumerate(papers)}


def detect_communities(graph, papers: List[Any], *,
                       resolution: float = 1.0,
                       min_size: int = 2) -> List[Dict[str, Any]]:
    """Leiden 社区检测，返回社区描述列表。"""
    import leidenalg as la
    ig_g, id_to_idx = build_similarity_graph(papers)
    if ig_g.ecount() == 0:
        # 无边时每篇论文单独成社区
        return [{"members": [p], "n": 1} for p in papers]

    partition = la.find_partition(
        ig_g, la.RBConfigurationVertexPartition,
        weights=ig_g.es["weight"], resolution_parameter=resolution)
    communities = []
    for comm in partition:
        members = [papers[i] for i in comm]
        if len(members) < min_size and len(partition) > 1:
            continue
        communities.append({"members": members, "n": len(members)})
    communities.sort(key=lambda c: -c["n"])
    return communities


def summarize_community(community: Dict[str, Any], *,
                        evidence_field: str = "evidence_type") -> Dict[str, Any]:
    """GraphRAG 式社区摘要（确定性部分）：统计主导特征 + findings + rating。"""
    members = community["members"]
    n = len(members)
    ev = Counter(p.attrs.get(evidence_field) for p in members if p.attrs.get(evidence_field))
    dom = Counter(p.attrs.get("domain_code") for p in members if p.attrs.get("domain_code"))
    metrics = Counter(m for p in members for m in (p.attrs.get("evidence_norm") or []))
    cat = Counter(p.attrs.get("problem_category") for p in members
                  if p.attrs.get("problem_category"))
    top_ev = ev.most_common(1)[0] if ev else ("unknown", 0)
    top_cat = cat.most_common(1)[0] if cat else ("mixed", 0)
    # 标题用问题类别（比 evidence_type 更有区分度，GraphRAG 也是用主导主题命名）
    title = f"社区:{top_cat[0]}" if top_cat[0] != "mixed" else f"社区:{top_ev[0]}"
    findings = []
    for label, ctr in (("证据类型", ev), ("领域", dom), ("问题类别", cat), ("指标", metrics)):
        if ctr:
            top = ctr.most_common(3)
            findings.append({"summary": f"{label}: {', '.join(f'{k}({v})' for k,v in top)}",
                             "explanation": f"在 {n} 篇社区成员中统计"})
    # GraphRAG rating：支持度（社区规模）+ 纯度（主导证据类型占比）
    purity = top_ev[1] / max(n, 1)
    rating = min((n / 20.0) * 0.6 + purity * 0.4, 1.0)
    return {"title": title, "summary": f"从 {n} 篇论文自动发现的社区，主导问题 {top_cat[0]}，证据 {top_ev[0]}",
            "findings": findings, "rating": round(rating, 3),
            "rating_explanation": f"n={n}, 主导证据纯度={purity:.2f}",
            "n_papers": n, "members": [p.id for p in members],
            "evidence_type": top_ev[0],
            "accepted_metrics": [k for k, _ in metrics.most_common(10)],
            "community_level": 0}
