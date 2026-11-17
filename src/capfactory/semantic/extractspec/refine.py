"""二次抽取：基于已有抽取结果，回到原文对应段落补抽指定目标。

流程：
    locate_paragraphs  按 section_hints + signal_words 选段落（不整篇喂）
    build_prompt       用 refine 配置渲染（含 existing 上下文）
    parse_payload      解析 JSON 并逐字段校验（required/enum/max_chars）
    apply_to_graph     建节点 + 挂父关系（append/overwrite）
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import loader
from .schema import FieldSpec, RefineSpec

_PARA_SPLIT = re.compile(r"\n\s*\n")


def _lines(md: Path) -> List[str]:
    raw = md.read_bytes().decode("utf-8", errors="replace")
    return raw.replace("\x00", "").splitlines()


def locate_paragraphs(md: Path, spec: RefineSpec) -> List[Dict[str, Any]]:
    """按 signal_words / section_hints 给段落打分，取前 max_paragraphs。"""
    lines = _lines(md)
    text = "\n".join(lines)
    paras, pos = [], 0
    for m in _PARA_SPLIT.finditer(text):
        seg = text[pos:m.start()]
        if seg.strip():
            paras.append({"start": pos, "text": seg.strip()})
        pos = m.end()
    if text[pos:].strip():
        paras.append({"start": pos, "text": text[pos:].strip()})
    hints = [h.lower() for h in spec.section_hints]
    words = [w.lower() for w in spec.signal_words]
    scored = []
    for p in paras:
        low = p["text"].lower()
        if len(p["text"]) < 60:
            continue
        # 图表标题与参考文献不算证据段落
        if re.match(r"\s*(table|figure|fig\.|algorithm \d|equation)\b", low):
            continue
        if re.match(r"\s*(references|bibliography)\b", low):
            break
        s = sum(3 for w in words if w in low)
        s += sum(5 for h in hints if h in low)
        if s:
            scored.append({**p, "score": s,
                           "line": text[:p["start"]].count("\n") + 1})
    scored.sort(key=lambda x: (-x["score"], x["start"]))
    n = int((spec.locate or {}).get("max_paragraphs") or 6)
    return scored[:n]


def _existing(graph: Any, spec: RefineSpec, aid: str) -> str:
    """把该论文已有的相关节点摘要成一段，供模型对齐命名。"""
    if graph is None:
        return "(无)"
    bits = []
    for t in ("Algorithm", "AlgorithmModule", "Benchmark"):
        for n in graph.by_type(t):
            pid = str(n.attrs.get("paper_id") or "")
            if pid and pid.endswith(aid):
                bits.append(f"{t}:{n.label}")
    return ", ".join(bits[:40]) or "(无)"


def build_prompt(spec: RefineSpec, *, context: str, existing: str,
                 compact: bool = False) -> str:
    if compact:
        # OpenRouter 免费推理模型对长说明+字段列表易返回空串；
        # 极简「任务 + JSON 示例 + 原文」结构实测稳定。
        import re as _re
        m = _re.search(r"输出 JSON：\{\"(\w+)\"", spec.template)
        wrapper = m.group(1) if m else spec.refine.split("_")[-1] + "s"
        demo = ", ".join(
            f'\"{f.name}\":\"{("|".join(f.enum) if f.enum else "...")}\"'
            for f in spec.fields)
        task = spec.template.strip().splitlines()[0]
        return (f"{task}\n输出 {{\"{wrapper}\":[{{{demo}}}]}}。只输出JSON。\n\n"
                f"原文：{context}")
    fields = "\n".join(
        f"- {f.name}: {f.type}"
        + (f"（枚举 {'|'.join(f.enum)}）" if f.enum else "")
        + ("（必填）" if f.required else "")
        + (f"（≤{f.max_chars} 字）" if f.max_chars else "")
        for f in spec.fields)
    body = spec.template
    for k, v in (("context", context), ("existing", existing),
                 ("fields", fields), ("parent", spec.parent_class)):
        body = body.replace("{" + k + "}", v or "(无)")
    head = ("你是知识图谱抽取器。只输出纯 JSON（无代码块、无解释）。\n"
            "不确定就留空，禁止编造；evidence 必须从原文逐字复制。\n")
    return head + body


def parse_payload(spec: RefineSpec, payload: Any) -> Dict[str, Any]:
    """解析并校验；返回 {items, issues}。items 中每项只保留声明字段。"""
    issues: List[str] = []
    if isinstance(payload, str):
        try:
            from ...utils import parse_llm_json
            payload = parse_llm_json(payload)
        except Exception:  # noqa: BLE001
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError as exc:
                return {"items": [], "issues": [f"JSON 解析失败: {exc}"]}
    if isinstance(payload, list):
        arr = payload                      # 部分模型直接返回顶层数组
    elif isinstance(payload, dict):
        arr = None
    else:
        return {"items": [], "issues": ["顶层不是对象"]}
    if isinstance(payload, dict):
        for v in payload.values():
            if isinstance(v, list):
                arr = v
                break
    if arr is None:
        return {"items": [], "issues": [f"未找到数组字段：{list(payload)}"]}
    items = []
    for i, raw in enumerate(arr[:20]):
        if not isinstance(raw, dict):
            issues.append(f"[{i}] 不是对象")
            continue
        row: Dict[str, Any] = {}
        bad = False
        for f in spec.fields:
            v = raw.get(f.name)
            if v in (None, "", []):
                if f.required:
                    issues.append(f"[{i}] 缺必填 {f.name}")
                    bad = True
                continue
            if f.enum and str(v) not in f.enum:
                issues.append(f"[{i}] {f.name}={v!r} 不在枚举 {f.enum}")
                bad = True
                continue
            if f.type == "list":
                if not isinstance(v, list):
                    v = [v]
                v = [str(x)[: f.max_chars or 60] for x in v][: f.max_items or 6]
            elif f.type == "int":
                try:
                    v = int(float(v))
                except (TypeError, ValueError):
                    issues.append(f"[{i}] {f.name} 不是整数")
                    continue
            else:
                v = str(v)[: f.max_chars or 200]
            row[f.name] = v
        if row and not bad:
            items.append(row)
    return {"items": items, "issues": issues}


def _paper_of(graph: Any, node: Any) -> str:
    pid = str(node.attrs.get("paper_id") or "")
    if pid:
        return pid.split(":")[-1]
    aid = str(node.attrs.get("arxiv_id") or "")
    if aid:
        return aid
    return str(node.id).split(":")[-1]


def apply_to_graph(graph: Any, spec: RefineSpec, aid: str,
                   items: List[Dict[str, Any]]) -> Dict[str, Any]:
    parents = [n for n in graph.by_type(spec.parent_class)
               if _paper_of(graph, n) == aid]
    if not parents and spec.parent_class == "Algorithm":
        # 算法跨论文共享 id（algorithm:molminer 无 paper_id），
        # 通过 Paper -PROPOSES_METHOD-> Algorithm 反查父节点
        pid = f"paper:{aid}"
        if pid in graph.nodes:
            parents = [graph.nodes[a.target] for a in graph.outgoing(pid, "PROPOSES_METHOD")
                       if a.target in graph.nodes
                       and graph.nodes[a.target].type == "Algorithm"]
    if not parents:
        return {"nodes": 0, "relations": 0, "error": "no_parent"}
    parent = parents[0]
    created: List[str] = []
    for i, row in enumerate(items, 1):
        nid = spec.node_id.format(arxiv_id=aid, n=i,
                                  kind=str(row.get("kind") or "x"),
                                  parent=parent.id)
        if nid in graph.nodes and spec.merge == "append":
            # 重跑（换模型/改配置）时更新同 id 节点，而不是静默跳过
            for k, v in row.items():
                if v not in (None, "", []):
                    graph.nodes[nid].attrs[k] = v
            continue
        label = str(row.get("statement") or row.get("name") or
                    f"{spec.cls} {i}")[:80]
        graph.node(nid, spec.cls, label, layer="semantic",
                   paper_id=parent.id, miner=f"refine:{spec.refine}", **row)
        if spec.relation:
            graph.assert_rel(parent.id, nid, spec.relation, layer="semantic")
        created.append(nid)
    return {"nodes": len(created), "relations": len(created),
            "parent": parent.id, "ids": created}


def run_refine(graph: Any, aid: str, name: str, *, chat_fn: Any = None,
               md_dir: Any = "data/docx", dry_run: bool = False,
               length: int = 1200, compact: bool = False) -> Dict[str, Any]:
    """跑一个二次抽取目标；dry_run=True 只返回 prompt 与候选段落。"""
    specs = loader.refines() or {}
    if name not in specs:
        return {"ok": False, "error": f"未找到 refine 配置：{name}",
                "available": sorted(specs)}
    spec = specs[name]
    md = Path(md_dir) / (aid + ".md")
    if not md.exists():
        return {"ok": False, "error": f"md 不存在：{md}"}
    paras = locate_paragraphs(md, spec)
    if not paras:
        return {"ok": False, "error": "未匹配到候选段落",
                "hint": f"检查 section_hints/signal_words：{spec.section_hints}"}
    ctx = "\n\n".join(p["text"][:length] for p in paras)
    prompt = build_prompt(spec, context=ctx,
                          existing=_existing(graph, spec, aid),
                          compact=compact)
    base = {"ok": True, "refine": name, "target": spec.cls,
            "n_paragraphs": len(paras),
            "paragraph_lines": [p["line"] for p in paras],
            "prompt_chars": len(prompt)}
    if dry_run or chat_fn is None:
        return {**base, "dry_run": True, "prompt": prompt,
                "paragraphs": [{"line": p["line"], "score": p["score"],
                                "text": p["text"][:160]} for p in paras]}
    parsed = {"items": [], "issues": []}
    raw = ""
    attempts = 3
    for attempt in range(attempts):
        try:
            raw = chat_fn(prompt)
        except Exception as exc:  # noqa: BLE001
            parsed["issues"].append(f"attempt{attempt}: {type(exc).__name__}")
            continue
        parsed = parse_payload(spec, raw)
        if parsed["items"]:
            break
        parsed["issues"].append(f"attempt{attempt}: empty")
    if not parsed["items"]:
        return {**base, "ok": False, "issues": parsed["issues"],
                "raw_head": str(raw)[:120]}
    applied = (apply_to_graph(graph, spec, aid, parsed["items"])
               if parsed["items"] else {"nodes": 0, "relations": 0})
    return {**base, "dry_run": False, "items": parsed["items"],
            "issues": parsed["issues"], "applied": applied}
