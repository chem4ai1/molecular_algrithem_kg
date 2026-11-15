"""抽取质量评估：自由 prompt vs schema prompt，以及语义层（规范化 + 校验 + 链接）的增益.

三组对照：

| 组 | prompt | 后处理 |
|---|---|---|
| ``free`` | 只说「抽实体和关系」，不给 schema | 无 |
| ``schema`` | 给 38 类 / 45 关系 / 词表 / 硬性规则 | 无（看 LLM 原始输出合规率） |
| ``schema+semantics`` | 同上 | 规范化（类型白名单、词表归一）+ 实体链接 + 校验 |

关键指标：类型合法率、关系合法率、词表合规率、必填完整率、证据绑定率、链接率。
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..po.concepts import CONCEPT_SPECS, RELATION_DOMAIN_RANGE
from ..po.prompts import extraction_prompt
from ..po.semantics import build_bundle
from ..po.store import POGraph
from ..po.vocab import default_registry
from ..kbpipe.chunker import Chunk
from ..kbpipe.extractor import OllamaChat, POExtractor
from ..kbpipe.linking import EntityLinker, LINKABLE, link_extraction

FREE_PROMPT = """从下面的论文片段中抽取实体和关系，输出 JSON：

{"entities": [{"type": "实体类型", "name": "实体名"}],
 "relations": [{"source": "实体名", "relation": "关系名", "target": "实体名"}]}

