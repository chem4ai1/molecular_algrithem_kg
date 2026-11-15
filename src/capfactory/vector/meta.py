"""元向量（meta-vector）：给每个向量附加可过滤、可加权、可解释的语义标注.

设计依据：

* **sci-rag-kit 的教训**（``domain/prompts/ontology_from_corpus.md``）：
  「语料里没有实例的类型只会浪费抽取时间」——所以标注维度必须能从语料里
  真实取到，取不到就写 ``not_extracted``，不硬填；
* **zotero-research-assistant 的做法**：切块尺寸要基准（Recall/MRR/NDCG），
  索引要审计（覆盖率、字段完整率）——所以元数据带 ``meta_version`` 与
  ``labeler``（rule/llm），可分组统计；
* **本项目语义层**：``section_role`` 对应论文结构，``domain_codes`` /
  ``algo_codes`` 复用 D0–D10 / A01–A18，``problem_ids`` 复用 P01–P11，
  ``entities`` 复用图谱 786 节点。

元向量不是「更多字段」，而是**三种用途**：

1. **过滤**：只在 ``section_role=result`` 里找数值，只在 ``method`` 里找机制；
2. **加权**：``chunk_role=claim`` 的块在「这论文主张什么」查询里加权；
3. **解释**：命中块能回答「它属于哪节、说了什么指标、提到哪些实体」。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

META_VERSION = "meta_v1"

# 论文通用结构（参考 sci-rag-kit 的 section 分类与 zotero 的 PDF 解析）
SECTION_ROLES = {
    "abstract": "abstract",
    "introduction": "introduction",
    "related work": "related_work",
    "background": "background",
    "method": "method", "methods": "method", "methodology": "method",
    "approach": "method", "materials and methods": "method",
    "experiment": "experiment", "experiments": "experiment",
    "experimental setup": "experiment", "evaluation": "experiment",
    "result": "result", "results": "result", "results and discussion": "result",
    "discussion": "discussion",
    "limitation": "limitation", "limitations": "limitation",
    "conclusion": "conclusion", "conclusions": "conclusion",
    "appendix": "appendix", "supplementary": "appendix",
    "reference": "reference", "references": "reference",
}
# 块的语用角色
CHUNK_ROLES = ("claim", "evidence", "protocol", "definition", "limitation",
               "numeric", "background", "mechanism", "other")
# 检索意图（来自 sci-rag-kit 的 query_classes 思想）
QUERY_CLASSES = ("method_mechanism", "benchmark_result", "data_protocol",
                 "limitation_failure", "background_motivation", "code_resource")
# 证据层级（复用 PO 词表）
EVIDENCE_LEVELS = ("computational", "biochemical", "in_vitro", "cellular",
                   "ex_vivo", "animal", "clinical_safety_PK", "clinical_efficacy")

_NUM = re.compile(
    r"(?P<value>-?\d+(?:\.\d+)?)\s*(?P<unit>%|‰|nM|μM|uM|mM|pM|Å|Å|nm|kcal/mol|"
    r"kcal·mol-1|ppb|ppm|M|h|min|s|×|x)?(?![A-Za-z0-9])")
_METRIC_HINT = re.compile(
    r"(validity|valid|uniqueness|novelty|diversity|success rate|success|"
    r"accuracy|auc|auprc|roc|f1|precision|recall|mcc|spearman|pearson|"
    r"rmse|mae|r2|ic50|kd|ki|ec50|mic|selectivity|yield|hit rate|"
    r"docking score|rmsd|tm-score|gdt|pose)", re.I)
def _rx(words: str) -> "re.Pattern[str]":
    return re.compile(r"(?<![a-z0-9])(" + words + r")(?![a-z0-9])", re.I)


# 证据层级：必须词边界，否则 "generate" 会被 "rat" 判成动物实验
_LEVEL_HINT = (
    ("clinical_efficacy", _rx(r"clinical trial|phase (i|ii|iii)|patients?")),
    ("clinical_safety_PK", _rx(r"pharmacokinetic|pk profile|human safety|toxicity in humans")),
    ("animal", _rx(r"mice|mouse|rats?|in vivo|zebrafish|rabbits?|murine")),
    ("cellular", _rx(r"cell line|hela|hek293|in cell|mic assay|cellular assay")),
    ("ex_vivo", _rx(r"ex vivo|tissue slice|organoids?")),
    ("in_vitro", _rx(r"in vitro|spr|itc|fluorescence assay")),
    ("biochemical", _rx(r"enzyme assay|binding affinity|kd|ic50|ki")),
    ("computational", _rx(r"benchmark|dataset|simulation|docking|in silico")),
)


def classify_section(name: str) -> str:
    low = " ".join(str(name or "").lower().split())
    for key, role in SECTION_ROLES.items():
        if low.startswith(key) or key in low:
            return role
    return "other"


def classify_chunk_role(text: str, section: str = "") -> str:
    """规则判定块的语用角色（LLM 标注可覆盖）。"""
    low = (text or "").lower()
    if section in ("experiment", "result") and _NUM.search(text) and _METRIC_HINT.search(low):
        return "numeric"
    if any(k in low for k in ("limitation", "fails to", "cannot", "suffer from",
                              "drawback", "however, ")):
        return "limitation"
    if section == "method" or any(k in low for k in ("we propose", "we introduce",
                                                     "our method", "algorithm 1")):
        return "mechanism"
    if any(k in low for k in ("we show", "results show", "outperform", "achieves",
                              "table ", "figure ", "improv")):
        return "evidence"
    if any(k in low for k in ("we define", "is defined as", "refers to", "denote")):
        return "definition"
    if any(k in low for k in ("dataset", "split", "protocol", "sampling", "baseline")):
        return "protocol"
    if any(k in low for k in ("we claim", "we demonstrate", "can be used", "enables")):
        return "claim"
    if section in ("introduction", "background", "related_work"):
        return "background"
    return "other"


def evidence_level(text: str) -> str:
    for level, rx in _LEVEL_HINT:
        if rx.search(text or ""):
            return level
    return "computational"


def extract_numeric_facts(text: str, *, limit: int = 8) -> List[Dict[str, Any]]:
    """抽取「指标 + 数值 + 单位」三元组；只保留带指标词的句子里的数字。"""
    facts: List[Dict[str, Any]] = []
    for sent in re.split(r"(?<=[.!?。！？])\s+", text or ""):
        metric = _METRIC_HINT.search(sent)
        if not metric:
            continue
        for m in _NUM.finditer(sent):
            raw = m.group("value")
            try:
                val = float(raw)
            except (TypeError, ValueError):
                continue
            if abs(val) > 1e6:
                continue
            facts.append({"metric": metric.group(0).lower(),
                          "value": val, "unit": (m.group("unit") or "").strip(),
                          "sentence": sent[:160]})
            if len(facts) >= limit:
                return facts
    return facts


def build_entity_lexicon(graph: Any, *, types: Sequence[str] = (
        "Dataset", "Benchmark", "Target", "MetricDefinition", "Algorithm",
        "AlgorithmFamily", "ResearchProblem", "Molecule", "CodeArtifact")) -> List[Tuple[str, str, str]]:
    """从图谱构建 (小写表面形式, 节点 id, 类型) 词典，供字符串匹配。"""
    lex: List[Tuple[str, str, str]] = []
    seen = set()
    for t in types:
        for n in graph.by_type(t):
            for surface in {n.label, str(n.attrs.get("name") or "")}:
                s = " ".join(str(surface).split())
                if len(s) < 3 or len(s) > 60:
                    continue
                key = (s.lower(), n.id)
                if key in seen:
                    continue
                seen.add(key)
                lex.append((s, n.id, n.type))
    lex.sort(key=lambda x: -len(x[0]))     # 长实体优先，避免 "MCL1" 抢 "MCL1/MDM2"
    return lex


def match_entities(text: str, lexicon: Sequence[Tuple[str, str, str]],
                   *, limit: int = 12) -> List[Dict[str, Any]]:
    low = " ".join(str(text or "").split()).lower()
    out: List[Dict[str, Any]] = []
    used: List[Tuple[int, int]] = []
    for surface, nid, ntype in lexicon:
        start = low.find(surface.lower())
        while start >= 0:
            end = start + len(surface)
            if not any(a <= start < b or a < end <= b for a, b in used):
                used.append((start, end))
                out.append({"surface": surface, "linked_id": nid, "type": ntype})
                break
            start = low.find(surface.lower(), start + 1)
        if len(out) >= limit:
            break
    return out


def query_class_of(text: str, role: str, section_role: str) -> str:
    """把块映射到检索意图，供检索时按意图调权重。"""
    if section_role in ("limitation",):
        return "limitation_failure"
    if role == "numeric" or _METRIC_HINT.search(text or ""):
        return "benchmark_result"
    if role == "protocol" or any(k in (text or "").lower() for k in
                                 ("dataset", "split", "protocol", "sampling")):
        return "data_protocol"
    if role == "mechanism" or section_role == "method":
        return "method_mechanism"
    if any(k in (text or "").lower() for k in ("github", "code", "repository",
                                               "we release", "we provide")):
        return "code_resource"
    return "background_motivation"


@dataclass
class ChunkMeta:
    """一个向量记录的语义标注（可存 JSONL，可过滤/加权）。"""

    doc_id: str = ""
    paper_title: str = ""
    section_raw: str = ""
    section_role: str = "other"
    chunk_role: str = "other"
    query_class: str = "background_motivation"
    evidence_level: str = "computational"
    domain_codes: List[str] = field(default_factory=list)
    algo_codes: List[str] = field(default_factory=list)
    problem_ids: List[str] = field(default_factory=list)
    entities: List[Dict[str, Any]] = field(default_factory=list)
    numeric_facts: List[Dict[str, Any]] = field(default_factory=list)
    order: int = 0
    chars: int = 0
    lang: str = "en"
    meta_version: str = META_VERSION
    labeler: str = "rule"           # rule | llm

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_meta(chunk: Any, graph: Optional[Any] = None, *,
               lexicon: Optional[Sequence[Tuple[str, str, str]]] = None,
               paper_titles: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """从 chunk + 图谱构建元向量（规则层，不调 LLM）。"""
    text = getattr(chunk, "text", "") or ""
    section = getattr(chunk, "section", "") or ""
    doc = getattr(chunk, "doc_id", "") or ""
    sec_role = classify_section(section)
    role = classify_chunk_role(text, sec_role)
    entities = match_entities(text, lexicon) if lexicon else []
    domains = sorted({e["linked_id"].split(":")[0] for e in entities
                      if e["type"] in ("Dataset", "Benchmark")})
    algos = sorted({e["linked_id"] for e in entities if e["type"] == "Algorithm"})
    problems = sorted({e["linked_id"] for e in entities
                       if e["type"] == "ResearchProblem"})
    meta = ChunkMeta(
        doc_id=doc,
        paper_title=(paper_titles or {}).get(doc, ""),
        section_raw=section[:80],
        section_role=sec_role,
        chunk_role=role,
        query_class=query_class_of(text, role, sec_role),
        evidence_level=evidence_level(text),
        domain_codes=domains,
        algo_codes=algos,
        problem_ids=problems,
        entities=entities,
        numeric_facts=extract_numeric_facts(text),
        order=int(getattr(chunk, "order", 0) or 0),
        chars=len(text),
        lang="zh" if _zh_ratio(text) > 0.3 else "en",
    )
    return meta.to_dict()


def _zh_ratio(text: str) -> float:
    if not text:
        return 0.0
    zh = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    return zh / max(len(text), 1)


def to_embedding_text(text: str, meta: Dict[str, Any]) -> str:
    """把元数据拼进检索文本（轻量上下文注入，避免只有正文）。"""
    parts = [text]
    if meta.get("section_role") and meta["section_role"] != "other":
        parts.append(f"[section:{meta['section_role']}]")
    if meta.get("chunk_role"):
        parts.append(f"[role:{meta['chunk_role']}]")
    if meta.get("entities"):
        names = ", ".join(e["surface"] for e in meta["entities"][:6])
        parts.append(f"[entities:{names}]")
    if meta.get("numeric_facts"):
        facts = "; ".join(
            f"{f.get('metric', '?')}={f.get('value', '?')}{f.get('unit', '')}"
            for f in meta["numeric_facts"][:3])
        parts.append(f"[facts:{facts}]")
    return "\n".join(parts)


def meta_summary(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """标注覆盖率审计（对应 zotero 的 audit_index）。"""
    from collections import Counter
    n = len(rows) or 1
    return {
        "n": len(rows),
        "section_role": dict(Counter(r.get("section_role") for r in rows).most_common()),
        "chunk_role": dict(Counter(r.get("chunk_role") for r in rows).most_common()),
        "query_class": dict(Counter(r.get("query_class") for r in rows).most_common()),
        "evidence_level": dict(Counter(r.get("evidence_level") for r in rows).most_common()),
        "with_entities": round(sum(1 for r in rows if r.get("entities")) / n, 3),
        "with_numeric": round(sum(1 for r in rows if r.get("numeric_facts")) / n, 3),
        "with_domain": round(sum(1 for r in rows if r.get("domain_codes")) / n, 3),
        "with_problem": round(sum(1 for r in rows if r.get("problem_ids")) / n, 3),
        "labeler": dict(Counter(r.get("labeler") for r in rows)),
        "avg_chars": round(sum(int(r.get("chars") or 0) for r in rows) / n, 1),
    }
