"""领域（D0–D10）与算法族（A01–A18）分类：把论文/能力/算法节点升级为可查询的图属性.

设计取舍：

* **20 篇报告论文用手工映射**（``PAPER_TAXONOMY``），每条给一句可在报告包
  ``论文问题算法评测矩阵.csv`` 的 ``algorithm`` 列复核的依据——这是可审计的核心资产；
* **未知论文/能力走确定性文本规则**（``DOMAIN_RULES`` / ``ALGO_RULES``），
  多标签、有界（最多 3 个），并记录 ``taxonomy_source = manual|rule``；
* 分类结果同时写入节点属性（``domain_codes`` / ``algo_codes``）并**实体化为
  ``Domain`` / ``AlgorithmFamily`` 节点 + ``IN_DOMAIN`` / ``USES_ALGO_FAMILY`` 边**，
  这样「D5 下有哪些论文」「用了 A04 的算法有哪些」可以直接图查询；
* 绝不因为分类失败就丢弃节点：无命中时落 ``D0``（通用）或 ``A18``（经典 ML），
  并在 ``taxonomy_rationale`` 里标注 fallback。
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..utils import now_iso
from .store import POGraph
from .vocab import (
    ALGORITHM_FAMILY_TO_CODE, ALGO_NAMES, DOMAIN_NAMES, TASK_FAMILY_TO_DOMAIN,
)

TAXONOMY_VERSION = "d11_a18_v1"
DOMAIN_FALLBACK = "D0"
ALGO_FALLBACK = "A18"
MAX_TAGS = 3

# ---------------------------------------------------------------------------
# 1. 报告 20 篇的手工映射（依据：论文问题算法评测矩阵.csv 的 algorithm 列）
# ---------------------------------------------------------------------------
PAPER_TAXONOMY: Dict[str, Dict[str, Any]] = {
    "01": {"domains": ["D5", "D3"], "algorithms": ["A04", "A10"],
           "rationale": "RF2/RFdiffusion 宏环扩展；SE(3) 等变扩散生成环肽构象"},
    "02": {"domains": ["D5", "D3"], "algorithms": ["A02", "A04", "A10"],
           "rationale": "all-atom VAE + target-specific affine latent + latent diffusion"},
    "03": {"domains": ["D5", "D2"], "algorithms": ["A11", "A01"],
           "rationale": "EDA 岛模型演化搜索 + ESMFold 结构预测构成优化回路"},
    "04": {"domains": ["D5", "D2"], "algorithms": ["A02", "A08"],
           "rationale": "序列 VAE 潜空间 + GP 代理 + 贝叶斯优化闭环"},
    "05": {"domains": ["D5", "D4"], "algorithms": ["A01", "A12", "A18"],
           "rationale": "ESM2 embedding + Deep Forest/分类器过滤做 AMP 挖掘"},
    "06": {"domains": ["D5", "D3"], "algorithms": ["A01", "A12"],
           "rationale": "ESM-2 span-mask 肽语言模型 + 目标序列条件化"},
    "07": {"domains": ["D5", "D4"], "algorithms": ["A18", "A12"],
           "rationale": "深度突变扫描 + ESM2 特征 + NB/Lasso/SVR 阈值交集"},
    "08": {"domains": ["D1", "D3", "D8"], "algorithms": ["A04", "A10"],
           "rationale": "原子级通用 denoiser + 多结构任务 prompt 联合训练"},
    "09": {"domains": ["D1", "D3"], "algorithms": ["A04", "A10"],
           "rationale": "等变 SE(3) diffusion + pocket inpainting 与 oracle 循环"},
    "10": {"domains": ["D1", "D3"], "algorithms": ["A04", "A10"],
           "rationale": "药效团编码 + 原子坐标/元素/键扩散生成"},
    "11": {"domains": ["D1", "D3"], "algorithms": ["A05", "A09", "A10"],
           "rationale": "SEMLA 口袋编码 + cross-attention + continuous/discrete flow matching"},
    "12": {"domains": ["D3"], "algorithms": ["A04", "A10", "A17"],
           "rationale": "平移/旋转/扭转流形扩散 + confidence ranking"},
    "13": {"domains": ["D1", "D3"], "algorithms": ["A04", "A10"],
           "rationale": "口袋条件 SE(3) 等变扩散 + 类别原子生成"},
    "14": {"domains": ["D6", "D3"], "algorithms": ["A01", "A04", "A10"],
           "rationale": "Pairformer + raw-atom coordinate diffusion 扩展多实体复合物"},
    "15": {"domains": ["D9", "D8"], "algorithms": ["A02", "A03", "A09"],
           "rationale": "GCN VAE-GAN + GRN 推断与迭代 gene weighting 做单细胞药物排序"},
    "16": {"domains": ["D1", "D2"], "algorithms": ["A14", "A04", "A07"],
           "rationale": "Chemistry42 多生成器平台编排 + 2D/3D 奖励与人工筛选"},
    "17": {"domains": ["D2", "D4", "D9"], "algorithms": ["A14", "A15", "A07"],
           "rationale": "PandaOmics 多组学排序 + Chemistry42 生成反馈 + 实验药化"},
    "18": {"domains": ["D2", "D4"], "algorithms": ["A14", "A04"],
           "rationale": "Chemistry42 辅助化学设计 + 结构/活性优化与实验药化"},
    "19": {"domains": ["D2", "D4", "D3"], "algorithms": ["A14", "A15", "A07"],
           "rationale": "PandaOmics 靶点优先级 + Chemistry42/Alchemistry 多轮生成与 ADMET 优化"},
    "20": {"domains": ["D1", "D2", "D3"], "algorithms": ["A14", "A04", "A07"],
           "rationale": "Chemistry42 多生成器/过滤 + MOE docking + PROTAC linker 生成"},
}

# ---------------------------------------------------------------------------
# 2. 文本规则（用于未知论文、能力、算法节点）
# ---------------------------------------------------------------------------
# 关键词规则来自 keywords.py（强/中/弱三级权重，可导出给 LLM），此处只做转发
from .keywords import (  # noqa: E402  (放在常量后以保持模块可读性)
    DOMAIN_MIN_SCORE, DOMAIN_RULES, ALGO_RULES, keyword_stats, keyword_table,
)

def _score(rules: Sequence[Tuple[str, str, float]], text: str) -> Dict[str, float]:
    low = (text or "").lower()
    scores: Dict[str, float] = defaultdict(float)
    for code, pattern, weight in rules:
        hits = len(re.findall(pattern, low))
        if hits:
            scores[code] += weight * (1.0 + 0.2 * (hits - 1))
    return dict(scores)


def classify(text: str, kind: str = "domain", *, limit: int = MAX_TAGS,
             fallback: str = "") -> List[str]:
    """多标签分类；无命中时返回 fallback（domain→D0，algo→A18）。

    领域侧额外执行 **D0 判定**：若最高分低于 ``DOMAIN_MIN_SCORE``
    （即只有弱/中等词，没有任何强生物/材料/化学关键词），
    按定义返回 ``D0``「通用算法（跨领域）」而不是强行归到某个领域。
    """
    rules = DOMAIN_RULES if kind == "domain" else ALGO_RULES
    fb = fallback or (DOMAIN_FALLBACK if kind == "domain" else ALGO_FALLBACK)
    scores = _score(rules, text)
    if not scores:
        return [fb]
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    if kind == "domain" and ordered[0][1] < DOMAIN_MIN_SCORE:
        return [DOMAIN_FALLBACK]
    return [c for c, _ in ordered[:limit]]


def classify_with_evidence(text: str, kind: str = "domain",
                           *, limit: int = MAX_TAGS) -> Tuple[List[str], Dict[str, float]]:
    rules = DOMAIN_RULES if kind == "domain" else ALGO_RULES
    scores = _score(rules, text)
    if not scores:
        return [DOMAIN_FALLBACK if kind == "domain" else ALGO_FALLBACK], {}
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    if kind == "domain" and ordered[0][1] < DOMAIN_MIN_SCORE:
        return [DOMAIN_FALLBACK], {c: round(s, 3) for c, s in ordered[:limit]}
    return [c for c, _ in ordered[:limit]], {c: round(s, 3) for c, s in ordered[:limit]}


def taxonomy_for_paper(number: str) -> Dict[str, Any]:
    key = str(number).strip().lstrip("0") or "0"
    key = key.zfill(2) if len(key) <= 2 else key
    hit = PAPER_TAXONOMY.get(key) or PAPER_TAXONOMY.get(str(number).strip())
    if hit:
        return {**hit, "source": "manual"}
    return {"domains": [], "algorithms": [], "rationale": "", "source": "missing"}


# ---------------------------------------------------------------------------
# 3. 应用到图
# ---------------------------------------------------------------------------
def _ensure_taxonomy_nodes(g: POGraph) -> Dict[str, str]:
    """幂等创建 Domain / AlgorithmFamily 节点，返回 code → qn 映射。"""
    ids: Dict[str, str] = {}
    for code, name in DOMAIN_NAMES.items():
        qn = f"domain:{code}"
        g.node(qn, "Domain", name, code=code, definition=name,
               taxonomy_version=TAXONOMY_VERSION)
        ids[code] = qn
    for code, name in ALGO_NAMES.items():
        qn = f"algofamily:{code}"
        g.node(qn, "AlgorithmFamily", name, code=code, description=name,
               taxonomy_version=TAXONOMY_VERSION)
        ids[code] = qn
    return ids


def _text_of(concept: Any) -> str:
    a = concept.attrs
    parts = [concept.label, str(a.get("title", "")), str(a.get("abstract", "")),
             str(a.get("statement", "")), str(a.get("scope", "")),
             str(a.get("method", "")), str(a.get("algorithm", "")),
             str(a.get("task", "")), str(a.get("architecture", "")),
             str(a.get("summary", "")), str(a.get("steps", "")),
             str(a.get("research_object", "")), str(a.get("contributions", ""))]
    return " ".join(p for p in parts if p)


def apply_taxonomy(g: POGraph, *, overwrite: bool = False) -> Dict[str, Any]:
    """给 PO 图打 D/A 标签并实体化分类节点。返回统计。"""
    ids = _ensure_taxonomy_nodes(g)
    stats: Dict[str, Any] = {"papers_tagged": 0, "claims_tagged": 0,
                             "algorithms_tagged": 0, "manual": 0, "rule": 0,
                             "domain_counts": Counter(), "algo_counts": Counter(),
                             "domain_edges": 0, "algo_edges": 0,
                             "unclassified_papers": []}
    paper_domains: Dict[str, List[str]] = {}

    for paper in g.by_type("Paper"):
        number = str(paper.attrs.get("number") or paper.id.split(":")[-1])
        if paper.attrs.get("domain_codes") and not overwrite:
            paper_domains[paper.id] = list(paper.attrs["domain_codes"])
            continue
        manual = taxonomy_for_paper(number)
        if manual["source"] == "manual":
            doms, algos = manual["domains"], manual["algorithms"]
            rationale, source = manual["rationale"], "manual"
            stats["manual"] += 1
        else:
            doms, dom_ev = classify_with_evidence(_text_of(paper), "domain")
            algos, algo_ev = classify_with_evidence(_text_of(paper), "algo")
            rationale = f"rule: domains={dom_ev} algorithms={algo_ev}"
            source = "rule"
            stats["rule"] += 1
        paper.attrs["domain_codes"] = doms
        paper.attrs["algo_codes"] = algos
        paper.attrs["domain_names"] = [DOMAIN_NAMES[d] for d in doms]
        paper.attrs["algo_names"] = [ALGO_NAMES[a] for a in algos]
        paper.attrs["taxonomy_rationale"] = rationale
        paper.attrs["taxonomy_source"] = source
        paper.attrs["taxonomy_version"] = TAXONOMY_VERSION
        paper_domains[paper.id] = doms
        stats["papers_tagged"] += 1
        for d in doms:
            if d in ids and g.assert_rel(paper.id, ids[d], "IN_DOMAIN",
                                         attribution="analyst_synthesis",
                                         taxonomy_source=source):
                stats["domain_edges"] += 1
            stats["domain_counts"][d] += 1
        for a in algos:
            if a in ids and g.assert_rel(paper.id, ids[a], "USES_ALGO_FAMILY",
                                         attribution="analyst_synthesis",
                                         taxonomy_source=source):
                stats["algo_edges"] += 1
            stats["algo_counts"][a] += 1
        if not doms or doms == [DOMAIN_FALLBACK]:
            stats["unclassified_papers"].append(number)

    # 能力主张继承所属论文的领域/算法族
    for claim, paper in _claim_paper_pairs(g):
        doms = paper_domains.get(paper, []) or list(claim.attrs.get("domain_codes", []))
        if not doms:
            continue
        claim.attrs.setdefault("domain_codes", doms)
        claim.attrs.setdefault("algo_codes", list(g.nodes[paper].attrs.get("algo_codes", [])))
        for d in claim.attrs["domain_codes"]:
            if d in ids:
                g.assert_rel(claim.id, ids[d], "IN_DOMAIN", attribution="analyst_synthesis")
        for a in claim.attrs.get("algo_codes", []):
            if a in ids:
                g.assert_rel(claim.id, ids[a], "USES_ALGO_FAMILY",
                             attribution="analyst_synthesis")
        stats["claims_tagged"] += 1

    # 算法节点：architecture 主映射 + 文本规则补充
    for algo in g.by_type("Algorithm"):
        arch = str(algo.attrs.get("architecture", "")).strip()
        codes: List[str] = []
        if arch in ALGORITHM_FAMILY_TO_CODE:
            codes.append(ALGORITHM_FAMILY_TO_CODE[arch])
        for c in classify(_text_of(algo), "algo", limit=MAX_TAGS):
            if c not in codes:
                codes.append(c)
        codes = codes[:MAX_TAGS]
        algo.attrs["algo_codes"] = codes
        algo.attrs["algo_names"] = [ALGO_NAMES[c] for c in codes]
        algo.attrs.setdefault("algo_family_source", "architecture+rule")
        for c in codes:
            if c in ids:
                g.assert_rel(algo.id, ids[c], "USES_ALGO_FAMILY",
                             attribution="analyst_synthesis")
        stats["algorithms_tagged"] += 1

    stats["domain_counts"] = dict(stats["domain_counts"])
    stats["algo_counts"] = dict(stats["algo_counts"])
    stats["n_domain_nodes"] = len(g.by_type("Domain"))
    stats["n_algofamily_nodes"] = len(g.by_type("AlgorithmFamily"))
    stats["matrix"] = taxonomy_matrix(g)
    stats["applied_at"] = now_iso()
    g.meta["taxonomy"] = {k: v for k, v in stats.items() if k != "matrix"}
    return stats


def _claim_paper_pairs(g: POGraph) -> Iterable[Tuple[Any, str]]:
    for paper in g.by_type("Paper"):
        for e in g.outgoing(paper.id, "HAS_CLAIM"):
            claim = g.nodes.get(e.target)
            if claim is not None:
                yield claim, paper.id


def taxonomy_matrix(g: POGraph) -> Dict[str, Any]:
    """D×A 交叉表：每个领域下各算法族的论文数。"""
    matrix: Dict[str, Dict[str, int]] = {}
    for paper in g.by_type("Paper"):
        for d in paper.attrs.get("domain_codes", []) or []:
            row = matrix.setdefault(d, {})
            for a in paper.attrs.get("algo_codes", []) or []:
                row[a] = row.get(a, 0) + 1
    return {
        "domains": {d: {"name": DOMAIN_NAMES.get(d, d), "n_papers": n,
                        "top_algorithms": dict(sorted(row.items(),
                                                      key=lambda kv: -kv[1])[:5])}
                    for d, row in sorted(matrix.items())
                    for n in [sum(1 for p in g.by_type("Paper")
                                  if d in (p.attrs.get("domain_codes") or []))]},
        "cell_counts": {d: dict(sorted(row.items(), key=lambda kv: -kv[1]))
                        for d, row in sorted(matrix.items())},
    }


# ---------------------------------------------------------------------------
# 4. 应用到主 KnowledgeGraph（现有论文 / 能力节点）
# ---------------------------------------------------------------------------
def apply_taxonomy_to_kg(kg: Any, *, overwrite: bool = False) -> Dict[str, Any]:
    """给主图的 ``paper`` / ``capability`` 节点打 D/A 标签。"""
    ids = _ensure_taxonomy_nodes_kg(kg)
    stats: Dict[str, Any] = {"papers_tagged": 0, "capabilities_tagged": 0,
                             "domain_edges": 0, "algo_edges": 0,
                             "domain_counts": Counter(), "algo_counts": Counter(),
                             "samples": []}
    for node in kg.nodes.values() if isinstance(kg.nodes, dict) else kg.nodes:
        ntype = node.get("type")
        attrs = node.setdefault("attrs", {})
        if ntype == "paper":
            text = " ".join(str(attrs.get(k, "")) for k in
                            ("abstract", "research_object", "background", "title"))
            text += " " + str(node.get("label", ""))
            if attrs.get("domain_codes") and not overwrite:
                continue
            manual = taxonomy_for_paper(attrs.get("number") or "")
            if manual["source"] == "manual":
                doms, algos, source = manual["domains"], manual["algorithms"], "manual"
            else:
                doms, _ = classify_with_evidence(text, "domain")
                algos, _ = classify_with_evidence(text, "algo")
                source = "rule"
            attrs["domain_codes"] = doms
            attrs["algo_codes"] = algos
            attrs["domain_names"] = [DOMAIN_NAMES[d] for d in doms]
            attrs["algo_names"] = [ALGO_NAMES[a] for a in algos]
            attrs["taxonomy_source"] = source
            attrs["taxonomy_version"] = TAXONOMY_VERSION
            stats["papers_tagged"] += 1
            _link_kg(kg, node["id"], doms, algos, ids, stats)
            stats["samples"].append({"id": node["id"], "type": ntype,
                                     "domains": doms, "algorithms": algos})
        elif ntype == "capability":
            if attrs.get("domain_codes") and not overwrite:
                continue
            task_family = str(attrs.get("task_family", "")).strip()
            algo_family = str(attrs.get("algorithm_family", "")).strip()
            doms: List[str] = []
            if task_family in TASK_FAMILY_TO_DOMAIN:
                doms.append(TASK_FAMILY_TO_DOMAIN[task_family])
            algos: List[str] = []
            if algo_family in ALGORITHM_FAMILY_TO_CODE:
                algos.append(ALGORITHM_FAMILY_TO_CODE[algo_family])
            text = " ".join(str(attrs.get(k, "")) for k in
                            ("summary", "method", "task", "category")) + " " + str(node.get("label", ""))
            for c in classify(text, "domain", limit=MAX_TAGS):
                if c == DOMAIN_FALLBACK and doms:
                    continue          # 已有明确领域时，不再追加 D0 兜底
                if c not in doms:
                    doms.append(c)
            for c in classify(text, "algo", limit=MAX_TAGS):
                if c not in algos:
                    algos.append(c)
            doms, algos = doms[:MAX_TAGS], algos[:MAX_TAGS]
            attrs["domain_codes"] = doms
            attrs["algo_codes"] = algos
            attrs["domain_names"] = [DOMAIN_NAMES[d] for d in doms]
            attrs["algo_names"] = [ALGO_NAMES[a] for a in algos]
            attrs["taxonomy_source"] = "task_family+rule" if task_family else "rule"
            attrs["taxonomy_version"] = TAXONOMY_VERSION
            stats["capabilities_tagged"] += 1
            _link_kg(kg, node["id"], doms, algos, ids, stats)
            stats["samples"].append({"id": node["id"], "type": ntype,
                                     "domains": doms, "algorithms": algos})
        else:
            continue
        for d in attrs.get("domain_codes", []):
            stats["domain_counts"][d] += 1
        for a in attrs.get("algo_codes", []):
            stats["algo_counts"][a] += 1
    stats["domain_counts"] = dict(stats["domain_counts"])
    stats["algo_counts"] = dict(stats["algo_counts"])
    stats["taxonomy_version"] = TAXONOMY_VERSION
    stats["applied_at"] = now_iso()
    return stats


def _ensure_taxonomy_nodes_kg(kg: Any) -> Dict[str, str]:
    ids: Dict[str, str] = {}
    for code, name in DOMAIN_NAMES.items():
        qn = f"domain:{code}"
        kg.add_node(qn, "Domain", name, code=code, definition=name,
                    taxonomy_version=TAXONOMY_VERSION)
        ids[code] = qn
    for code, name in ALGO_NAMES.items():
        qn = f"algofamily:{code}"
        kg.add_node(qn, "AlgorithmFamily", name, code=code, description=name,
                    taxonomy_version=TAXONOMY_VERSION)
        ids[code] = qn
    return ids


def _link_kg(kg: Any, node_id: str, doms: Sequence[str], algos: Sequence[str],
             ids: Dict[str, str], stats: Dict[str, Any]) -> None:
    for d in doms:
        if d in ids:
            kg.add_edge(node_id, ids[d], "IN_DOMAIN")
            stats["domain_edges"] += 1
    for a in algos:
        if a in ids:
            kg.add_edge(node_id, ids[a], "USES_ALGO_FAMILY")
            stats["algo_edges"] += 1


# ---------------------------------------------------------------------------
# 5. 导出与 CLI
# ---------------------------------------------------------------------------
def taxonomy_spec() -> Dict[str, Any]:
    """供 API/前端使用的完整分类体系。"""
    return {
        "version": TAXONOMY_VERSION,
        "domains": [{"code": c, "name": n} for c, n in DOMAIN_NAMES.items()],
        "algorithms": [{"code": c, "name": n} for c, n in ALGO_NAMES.items()],
        "paper_taxonomy": PAPER_TAXONOMY,
        "task_family_to_domain": dict(TASK_FAMILY_TO_DOMAIN),
        "algorithm_family_to_code": dict(ALGORITHM_FAMILY_TO_CODE),
        "domain_rules": [{"code": c, "pattern": p, "weight": w} for c, p, w in DOMAIN_RULES],
        "algo_rules": [{"code": c, "pattern": p, "weight": w} for c, p, w in ALGO_RULES],
        "keywords": keyword_table(),
        "keyword_stats": keyword_stats(),
        "domain_min_score": DOMAIN_MIN_SCORE,
        "fallbacks": {"domain": DOMAIN_FALLBACK, "algorithm": ALGO_FALLBACK},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="领域/算法族分类：打标并写回图")
    ap.add_argument("--po-graph", default="storage_cf/po/report_graph.json",
                    help="报告包 PO 图（如不存在则先从报告包导入）")
    ap.add_argument("--report-dir", default="")
    ap.add_argument("--kg", default="storage_cf/kg/graph.json", help="主 KnowledgeGraph")
    ap.add_argument("--apply-kg", action="store_true", help="同时给主图论文/能力打标")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    out: Dict[str, Any] = {}
    po_path = Path(args.po_graph)
    if args.report_dir or not po_path.exists():
        from .importer import import_report_bundle
        root = Path(args.report_dir) if args.report_dir else \
            Path("/home/zengshuxin/xKG-main/问题导向本体与知识图谱架构_20261109")
        g, _ = import_report_bundle(root)
    else:
        g = POGraph.load(po_path)
    po_stats = apply_taxonomy(g, overwrite=args.overwrite)
    g.save(po_path)
    out["po"] = {k: v for k, v in po_stats.items() if k != "matrix"}
    out["po_graph"] = str(po_path)

    if args.apply_kg:
        from ..kg import KnowledgeGraph
        kg = KnowledgeGraph()
        kg.load(Path(args.kg))
        kg_stats = apply_taxonomy_to_kg(kg, overwrite=args.overwrite)
        import shutil
        backup = Path(args.kg).with_name(Path(args.kg).stem + "_pre_taxonomy.json")
        if not backup.exists():
            shutil.copy2(args.kg, backup)
        kg.save(Path(args.kg))
        out["kg"] = kg_stats
        out["kg_path"] = args.kg
        out["kg_backup"] = str(backup)
    print(json.dumps(out, ensure_ascii=False, indent=2)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
