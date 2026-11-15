"""文本块 → PO 概念/断言（LLM 抽取 + 确定性校验）.

流程：``chunk`` → ``extraction_prompt``（含 schema 与硬性规则）→ chat →
JSON 解析 → 规范化（词表归一 / 类型白名单）→ ``validate_po_graph`` →
增量写入 ``POGraph``。

设计原则：**LLM 只负责读文本下判断，写入前必须过校验**。
抽取器不直接信任模型给的 id/类型/关系，而是重新映射到词表；
非法字段被丢弃并记录在 ``problems``，不静默进入图。

``chat_fn`` 抽象成 ``(prompt: str) -> str``，因此可接 Ollama（本地、免费）
或任意 OpenAI 兼容端点。
"""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from ..po.concepts import CONCEPT_SPECS, RELATION_DOMAIN_RANGE, Concept
from ..po.prompts import extraction_prompt
from ..po.store import POGraph
from ..po.semantics import build_bundle
from ..po.vocab import default_registry
from ..utils import now_iso

ChatFn = Callable[[str], str]


class OllamaChat:
    """本地 Ollama 文本模型（默认 qwen3.5），作为免费抽取后端。"""

    def __init__(self, model: str = "qwen3.5:latest",
                 base_url: str = "http://127.0.0.1:11434",
                 *, timeout: int = 300, temperature: float = 0.1,
                 num_predict: int = 3000) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.temperature = temperature
        self.num_predict = num_predict
        self.stats = {"calls": 0, "errors": 0, "seconds": 0.0}

    def __call__(self, prompt: str) -> str:
        import time
        payload = {
            "model": self.model, "prompt": prompt, "stream": False,
            "format": "json",
            # qwen3.5 等 thinking 模型默认把正文放进 thinking 字段、response 为空；
            # 显式关闭 think 才能拿到可直接解析的 JSON（实测 138s → <1s）。
            "think": False,
            "options": {"temperature": self.temperature,
                        "num_predict": self.num_predict},
        }
        req = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                body = json.loads(r.read().decode("utf-8"))
            self.stats["calls"] += 1
            resp = str(body.get("response") or "")
            if not resp.strip():
                # 兜底：某些版本仍把 JSON 放在 thinking 里
                thinking = str(body.get("thinking") or "")
                m = re.search(r"\{.*\}", thinking, re.S)
                resp = m.group(0) if m else ""
            return resp
        except Exception as exc:  # noqa: BLE001
            self.stats["errors"] += 1
            return json.dumps({"nodes": [], "assertions": [],
                               "_error": str(exc)[:200]})
        finally:
            self.stats["seconds"] += time.time() - t0


def _json_block(text: str) -> Dict[str, Any]:
    """兼容转发：唯一实现在 ``capfactory.utils.parse_llm_json``。"""
    from ..utils import parse_llm_json
    return parse_llm_json(text) or {}

@dataclass
class ExtractionResult:
    chunk_id: str
    nodes: List[Dict[str, Any]] = field(default_factory=list)
    assertions: List[Dict[str, Any]] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)
    raw_chars: int = 0
    kept: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {"chunk_id": self.chunk_id, "kept": self.kept,
                "nodes": self.nodes, "assertions": self.assertions,
                "problems": self.problems[:30], "raw_chars": self.raw_chars}


