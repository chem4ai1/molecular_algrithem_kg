"""词表注入标准（动态词表 + other 扩表 + top20 向量筛选）。

规则：
  1. 不把封闭词表全量塞进 prompt；每个词表只注入与当前文本最相关的 top-K；
  2. 词表数 > VOCAB_LIMIT(20) 时用向量化（bge-m3，失败回退字符 n-gram）选 top20；
  3. 模型发现词表外的新类时输出 `other` + `proposed_new`，由 `observe()` 收集；
     候选出现 >= PROMOTE_AFTER(2) 次自动 `promote()` 进词表；
  4. 词表持久化到 vocab.json，下一轮抽取自动带上新类。
"""
from __future__ import annotations
import json, math, re
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

VOCAB_LIMIT = 20
PROMOTE_AFTER = 2
VOCAB_FILE = Path("storage_cf/sciforge/semantic_extraction/vocab.json")


def _task_types() -> List[str]:
    try:
        from ...sciforge.algorithm_problem import TASK_TYPES
        return sorted(TASK_TYPES)
    except Exception:  # noqa: BLE001
        return []


def _families() -> List[str]:
    try:
        from ...sciforge.algorithm_schema import FAMILY_IDS
        return sorted(FAMILY_IDS)
    except Exception:  # noqa: BLE001
        return []


def _func_types() -> List[str]:
    return ["forward", "generator", "loss", "init", "io", "transform",
            "accessor", "optimizer", "scheduler", "class", "helper", "train"]


BASE_VOCABS: Dict[str, List[str]] = {
    "task_type": _task_types(),
    "form": ["SMILES", "3D坐标", "向量", "图", "序列", "分布", "标量", "文本"],
    "domain_code": [f"D{i}" for i in range(11)],
    "flow_family": _families(),
    "func_type": _func_types(),
    "problem_category": _task_types(),
    # --- 写作方法论枚举（词表驱动，允许 other + proposed_new 自动扩表）---
    "paradigm": ["formal", "empirical", "design", "interpretive"],
    "evidence_type": ["causal_inference", "derivational", "experimental",
                      "simulational", "correlational", "interpretive"],
    "gap_type": ["capability", "scale", "data", "theory", "efficiency"],
    "component_role": ["backbone", "encoder", "decoder", "loss", "sampler", "other"],
    "outcome_class": ["primary", "secondary"],
    "arm_kind": ["main", "baseline", "ablation", "hyperparam"],
    "claimed_strength": ["proven", "supported", "suggests"],
}


def _load() -> Dict[str, Any]:
    if VOCAB_FILE.exists():
        try:
            return json.loads(VOCAB_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {"promoted": {}, "candidates": {}}


def _save(d: Dict[str, Any]) -> None:
    VOCAB_FILE.parent.mkdir(parents=True, exist_ok=True)
    VOCAB_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2),
                          encoding="utf-8")


def values(name: str) -> List[str]:
    d = _load()
    return list(dict.fromkeys(BASE_VOCABS.get(name, [])
                              + d.get("promoted", {}).get(name, [])))


def _char_ngrams(s: str, n: int = 3) -> Dict[str, float]:
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", str(s).lower())
    toks = [s[i:i + n] for i in range(max(len(s) - n + 1, 1))]
    out: Dict[str, float] = {}
    for t in toks:
        out[t] = out.get(t, 0.0) + 1.0
    norm = math.sqrt(sum(v * v for v in out.values())) or 1.0
    return {k: v / norm for k, v in out.items()}