只输出 JSON。"""


def _json_of(text: str) -> Dict[str, Any]:
    """兼容转发：唯一实现在 ``capfactory.utils.parse_llm_json``。"""
    from ..utils import parse_llm_json
    return parse_llm_json(text) or {}

def _types_of(raw: Dict[str, Any]) -> List[str]:
    nodes = raw.get("nodes") or raw.get("entities") or []
    return [str(n.get("type") or "") for n in nodes if isinstance(n, dict)]


def _rels_of(raw: Dict[str, Any]) -> List[str]:
    rels = raw.get("assertions") or raw.get("relations") or []
    return [str(r.get("relation") or r.get("type") or "") for r in rels
            if isinstance(r, dict)]


def metrics_raw(raw: Dict[str, Any]) -> Dict[str, Any]:
    """对 LLM 原始输出直接算合规率（不经任何后处理）。"""
    types = _types_of(raw)
    rels = _rels_of(raw)
    legal_t = [t for t in types if t in CONCEPT_SPECS]
    legal_r = [r for r in rels if r in RELATION_DOMAIN_RANGE]
    return {
        "n_nodes": len(types),
        "n_relations": len(rels),
        "type_validity": round(len(legal_t) / len(types), 4) if types else 0.0,
        "relation_validity": round(len(legal_r) / len(rels), 4) if rels else 0.0,
        "illegal_types": list(Counter(t for t in types if t not in CONCEPT_SPECS).most_common(6)),
        "illegal_relations": list(Counter(r for r in rels
                                          if r not in RELATION_DOMAIN_RANGE).most_common(6)),
    }


def metrics_concepts(nodes: Sequence[Any]) -> Dict[str, Any]:
    """对规范化后的 Concept 算词表/必填/证据合规率。"""
    if not nodes:
        return {"n": 0, "vocab_ok": 0.0, "required_ok": 0.0, "evidence_ok": 0.0}
    vocab_ok = req_ok = ev_ok = 0
    vocab_checks = 0
    for n in nodes:
        spec = CONCEPT_SPECS.get(n.type)
        if not spec:
            continue
        for fld, vocab in spec.vocab.items():
            if fld in n.attrs and n.attrs[fld] not in (None, ""):
                vocab_checks += 1
                _, ok = default_registry.normalize(vocab, n.attrs[fld])
                vocab_ok += int(bool(ok))
        filled = all(n.attrs.get(f) not in (None, "", []) for f in spec.required)
        req_ok += int(filled)
        ev_ok += int(bool(n.evidence_ids))
    return {
        "n": len(nodes),
        "vocab_ok": round(vocab_ok / vocab_checks, 4) if vocab_checks else 1.0,
        "vocab_checks": vocab_checks,
        "required_ok": round(req_ok / len(nodes), 4),
        "evidence_ok": round(ev_ok / len(nodes), 4),
    }


def pick_chunks(chunks: Sequence[Chunk], per_doc: int = 1) -> List[Chunk]:
    """每篇优先取 abstract / method / result 的第一块。"""
    by_doc: Dict[str, List[Chunk]] = {}
    for c in chunks:
        by_doc.setdefault(c.doc_id, []).append(c)
    out: List[Chunk] = []
    for doc, items in by_doc.items():
        items.sort(key=lambda c: (0 if c.section.lower().startswith(
            ("abstract", "method", "result")) else 1, c.order))
        out.extend(items[:per_doc])
    return out


def run_group(chunks: Sequence[Chunk], *, mode: str,
              chat: Optional[OllamaChat] = None,
              base: Optional[POGraph] = None,
              embedder: Any = None,
              reuse: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """跑一组（free / schema / schema+semantics），返回逐块结果与汇总。"""
    chat = chat or OllamaChat()
    bundle = build_bundle(include_vocab=False)
    extractor = POExtractor(chat_fn=chat, max_nodes=14)
    rows: List[Dict[str, Any]] = []
    t0 = time.time()
    reuse_raw = {r["chunk_id"]: r for r in (reuse or [])}
    for c in chunks:
        if mode == "free":
            prompt = FREE_PROMPT + f"\n\n片段：\n{c.text[:3000]}"
        else:
            prompt = extraction_prompt(text=c.text, paper_id=c.doc_id,
                                       paper_version_id=f"version:{c.doc_id}",
                                       evidence_locator=c.section,
                                       bundle=bundle, max_nodes=14)
        if c.id in reuse_raw:          # 复用上一组已拿到的 LLM 输出，避免重复调用
            raw = reuse_raw[c.id].get("_raw") or {}
            raw_text = json.dumps(raw, ensure_ascii=False)
            prompt = ""
        else:
            raw_text = chat(prompt)
            raw = _json_of(raw_text)
        row: Dict[str, Any] = {
            "chunk_id": c.id, "doc_id": c.doc_id, "section": c.section,
            "prompt_chars": len(prompt), "raw_chars": len(raw_text),
            "raw": metrics_raw(raw), "_raw": raw,
        }
        if mode != "free":
            res = extractor.normalize(raw, chunk=c, paper_id=c.doc_id,
                                      version_id=f"version:{c.doc_id}")
            nodes = [n for n in (extractor.to_graph([res]).nodes.values())]
            row["normalized"] = {
                "nodes": res.kept, "assertions": len(res.assertions),
                "problems": res.problems[:8],
                "concept_metrics": metrics_concepts(nodes),
            }
            if base is not None and mode == "schema+semantics":
                ex = extractor.to_graph([res])
                link = link_extraction(ex, base, embedder=embedder)
                row["link"] = {k: link[k] for k in
                               ("total", "linked", "unresolved", "by_method", "link_rate")}
                row["link_samples"] = link["links"][:6]
                row["links_all"] = link["links"]
        rows.append(row)
    total_nodes = sum(r["raw"]["n_nodes"] for r in rows)
    total_rels = sum(r["raw"]["n_relations"] for r in rows)
    agg: Dict[str, Any] = {
        "mode": mode, "chunks": len(rows), "seconds": round(time.time() - t0, 1),
        "n_nodes": total_nodes, "n_relations": total_rels,
        "type_validity": round(sum(r["raw"]["type_validity"] * r["raw"]["n_nodes"]
                                   for r in rows) / total_nodes, 4) if total_nodes else 0.0,
        "relation_validity": round(sum(r["raw"]["relation_validity"] * r["raw"]["n_relations"]
                                       for r in rows) / total_rels, 4) if total_rels else 0.0,
        "illegal_types": list(Counter(t for r in rows
                                      for t, _ in r["raw"]["illegal_types"]).most_common(8)),
        "illegal_relations": list(Counter(t for r in rows
                                          for t, _ in r["raw"]["illegal_relations"]).most_common(8)),
        "rows": rows,
    }
    if mode != "free":
        nm = [r["normalized"] for r in rows if "normalized" in r]
        n = sum(x["nodes"] for x in nm)
        agg["normalized"] = {
            "nodes": n,
            "assertions": sum(x["assertions"] for x in nm),
            "problems": sum(len(x["problems"]) for x in nm),
            "vocab_ok": round(sum(x["concept_metrics"]["vocab_ok"] * x["concept_metrics"]["n"]
                                  for x in nm) / n, 4) if n else 0.0,
            "required_ok": round(sum(x["concept_metrics"]["required_ok"] * x["concept_metrics"]["n"]
                                     for x in nm) / n, 4) if n else 0.0,
            "evidence_ok": round(sum(x["concept_metrics"]["evidence_ok"] * x["concept_metrics"]["n"]
                                     for x in nm) / n, 4) if n else 0.0,
        }
    if mode == "schema+semantics":
        lk = [r["link"] for r in rows if "link" in r]
        tot = sum(x["total"] for x in lk)
        methods: Counter = Counter()
        for x in lk:
            methods.update(x["by_method"])
        agg["link"] = {
            "total": tot,
            "linked": sum(x["linked"] for x in lk),
            "unresolved": sum(x["unresolved"] for x in lk),
            "link_rate": round(sum(x["linked"] for x in lk) / tot, 4) if tot else 0.0,
            "by_method": dict(methods),
        }
    return agg


def compare(chunks: Sequence[Chunk], *, base: POGraph,
            chat: Optional[OllamaChat] = None,
            embedder: Any = None,
            modes: Sequence[str] = ("free", "schema", "schema+semantics")
            ) -> Dict[str, Any]:
    """跑多组对照并给出汇总。"""
    out = {"groups": [], "chunks": len(chunks)}
    schema_rows: Optional[List[Dict[str, Any]]] = None
    for m in modes:
        if m == "schema+semantics":
            g = run_group(chunks, mode=m, chat=chat, base=base,
                          embedder=embedder, reuse=schema_rows)
        else:
            g = run_group(chunks, mode=m, chat=chat)
        if m == "schema":
            schema_rows = g.get("rows") or []
        out["groups"].append(g)
    return out


RECORD_FIELDS = ("title", "method", "question", "background", "algorithm",
                 "task", "capability", "boundary")


def build_record_chunks(records: Sequence[Dict[str, Any]], n: int = 3) -> List[Chunk]:
    """把报告包 paper_records 拼成伪摘要，用于 round-trip 自洽性测试。"""
    out: List[Chunk] = []
    for r in list(records)[:n]:
        num = str(r.get("paperNumber") or r.get("number") or "")
        parts = [f"{k}: {r[k]}" for k in RECORD_FIELDS
                 if isinstance(r.get(k), str) and r.get(k).strip()]
        out.append(Chunk(id=f"record:{num}", doc_id=num, section="record",
                         order=0, text="\n".join(parts)[:3000]))
    return out


def roundtrip(records: Sequence[Dict[str, Any]], base: POGraph, *,
              chat: Optional[OllamaChat] = None, embedder: Any = None,
              n: int = 3) -> Dict[str, Any]:
    """自洽性测试：从已知论文记录抽取，看能否链接回论文/算法节点。"""
    recs = list(records)[:n]
    chunks = build_record_chunks(recs, n)
    res = run_group(chunks, mode="schema+semantics", chat=chat, base=base,
                    embedder=embedder)
    rows: List[Dict[str, Any]] = []
    hit = total = 0
    expect_missing: List[str] = []
    for row, chunk, rec in zip(res["rows"], chunks, recs):
        num = chunk.doc_id
        method = str(rec.get("method") or "")
        expect = {"Paper": f"paper:{num}"}
        # Algorithm 节点以方法名为主键（algorithm:PepMimic），不是编号
        if method:
            if f"algorithm:{method}" in base.nodes:
                expect["Algorithm"] = f"algorithm:{method}"
            else:
                expect_missing.append(f"algorithm:{method}")
        links = row.get("links_all") or []
        row_hits = []
        for ln in links:
            exp = expect.get(ln["source_type"])
            if not exp:
                continue
            total += 1
            ok = ln.get("target_id") == exp
            hit += int(ok)
            row_hits.append({"type": ln["source_type"], "label": ln["source_label"],
                             "linked": ln.get("target_id"), "expect": exp,
                             "method": ln.get("method"), "ok": ok})
        rows.append({"paper": num, "checks": row_hits,
                     "link": row.get("link"), "nodes": row["normalized"]["nodes"],
                     "assertions": row["normalized"]["assertions"]})
    res["roundtrip"] = {
        "papers": len(chunks), "checks": total, "hits": hit,
        "accuracy": round(hit / total, 4) if total else 0.0,
        "expect_missing": expect_missing,
        "rows": rows,
        "note": ("Paper/Algorithm 的期望链接由 paperNumber 决定；"
                 "抽取常把标题写成 Paper、把方法名写成 Algorithm，"
                 "命中即说明抽取+链接能回到原节点。"),
    }
    return res


def to_markdown(result: Dict[str, Any]) -> str:
    g = {x["mode"]: x for x in result["groups"]}
    lines = ["# 论文知识抽取与实体链接评估", "",
             f"- 样本：{result['chunks']} 个文本块（每篇 1 块，优先 abstract/method/result）",
             f"- 模型：`{(result.get('model') or 'qwen3.5:latest')}`（本地 Ollama，think=false）", "",
             "## 1. 抽取层：自由 prompt vs schema prompt", "",
             "| 组 | 块数 | 节点 | 关系 | 类型合法率 | 关系合法率 | 耗时(s) |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for m in ("free", "schema"):
        x = g.get(m)
        if not x:
            continue
        lines.append(f"| {m} | {x['chunks']} | {x['n_nodes']} | {x['n_relations']} | "
                     f"{x['type_validity']:.1%} | {x['relation_validity']:.1%} | {x['seconds']} |")
    free = g.get("free", {})
    schema = g.get("schema", {})
    if free.get("illegal_types"):
        lines.append(f"\n自由 prompt 的非法类型（Top）：`{free['illegal_types'][:6]}`")
    if schema.get("illegal_types"):
        lines.append(f"\nschema prompt 的非法类型（Top）：`{schema['illegal_types'][:6]}`")
    if schema.get("illegal_relations"):
        lines.append(f"\nschema prompt 的非法关系（Top）：`{schema['illegal_relations'][:6]}`")

    lines += ["", "## 2. 语义层增益（规范化 + 校验 + 链接）", "",
              "| 指标 | schema | schema+semantics |", "|---|---:|---:|"]
    rows = [
        ("类型合法率", schema.get("type_validity", 0), schema.get("type_validity", 0)),
        ("关系合法率", schema.get("relation_validity", 0), schema.get("relation_validity", 0)),
        ("词表合规率", schema.get("normalized", {}).get("vocab_ok", 0),
         g.get("schema+semantics", {}).get("normalized", {}).get("vocab_ok", 0)),
        ("必填完整率", schema.get("normalized", {}).get("required_ok", 0),
         g.get("schema+semantics", {}).get("normalized", {}).get("required_ok", 0)),
        ("证据绑定率", schema.get("normalized", {}).get("evidence_ok", 0),
         g.get("schema+semantics", {}).get("normalized", {}).get("evidence_ok", 0)),
    ]
    for name, a, b in rows:
        lines.append(f"| {name} | {a:.1%} | {b:.1%} |")
    link = g.get("schema+semantics", {}).get("link") or {}
    if link:
        lines += ["", "## 3. 实体链接", "",
                  f"- 可链接实体 {link['total']} 个，成功 {link['linked']} 个"
                  f"（**{link['link_rate']:.1%}**），未链接 {link['unresolved']} 个",
                  f"- 方法分布：`{link['by_method']}`"]
    return "\n".join(lines) + "\n"