class POExtractor:
    """把一个文本块抽成 PO 节点与断言（带校验）。"""

    def __init__(self, chat_fn: Optional[ChatFn] = None, *,
                 max_nodes: int = 20, min_confidence: float = 0.0) -> None:
        self.chat = chat_fn or OllamaChat()
        self.bundle = build_bundle(include_vocab=False)
        self.max_nodes = max_nodes
        self.min_confidence = min_confidence
        self.problems: List[str] = []

    # -- 规范化 -----------------------------------------------------------
    def normalize(self, raw: Dict[str, Any], *, chunk: Any,
                   paper_id: str, version_id: str) -> ExtractionResult:
        res = ExtractionResult(chunk_id=getattr(chunk, "id", ""),
                               raw_chars=len(getattr(chunk, "text", "")))
        allowed = set(CONCEPT_SPECS)
        kept_ids: Dict[str, str] = {}
        for i, n in enumerate((raw.get("nodes") or [])[: self.max_nodes]):
            if not isinstance(n, dict):
                continue
            ntype = str(n.get("type") or "")
            if ntype not in allowed:
                res.problems.append(f"node[{i}] 未知类型 {ntype!r}")
                continue
            label = str(n.get("label") or n.get("id") or "")[:120]
            nid = str(n.get("id") or f"{ntype.lower()}:{getattr(chunk,'order',i)}:{i}")
            attrs = dict(n.get("attrs") or {})
            # 词表归一
            spec = CONCEPT_SPECS[ntype]
            for fld, vocab in spec.vocab.items():
                if fld in attrs and attrs[fld] not in (None, ""):
                    canonical, ok = default_registry.normalize(vocab, attrs[fld])
                    if ok and canonical:
                        attrs[fld] = canonical
                    else:
                        res.problems.append(f"{nid}.{fld}={attrs[fld]!r} 不在词表")
            # 补必填标签类字段
            for fld in spec.required:
                if fld in ("label", "name", "title", "statement", "question") \
                        and fld not in attrs:
                    attrs[fld] = label
            attrs.setdefault("source_chunk", getattr(chunk, "id", ""))
            attrs.setdefault("source_paper", paper_id)
            if ntype == "PaperVersion" and paper_id:
                attrs.setdefault("paper_id", paper_id)
            if ntype == "Task":
                attrs.setdefault("task_family", "other")
            if ntype == "MetricDefinition":
                attrs.setdefault("direction", "higher")
            node = Concept(id=nid, type=ntype, label=label, attrs=attrs,
                           attribution=str(n.get("attribution") or "analyst_synthesis"),
                           evidence_ids=[str(x) for x in (n.get("evidence_ids") or [])][:8],
                           source_version=version_id)
            vp = node.validate(default_registry)
            if vp:
                # 保留节点但记录问题：缺证据/缺字段不阻止入图，便于人工补
                res.problems.extend(vp[:3])
            kept_ids[str(n.get("id") or "")] = nid
            res.nodes.append(node.to_dict())
        for j, a in enumerate((raw.get("assertions") or [])[: self.max_nodes * 2]):
            if not isinstance(a, dict):
                continue
            rel = str(a.get("relation") or "")
            if rel not in RELATION_DOMAIN_RANGE:
                res.problems.append(f"assertion[{j}] 未知关系 {rel!r}")
                continue
            src = kept_ids.get(str(a.get("source") or ""), str(a.get("source") or ""))
            tgt = kept_ids.get(str(a.get("target") or ""), str(a.get("target") or ""))
            if not src or not tgt:
                res.problems.append(f"assertion[{j}] id 未映射")
                continue
            res.assertions.append({"source": src, "target": tgt, "relation": rel,
                                   "attribution": str(a.get("attribution")
                                                      or "analyst_synthesis"),
                                   "evidence_ids": [str(x) for x in
                                                    (a.get("evidence_ids") or [])][:8]})
        res.kept = len(res.nodes)
        return res

    # -- 主入口 -----------------------------------------------------------
    def extract(self, chunk: Any, *, paper_id: str = "",
                version_id: str = "", locator: str = "",
                whole: bool = False) -> ExtractionResult:
        """单块抽取。

        ``whole=True``：该 chunk 是「骨架节整篇」（摘要/引言/结论），
        放开文本上限到 60K 字符、节点上限到 60，配合 32K 输出抽取
        跨节的 ResearchQuestion / ProblemContext / Workflow / Domain。
        """
        prompt = extraction_prompt(
            text=getattr(chunk, "text", ""), paper_id=paper_id,
            paper_version_id=version_id, evidence_locator=locator,
            bundle=self.bundle,
            max_nodes=60 if whole else self.max_nodes,
            max_text_chars=60000 if whole else 12000)
        out = self.chat(prompt)
        raw = _json_block(out)
        return self.normalize(raw, chunk=chunk, paper_id=paper_id,
                               version_id=version_id)

    def to_graph(self, results: Sequence[ExtractionResult], *,
                 graph: Optional[POGraph] = None) -> POGraph:
        """把抽取结果合并进 PO 图（带来源归属）。"""
        g = graph or POGraph("po::extracted::" + now_iso())
        for r in results:
            for nd in r.nodes:
                g.add(Concept.from_dict(nd))
            for a in r.assertions:
                g.assert_rel(a["source"], a["target"], a["relation"],
                             attribution=a.get("attribution", "analyst_synthesis"),
                             evidence_ids=a.get("evidence_ids", []) or [],
                             source_chunk=a.get("source_chunk", ""))
        g.meta["extraction"] = {
            "chunks": len(results),
            "nodes_added": sum(r.kept for r in results),
            "assertions_added": sum(len(r.assertions) for r in results),
            "problems": sum(len(r.problems) for r in results),
            "extracted_at": now_iso(),
        }
        return g