def _cos(a: Dict[str, float], b: Dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


def _vector_scores(query: str, items: Sequence[str]) -> List[float]:
    """向量化打分：bge-m3 优先，失败回退字符 n-gram 余弦。"""
    try:
        import numpy as np
        from ...vector.embedder import BgeEmbedder, cosine
        emb = BgeEmbedder()
        q = emb.embed([query])[0]
        v = emb.embed(list(items))
        return [float(cosine(q, x)) for x in v]
    except Exception:  # noqa: BLE001
        q = _char_ngrams(query)
        return [_cos(q, _char_ngrams(x)) for x in items]


def select(name: str, text: str, *, k: int = VOCAB_LIMIT) -> Tuple[List[str], int]:
    """返回 (注入项, 词表总数)。> k 时按相关度选 top-k。"""
    vals = values(name)
    if len(vals) <= k:
        return vals, len(vals)
    # 字面命中优先，再用向量/字符相似度补足
    low = (text or "").lower()
    literal = [v for v in vals if v.lower() in low]
    rest = [v for v in vals if v not in literal]
    scores = _vector_scores(text or "", rest) if rest else []
    ranked = [v for _, v in sorted(zip(scores, rest), reverse=True)]
    return (literal + ranked)[:k], len(vals)


def observe(name: str, value: str) -> Dict[str, Any]:
    """模型输出词表外值：收集候选，达到阈值自动扩表。"""
    value = str(value or "").strip()
    if not value or value in values(name) or value.lower() == "unknown":
        return {"observed": False}
    d = _load()
    cand = d.setdefault("candidates", {}).setdefault(name, {})
    cand[value] = cand.get(value, 0) + 1
    promoted = False
    if cand[value] >= PROMOTE_AFTER:
        p = d.setdefault("promoted", {}).setdefault(name, [])
        if value not in p:
            p.append(value)
            promoted = True
        cand.pop(value, None)
    _save(d)
    return {"observed": True, "value": value, "count": cand.get(value, 0),
            "promoted": promoted}


def promote(name: str, value: str) -> bool:
    d = _load()
    p = d.setdefault("promoted", {}).setdefault(name, [])
    if value in p or value in BASE_VOCABS.get(name, []):
        return False
    p.append(value)
    d.setdefault("candidates", {}).setdefault(name, {}).pop(value, None)
    _save(d)
    return True


STAGE_VOCABS: Dict[str, Tuple[str, ...]] = {
    "E1_paper": ("problem_category", "domain_code", "paradigm", "evidence_type"),
    "E2_algorithm": ("task_type", "component_role"),
    "E3_benchmark": ("form", "outcome_class", "arm_kind"),
    "E4_values": ("outcome_class", "arm_kind"),
    "E5_relations": (),       # 工具/公式是自由文本
    "E6_lineage": (),         # 方法名是自由文本
}


def render(text: str, *, k: int = VOCAB_LIMIT,
           stage: str | None = None) -> str:
    """生成注入 prompt 的精简词表块（每类最多 k 项）。"""
    names = STAGE_VOCABS.get(stage, tuple(BASE_VOCABS)) \
        if stage else tuple(BASE_VOCABS)
    if not names:
        return ""   # 该阶段无词表需求，直接不注入
    lines = ["【动态词表 · 每类只列与本文最相关的 top" + str(k) + "】"]
    for name in names:
        items, total = select(name, text, k=k)
        if not items:
            continue
        lines.append(f"- {name}（共 {total} 项，本次注入 {len(items)}）："
                     + ", ".join(items))
        if total > k:
            lines.append("  （已按向量相似度筛选，未列全量）")
    lines += [
        "规则：优先从上面的词表里选；若确实出现了词表外的新类，"
        '输出 "other" 并在 proposed_new 里写出建议的新类名，'
        "系统会自动收集并扩充词表，不要静默丢弃。",
    ]
    return "\n".join(lines)


def stats() -> Dict[str, Any]:
    d = _load()
    return {"limit": VOCAB_LIMIT, "promote_after": PROMOTE_AFTER,
            "sizes": {n: len(values(n)) for n in BASE_VOCABS},
            "promoted": {k: len(v) for k, v in d.get("promoted", {}).items()},
            "candidates": {k: len(v) for k, v
                           in d.get("candidates", {}).items()}}
