"""全量 LLM 推断补齐：把族级默认算法升级为「问题/机理」显式卡片。

对每个待补算法：
  ① 从 10 篇论文 md 里选「提到该算法最多」的一篇作为证据来源
  ② local_context 只取算法名附近片段，避免宿主论文主方法污染
  ③ infer_problem_core 用 qwen 分析问题/机理/任务类型
  ④ 规则校验族-任务一致性，冲突时以族为准并记录
  ⑤ 反查原论文引用标号
  ⑥ 写回图节点 + 重建语义检索索引
"""
from __future__ import annotations
import json, time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .algorithm_problem import (TASK_TYPES, CORE_FIELDS, infer_problem_core,
                                find_source_paper, local_context,
                                build_index, FAMILY_TASK)
from .algorithm_schema import classify_rule, FAMILIES

MD_DIR = Path("/home/zengshuxin/xKG-main/data/docx")
OUT = Path("storage_cf/sciforge/algorithm_infer_all_report.json")


def corpus_for(name: str) -> Dict[str, Any]:
    """选提到该算法次数最多的论文；引用式名称用关键词回退。"""
    import re as _re
    terms = [name.lower()]
    if "et al" in name.lower():
        terms += [w.lower() for w in _re.findall(r"[A-Za-z]{3,}", name)
                  if w.lower() not in ("et", "al")]
    best: Dict[str, Any] = {"arxiv_id": "", "hits": 0, "text": ""}
    for p in sorted(MD_DIR.glob("*.md")):
        md = p.read_text(encoding="utf-8", errors="replace")
        low = md.lower()
        n = max(low.count(t) for t in terms)
        if n > best["hits"]:
            best = {"arxiv_id": p.stem, "hits": n, "text": md,
                    "matched_term": max(terms, key=lambda t: low.count(t))}
    return best


def _search_text(n: Any, core: Dict[str, Any]) -> str:
    return (f"{n.label}. 任务类型：{core['task_type_label']}. "
            f"能解决的问题：{' '.join(core['problems_solved'])}. "
            f"机理：{core['mechanism']}. 为什么有效：{core['why_it_works']}. "
            f"适用：{' '.join(core.get('applicable_to') or [])}")


def infer_all(graph: Any, *, chat_fn: Any = None, limit: int = 0,
              persist: bool = True) -> Dict[str, Any]:
    todo = [n for n in graph.by_type("Algorithm")
            if n.attrs.get("filled_by") == "family_default"]
    if limit:
        todo = todo[:limit]
    rep: Dict[str, Any] = {"n_todo": len(todo), "n_ok": 0, "n_failed": 0,
                           "task_conflicts": [], "no_corpus": [],
                           "seconds": 0.0, "per_algorithm": {}}
    t0 = time.time()
    for n in todo:
        name, fam = n.label, n.attrs.get("schema_family") or "autoregressive"
        c = corpus_for(name)
        if not c["arxiv_id"] or c["hits"] == 0:
            rep["no_corpus"].append(name)
            rep["per_algorithm"][name] = {"ok": False,
                                          "reason": "no_paper_mention"}
            continue
        ctx = local_context(name, c["text"])
        try:
            r = infer_problem_core(name, fam, ctx, chat_fn=chat_fn)
        except Exception as exc:  # noqa: BLE001
            r = {"ok": False, "issues": [f"{type(exc).__name__}:{exc}"[:120]]}
        if not r["ok"]:
            rep["n_failed"] += 1
            rep["per_algorithm"][name] = {
                "ok": False, "issues": r.get("issues"),
                "attempts": r.get("attempts")}
            continue
        d = r["data"]
        task = d["task_type"]
        # 族-任务一致性：族默认任务是强先验，LLM 偏离时记录并以族为准
        expected = FAMILY_TASK.get(fam, ("", ""))[0]
        if expected and task != expected:
            rep["task_conflicts"].append(
                {"name": name, "family": fam, "llm": task,
                 "family_default": expected})
        src = find_source_paper(name, c["text"])
        core = {
            "problems_solved": d["problems_solved"],
            "mechanism": d["mechanism"],
            "mechanism_steps": [x.strip() for x in
                                __import__("re").split(r"[；;]", d["mechanism"])
                                if x.strip()][:4],
            "why_it_works": d["why_it_works"],
            "applicable_to": d.get("applicable_to") or [],
            "limitations": d.get("limitations") or [],
            "task_type": task,
            "task_type_label": TASK_TYPES.get(task, task),
            "source_paper": src, "source_ref_no": src.get("ref_no", ""),
            "filled_by": "llm_inference",
            "inference_basis": d.get("inference_basis"),
            "inference_confidence": d.get("confidence"),
            "evidence_paper": c["arxiv_id"],
        }
        obj = n.attrs.get("object_kind") or ""
        core["baseline_group"] = (
            task if obj in ("unknown", "未分类对象", "")
            else f"{task}|{obj}")
        n.attrs.update(core)
        n.attrs["search_text"] = _search_text(n, core)
        rep["n_ok"] += 1
        rep["per_algorithm"][name] = {
            "ok": True, "task_type": task, "attempts": r["attempts"],
            "source": src.get("status"), "evidence_paper": c["arxiv_id"],
            "inference_basis": d.get("inference_basis"),
            "confidence": d.get("confidence")}
    rep["seconds"] = round(time.time() - t0, 1)
    if persist:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        graph.save("storage_cf/sciforge/batch10_final_graph.json")
        rep["index"] = build_index(graph)
    return rep
