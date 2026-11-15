"""实体链接：把 LLM 抽出的实体对到图中已有节点（精确 → 别名 → 向量 → 未链接留痕）.

为什么需要它：

* LLM 每抽一次都会造出 ``dataset:CrossDocked``、``Dataset:crossdocked2020``、
  ``dataset:CrossDocked2020(v2)`` 这类同一实体的不同写法；不链接就会让图里
  出现大量重复 Dataset/Target，SOTA 与覆盖统计全部失真。
* 链接是**消歧结果**而不是知识断言，因此写成节点属性
  （``linked_id`` / ``link_method`` / ``link_score``），不新增关系类型，
  避免污染 45 条关系的严格 domain/range。

三级策略与阈值：

1. ``exact``：NFKC + 小写 + 去标点 + 去复数后完全相同；
2. ``alias``：经受控词表归一（``D01→D1``、``maximize→higher``）或去括号/版本后缀后相同；
3. ``vector``：bge-m3 余弦 ≥ ``min_vector_score``（默认 0.80），且类型兼容；
4. ``unresolved``：以上都不中，显式留痕，**不硬凑**。

类型兼容表是关键防线：``Dataset`` 只能链到 ``Dataset``/``Benchmark``，
不会因为名字像就把 ``MCL1``（靶点）链到 ``MCL1/MDM2/GABARAP/RbtA``（数据集）。
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..po.concepts import Concept
from ..po.store import POGraph
from ..po.vocab import default_registry

# 抽取类型 → 允许链接到的图中类型
COMPATIBLE: Dict[str, Tuple[str, ...]] = {
    # 严格同类型：不同粒度（Algorithm vs AlgorithmFamily、Dataset vs Benchmark、
    # Molecule vs CandidateSet）名字可能相同，但语义不同，互相链接会制造假合并。
    "Dataset": ("Dataset",),
    "Benchmark": ("Benchmark",),
    "Target": ("Target",),
    "Organism": ("Organism",),
    "MetricDefinition": ("MetricDefinition",),
    "Algorithm": ("Algorithm",),          # 族级降级在 link() 里单独处理
    "AlgorithmFamily": ("AlgorithmFamily",),
    "Workflow": ("Workflow",),
    "ResearchProblem": ("ResearchProblem",),
    "ProblemCategory": ("ProblemCategory",),
    "Molecule": ("Molecule",),
    "CodeArtifact": ("CodeArtifact",),
    "Paper": ("Paper",),
    "PaperVersion": ("PaperVersion",),
    "Task": ("Task",),
    "Assay": ("Assay",),
    "Endpoint": ("Endpoint",),
    "Domain": ("Domain",),
}
# 只做参考实体链接（新观测/证据/条件不该被合并）
LINKABLE = set(COMPATIBLE)
# 合并时复用已有节点的类型；其余类型一律新建
REUSE = {"Dataset", "Benchmark", "Target", "Organism", "MetricDefinition",
         "Algorithm", "ResearchProblem", "ProblemCategory", "Molecule",
         "CodeArtifact", "Paper", "PaperVersion", "Task", "Assay", "Endpoint",
         "Domain", "AlgorithmFamily"}

_ARXIV = re.compile(r"(\d{4}\.\d{4,5})")
_DOI = re.compile(r"(10\.\d{4,9}/[^\s,;]+)", re.I)
# 上位类允许更低的相似度：把「具体问题」归入 11 个大类本就模糊
SUBSUME_SCORE = 0.52
_VER_SUFFIX = re.compile(r"[\(\[]?\s*(v\d+(\.\d+)*|version\s*\d+)\s*[\)\]]?$", re.I)
_PAREN = re.compile(r"[\(\（][^\)\）]{0,40}[\)\）]")


def normalize_key(text: str) -> str:
    """NFKC + 小写 + 去标点/括号/版本后缀 + 去复数。"""
    s = unicodedata.normalize("NFKC", str(text or "")).lower()
    s = _PAREN.sub(" ", s)
    s = _VER_SUFFIX.sub(" ", s)
    s = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _identifier_keys(label: str, attrs: Optional[Dict[str, Any]] = None) -> List[str]:
    """从标签/属性里抽 arXiv ID 与 DOI，作为身份别名键。"""
    out: List[str] = []
    for text in (f"{label} {json.dumps(attrs or {}, ensure_ascii=False)}",):
        for m in _ARXIV.finditer(text):
            out.append(normalize_key(m.group(1)))
        for m in _DOI.finditer(text):
            out.append(normalize_key(m.group(1).rstrip(".")))
    return list(dict.fromkeys(x for x in out if x))


def singular(key: str) -> str:
    """保守去复数：只处理长度>3 且以 s 结尾的普通词，避免破坏 ChemTS/GATs 等专名。"""
    return key[:-1] if len(key) > 3 and key.endswith("s") and not key.endswith(("ss", "us", "is")) else key


@dataclass
class LinkResult:
    source_id: str
    source_type: str
    source_label: str
    target_id: str = ""
    target_type: str = ""
    target_label: str = ""
    method: str = "unresolved"      # exact | alias | vector | family_fallback | subsume | novel
    score: float = 0.0
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    # 三态：linked（链到具体实例）/ subsumed（落到上位类）/ novel（无着落，进 other 缓冲）
    state: str = "novel"
    subsumed_by: str = ""           # 上位类节点 id（P 类 / AlgorithmFamily）
    reason: str = ""                # 为什么没链上（可解释）

    @property
    def linked(self) -> bool:
        """链到**具体实例**。"""
        return self.state == "linked" and bool(self.target_id)

    @property
    def resolved(self) -> bool:
        """有着落（具体实例或上位类）。"""
        return self.state in ("linked", "subsumed")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EntityLinker:
    """基于图中已有节点的实体链接器。"""

    def __init__(self, graph: POGraph, *, embedder: Any = None,
                 min_vector_score: float = 0.80,
                 family_min_score: float = 0.55) -> None:
        self.graph = graph
        self.min_vector_score = min_vector_score
        self.family_min_score = family_min_score
        # 上位类允许更低的相似度：具体方法名与族名天然不完全同词
        self.family_min_score = family_min_score
        self.embedder = embedder
        self._exact: Dict[Tuple[str, str], str] = {}
        self._alias: Dict[Tuple[str, str], str] = {}
        self._labels: Dict[str, List[str]] = {}
        self._vec: Optional[Dict[str, Any]] = None
        self._build_index()

    # -- 索引 -------------------------------------------------------------
    def _candidates(self, node: Concept) -> Iterable[str]:
        a = node.attrs
        yield node.label
        for k in ("name", "code", "full_name", "title", "metric", "target",
                  "organism", "short_name", "alias", "aliases"):
            v = a.get(k)
            if isinstance(v, str) and v.strip():
                yield v
            elif isinstance(v, (list, tuple)):
                for x in v[:6]:
                    if isinstance(x, str) and x.strip():
                        yield x
        # 论文身份：DOI / arXiv ID / URL / title 变体都可作为别名
        if node.type in ("Paper", "PaperVersion"):
            for k in ("doi", "arxiv_id", "url", "title", "number", "paper_id"):
                v = a.get(k)
                if isinstance(v, str) and v.strip():
                    yield v
            m = _ARXIV.search(str(node.label) + " " + str(a.get("title") or ""))
            if m:
                yield m.group(1)
        # 领域/算法族的中文名与英文别名（vae/gan/gnn/diffusion…）
        if node.type in ("Domain", "AlgorithmFamily"):
            names = {"Domain": "domain_code", "AlgorithmFamily": "algo_code"}[node.type]
            v = a.get("code")
            if v:
                yield str(v)
                if node.type == "AlgorithmFamily":
                    from ..po.vocab import ALGORITHM_FAMILY_TO_CODE
                    for key, code in ALGORITHM_FAMILY_TO_CODE.items():
                        if code == v:
                            yield key.replace("_", " ")
                for canonical in default_registry.values(names):
                    if canonical == v:
                        for raw, canon in default_registry.get(names).aliases.items():
                            if canon == v:
                                yield raw

    def _build_index(self) -> None:
        for node in self.graph.nodes.values():
            keys = {normalize_key(x) for x in self._candidates(node) if x}
            keys.discard("")
            for k in keys:
                self._exact.setdefault((node.type, k), node.id)
                self._alias.setdefault((node.type, k), node.id)
                sk = singular(k)
                if sk != k:
                    self._exact.setdefault((node.type, sk), node.id)
            self._labels.setdefault(node.type, []).append(node.label)

    def _candidate_ids(self, source_type: str) -> List[str]:
        types = COMPATIBLE.get(source_type, ())
        out: List[str] = []
        for t in types:
            out.extend(n.id for n in self.graph.by_type(t))
        return out

    # -- 向量索引（惰性） -------------------------------------------------
    def _ensure_vec(self) -> None:
        if self._vec is not None or self.embedder is None:
            return
        self._vec = {}
        for t in {x for ts in COMPATIBLE.values() for x in ts}:
            ids = [n.id for n in self.graph.by_type(t)]
            if not ids:
                continue
            texts = [self.graph.nodes[i].label for i in ids]
            try:
                mat = self.embedder.embed(texts)
            except Exception:  # noqa: BLE001
                self._vec = {}
                return
            import numpy as np
            norms = np.linalg.norm(mat, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            self._vec.setdefault("items", []).extend(
                {"id": i, "type": t, "vec": mat[k] / norms[k, 0]}
                for k, i in enumerate(ids))

    def _vector_match(self, source_type: str, label: str
                      ) -> Tuple[str, float, List[Dict[str, Any]]]:
        self._ensure_vec()
        if not self._vec or not self.embedder:
            return "", 0.0, []
        import numpy as np
        try:
            q = self.embedder.embed_one(label)
        except Exception:  # noqa: BLE001
            return "", 0.0, []
        qn = q / (np.linalg.norm(q) or 1.0)
        allowed = set(COMPATIBLE.get(source_type, ()))
        scored = [{"id": it["id"], "type": it["type"],
                   "score": float(np.dot(it["vec"], qn))}
                  for it in self._vec.get("items", []) if it["type"] in allowed]
        scored.sort(key=lambda x: -x["score"])
        if not scored:
            return "", 0.0, []
        best = scored[0]
        if best["score"] < self.min_vector_score:
            return "", best["score"], scored[:3]
        return best["id"], best["score"], scored[:3]

    def _vector_match_types(self, types: Sequence[str], label: str,
                            *, threshold: float) -> Tuple[str, float, List[Dict[str, Any]]]:
        """在指定类型集合里做向量匹配（用于上位类归并）。"""
        self._ensure_vec()
        if not self._vec or not self.embedder:
            return "", 0.0, []
        import numpy as np
        try:
            q = self.embedder.embed_one(label)
        except Exception:  # noqa: BLE001
            return "", 0.0, []
        qn = q / (np.linalg.norm(q) or 1.0)
        allowed = set(types)
        scored = [{"id": it["id"], "type": it["type"],
                   "score": float(np.dot(it["vec"], qn))}
                  for it in self._vec.get("items", []) if it["type"] in allowed]
        scored.sort(key=lambda x: -x["score"])
        if not scored:
            return "", 0.0, []
        best = scored[0]
        if best["score"] < threshold:
            return "", best["score"], scored[:3]
        return best["id"], best["score"], scored[:3]

    def _subsume(self, concept: Concept, res: LinkResult) -> bool:
        """粒度错配的处理：把具体实例归**上位类**，而不是硬塞给同级实例。

        - ``ResearchProblem``（论文级具体问题）→ ``ProblemCategory``（P01–P11 大类）；
        - ``Task`` 没有上位节点（``task_family`` 只是属性），交给 other 缓冲并附建议。
        """
        if concept.type == "ResearchProblem":
            tid, score, cands = self._vector_match_types(
                ("ProblemCategory", "ResearchProblem"), concept.label,
                threshold=SUBSUME_SCORE)
            if tid:
                res.candidates = cands
                res.update_target(tid, self.graph.nodes[tid], "subsume", score,
                                  state="subsumed")
                res.subsumed_by = tid
                res.reason = f"论文级具体问题归入上位类（相似度 {score:.2f}）"
                return True
        return False

    # -- 主入口 -----------------------------------------------------------
    def link(self, concept: Concept) -> LinkResult:
        res = LinkResult(source_id=concept.id, source_type=concept.type,
                         source_label=concept.label)
        if concept.type not in LINKABLE:
            res.method = "not_applicable"
            return res

        # 1) 精确（含身份标识：arXiv ID / DOI）
        key = normalize_key(concept.label)
        keys = [key, singular(key)]
        for ident in _identifier_keys(concept.label, concept.attrs):
            keys.append(ident)
        for t in COMPATIBLE.get(concept.type, ()):
            hit = next((self._exact.get((t, k)) for k in keys
                        if self._exact.get((t, k))), "")
            if hit:
                res.update_target(hit, self.graph.nodes[hit], "exact", 1.0)
                return res
        # 2) 别名（词表归一 / 去括号版本）
        for t in COMPATIBLE.get(concept.type, ()):
            for vocab in self._vocab_fields(concept):
                canonical, ok = default_registry.normalize(vocab, concept.label)
                if ok and canonical:
                    hit = self._alias.get((t, normalize_key(canonical)))
                    if hit:
                        res.update_target(hit, self.graph.nodes[hit], "alias", 0.9)
                        return res
            hit = self._alias.get((t, normalize_key(concept.attrs.get("name") or "")))
            if hit:
                res.update_target(hit, self.graph.nodes[hit], "alias", 0.85)
                return res
        # 3) 向量（严格同类型）
        tid, score, cands = self._vector_match(concept.type, concept.label)
        res.candidates = cands
        res.score = round(score, 4)
        if tid:
            res.update_target(tid, self.graph.nodes[tid], "vector", score)
            return res
        # 3.5) 粒度错配 → 上位类（ProblemCategory），标 subsumed 不冒充同义
        if self._subsume(concept, res):
            return res
        # 4) 族级降级：具体算法名（VAE/GAN/GNN）链到算法族
        #    这是明确的粒度降级，标 method=family_fallback，不静默当同义
        if concept.type == "Algorithm":
            # 先按算法族关键词归类：可解释、可复算，优先于向量
            from ..po.taxonomy import classify_with_evidence
            text = " ".join(str(x) for x in (concept.label,
                                             concept.attrs.get("name", ""),
                                             concept.attrs.get("description", ""))
                            if x)
            codes, scores = classify_with_evidence(text, "algo", limit=3)
            if scores and codes:
                code = codes[0]
                fam = next((n for n in self.graph.by_type("AlgorithmFamily")
                            if n.attrs.get("code") == code), None)
                if fam is not None:
                    res.update_target(fam.id, fam, "family_keyword",
                                      scores.get(code, 0.0), state="subsumed")
                    res.subsumed_by = fam.id
                    res.reason = (f"按算法族关键词归入 {code}"
                                  f"（命中 {scores}）")
                    return res
            for label_try in (concept.label, normalize_key(concept.label)):
                canonical, ok = default_registry.normalize("algo_code", label_try)
                if not (ok and canonical):
                    continue
                fam = next((n for n in self.graph.by_type("AlgorithmFamily")
                            if n.attrs.get("code") == canonical), None)
                if fam is not None:
                    res.update_target(fam.id, fam, "family_fallback", 0.95,
                                      state="subsumed")
                    res.subsumed_by = fam.id
                    res.reason = f"具体算法名归入算法族 {canonical}"
                    return res
            ftid, fscore, fcands = self._vector_match_types(
                ("AlgorithmFamily",), concept.label, threshold=self.family_min_score)
            if ftid:
                res.candidates = fcands or res.candidates
                res.update_target(ftid, self.graph.nodes[ftid], "family_fallback", fscore,
                                  state="subsumed")
                res.subsumed_by = ftid
                res.reason = "具体算法名归入算法族（向量）"
                return res
        # 6) 无着落 → novel，交给 other 缓冲（不丢弃、不硬凑）
        res.method = "unresolved"      # 匹配方式：未匹配
        res.state = "novel"            # 结论：无着落，进 other 缓冲
        top = (res.candidates or [{}])[0]
        res.reason = (f"图内无同类型节点；最相近 {top.get('id','-')}"
                      f"（{top.get('score', 0):.2f}）低于阈值 {self.min_vector_score}")
        return res

    def _vocab_fields(self, concept: Concept) -> List[str]:
        from ..po.concepts import CONCEPT_SPECS
        spec = CONCEPT_SPECS.get(concept.type)
        return list(spec.vocab.values()) if spec else []


# dataclass 上补一个便捷方法（保持字段声明简洁）
def _update_target(self: LinkResult, tid: str, node: Concept,
                   method: str, score: float, state: str = "linked") -> None:
    self.target_id = tid
    self.target_type = node.type
    self.target_label = node.label
    self.method = method
    self.score = round(float(score), 4)
    self.state = state


LinkResult.update_target = _update_target  # type: ignore[attr-defined]


def link_extraction(extracted: POGraph, base: POGraph, *,
                    embedder: Any = None, min_vector_score: float = 0.80
                    ) -> Dict[str, Any]:
    """对抽取图的每个参考实体做链接，结果写回节点属性。"""
    linker = EntityLinker(base, embedder=embedder, min_vector_score=min_vector_score)
    stats: Dict[str, Any] = {"total": 0, "linked": 0, "subsumed": 0, "novel": 0,
                             "unresolved": 0, "by_method": {}, "by_state": {},
                             "by_type": {}, "unresolved_samples": [],
                             "subsumed_samples": [], "links": []}
    for node in extracted.nodes.values():
        if node.type not in LINKABLE:
            continue
        res = linker.link(node)
        node.attrs["link_method"] = res.method
        node.attrs["link_score"] = res.score
        node.attrs["link_state"] = res.state
        node.attrs["link_reason"] = res.reason
        if res.linked:
            node.attrs["linked_id"] = res.target_id
            node.attrs["linked_label"] = res.target_label
            stats["linked"] += 1
        elif res.state == "subsumed":
            node.attrs["subsumed_by"] = res.subsumed_by
            node.attrs["linked_id"] = res.subsumed_by
            stats["subsumed"] += 1
            if len(stats["subsumed_samples"]) < 12:
                stats["subsumed_samples"].append(
                    {"type": node.type, "label": node.label,
                     "subsumed_by": res.subsumed_by, "method": res.method,
                     "score": res.score})
        else:
            node.attrs["linked_id"] = ""
            stats["novel"] += 1
            stats["unresolved"] += 1
            if len(stats["unresolved_samples"]) < 12:
                stats["unresolved_samples"].append(
                    {"type": node.type, "label": node.label,
                     "score": res.score, "reason": res.reason})
        stats["by_state"][res.state] = stats["by_state"].get(res.state, 0) + 1
        stats["total"] += 1
        stats["by_method"][res.method] = stats["by_method"].get(res.method, 0) + 1
        stats["by_type"][node.type] = stats["by_type"].get(node.type, 0) + 1
        stats["links"].append(res.to_dict())
    stats["link_rate"] = round(stats["linked"] / stats["total"], 4) if stats["total"] else 0.0
    stats["resolve_rate"] = (round((stats["linked"] + stats["subsumed"]) / stats["total"], 4)
                             if stats["total"] else 0.0)
    return stats


def merge_into(base: POGraph, extracted: POGraph, *,
               embedder: Any = None) -> Dict[str, Any]:
    """把抽取图合并进基础图：参考实体复用已有节点，其余新建。"""
    stats = link_extraction(extracted, base, embedder=embedder)
    id_map: Dict[str, str] = {}
    added_nodes = added_edges = reused = 0
    for node in extracted.nodes.values():
        target = node.attrs.get("linked_id") or ""
        if target and node.type in REUSE and target in base.nodes:
            id_map[node.id] = target
            reused += 1
            continue
        if node.id in base.nodes:          # 幂等：同 id 已存在则复用，不造副本
            id_map[node.id] = node.id
            continue
        new_id = node.id
        node.attrs.pop("linked_id", None)
        base.add(node if new_id == node.id else Concept(
            id=new_id, type=node.type, label=node.label, attrs=node.attrs,
            attribution=node.attribution, evidence_ids=node.evidence_ids))
        id_map[node.id] = new_id
        added_nodes += 1
    for a in extracted.assertions:
        s = id_map.get(a.source, a.source)
        t = id_map.get(a.target, a.target)
        if s not in base.nodes or t not in base.nodes:
            continue
        if base.assert_rel(s, t, a.relation, attribution=a.attribution,
                           evidence_ids=a.evidence_ids):
            added_edges += 1
    return {"link": stats, "reused": reused, "added_nodes": added_nodes,
            "added_edges": added_edges, "id_map": id_map}
