"""Stage0 主链筛选 + Stage1 块向量化存储。

用户要求：
* 建立 Paper 根节点时**不需要**表格 / 参考文献 / 相关论文等块；
* 先由大模型**根据小标题**筛选，只保留能建立「以论文为根的主链」的几块；
* 其余块按类型（related_work / method / benchmark）留到第二步肢解；
* 深挖前先把这些块**向量化存储**。
"""
from __future__ import annotations
import json, re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from ..utils import parse_llm_json

HEADING_PROMPT = """你是论文结构筛选器。下面是按小标题列出的章节清单。
请只根据标题判断，输出严格 JSON（纯 JSON，不要代码块）：
{"main_chain":["标题"],"blocks":{"related_work":["标题"],"method":["标题"],
 "benchmark":["标题"]},"skip":["标题"]}
规则：
1. main_chain 只保留能建立「以论文为根的主链」的：摘要/引言的问题与动机、
   方法总体、实验设置、结论。对应 C1-C8 主链（结构/问题/假设/方法/应用/评测/代码/解题路径）。
2. **表格、参考文献、附录、致谢、URL、补充材料一律放 skip**，不进主链。
3. Related Work / Prior Work / 背景比较放 blocks.related_work（第二步建科技树用）。
4. 具体方法/算法/公式/架构小节放 blocks.method（第二步建算法-代码联系用）。
5. 实验/结果/评测/表格正文小节放 blocks.benchmark（第二步深挖数据特征与指标用）。
6. 每个标题只能出现一次；无法判断的放 skip；不要新增清单里没有的标题。
【小标题清单】
{headings}
"""

KIND_RULES = {
    "related_work": ("related work", "prior work", "background", "previous",
                     "literature", "existing method"),
    "method": ("method", "approach", "model", "architecture", "algorithm",
               "preliminar", "training", "sampling", "rollout", "objective"),
    "benchmark": ("experiment", "result", "benchmark", "evaluation", "setup",
                  "dataset", "table", "calibration", "ablation"),
    "skip": ("reference", "bibliography", "appendix", "supplement", "url",
             "acknowledg", "supporting information", "citation"),
}
MAIN_HINTS = ("abstract", "introduction", "conclusion", "overview",
              "1. introduction", "summary")


def rule_screen(headings: Sequence[str]) -> Dict[str, Any]:
    """LLM 不可用时的确定性兜底。"""
    plan: Dict[str, Any] = {"main_chain": [], "blocks": {
        "related_work": [], "method": [], "benchmark": []}, "skip": []}
    for h in headings:
        low = h.lower()
        if any(k in low for k in KIND_RULES["skip"]):
            plan["skip"].append(h)
        elif any(k in low for k in KIND_RULES["related_work"]):
            plan["blocks"]["related_work"].append(h)
        elif any(k in low for k in KIND_RULES["benchmark"]):
            plan["blocks"]["benchmark"].append(h)
        elif any(k in low for k in KIND_RULES["method"]):
            plan["blocks"]["method"].append(h)
        elif any(k in low for k in MAIN_HINTS):
            plan["main_chain"].append(h)
        else:
            plan["skip"].append(h)
    return plan


def screen_headings(headings: Sequence[str], *,
                    chat_fn: Optional[Callable[..., str]] = None,
                    max_tokens: int = 2000, retries: int = 1,
                    router: Any = None) -> Dict[str, Any]:
    """大模型按小标题筛选；校验不通过则规则兜底。"""
    if router is not None:
        listed = "\n".join(f"- {h}" for h in headings)
        prompt = HEADING_PROMPT.replace("{headings}", listed)
        rr = router.run(prompt, stage="heading_screen",
                        validate=lambda out: _validate_plan(
                            parse_llm_json(out) or {}, headings),
                        requested=max_tokens)
        if rr["ok"]:
            data = parse_llm_json(rr["out"]) or {}
            data["source"] = "llm_heading_screen"
            data["router"] = {"backend": rr["backend"],
                              "n_attempts": rr["n_attempts"],
                              "budget": rr["final_budget"].get("max_tokens")}
            return data
        plan = rule_screen(headings)
        plan["source"] = "rule_fallback"
        plan["router"] = {"backend": rr["backend"],
                          "n_attempts": rr["n_attempts"]}
        return plan
    if chat_fn is None:
        from ..llm.backends import chat as _chat
        chat_fn = lambda p, **kw: _chat(p, backend="vllm", **kw)  # noqa: E731
    listed = "\n".join(f"- {h}" for h in headings)
    prompt = HEADING_PROMPT.replace("{headings}", listed)
    for _ in range(retries + 1):
        try:
            out = chat_fn(prompt, max_tokens=max_tokens, timeout=180)
            data = parse_llm_json(out) or {}
            issues = _validate_plan(data, headings)
            if not issues:
                data["source"] = "llm_heading_screen"
                return data
            prompt = (HEADING_PROMPT.replace("{headings}", listed)
                      + "\n【上次输出问题】" + "; ".join(issues[:5]))
        except Exception:  # noqa: BLE001
            break
    plan = rule_screen(headings)
    plan["source"] = "rule_fallback"
    return plan


def _validate_plan(data: Dict[str, Any], headings: Sequence[str]) -> List[str]:
    issues: List[str] = []
    if not isinstance(data.get("main_chain"), list) or not data["main_chain"]:
        issues.append("main_chain 不能为空")
    if not isinstance(data.get("blocks"), dict):
        issues.append("缺 blocks")
        return issues
    for k in ("related_work", "method", "benchmark"):
        if not isinstance(data["blocks"].get(k), list):
            issues.append(f"blocks.{k} 必须是数组")
    seen: List[str] = []
    for h in (data.get("main_chain") or []) + sum(
            [v for v in data["blocks"].values() if isinstance(v, list)], []) + \
            (data.get("skip") or []):
        if h not in headings:
            issues.append(f"幻觉标题:{h[:24]}")
        if h in seen:
            issues.append(f"重复分类:{h[:24]}")
        seen.append(h)
    return issues


def degraded_plan(sections: Dict[str, str]) -> Dict[str, Any]:
    """小标题全是噪声（PDF 把表格标签当标题）时的兜底：按正文长度分块。

    保证至少有一块主链与一块可深挖内容，不让整篇论文静默丢失。
    """
    ranked = sorted(sections, key=lambda h: -len(sections[h]))
    plan: Dict[str, Any] = {"main_chain": ranked[:1],
        "blocks": {"related_work": [], "method": [], "benchmark": []},
        "skip": [], "source": "degraded_by_body_length", "degraded": True}
    for h in ranked[1:4]:
        plan["blocks"]["method"].append(h)
    for h in ranked[4:7]:
        plan["blocks"]["benchmark"].append(h)
    return plan


def ensure_plan(plan: Dict[str, Any], headings: Sequence[str],
                sections: Dict[str, str]) -> Dict[str, Any]:
    if plan.get("main_chain") or any((plan.get("blocks") or {}).values()):
        return plan
    return degraded_plan(sections)


def build_blocks(sections: Dict[str, str], plan: Dict[str, Any], *,
                 max_chars: int = 32000) -> List[Dict[str, Any]]:
    """按筛选结果把章节切成「可深挖的块」；主链块不进这里。"""
    out: List[Dict[str, Any]] = []
    for kind, heads in (plan.get("blocks") or {}).items():
        for i, h in enumerate(heads or []):
            text = sections.get(h, "")
            if len(text) < 80:
                continue
            out.append({"block_id": f"{kind}:{i:02d}", "heading": h,
                        "kind": kind, "text": text[:max_chars],
                        "char_len": len(text), "in_main_chain": False})
    return out


class BlockStore:
    """块的向量化存储与余弦检索（本地 bge-m3，不依赖图数据库）。"""

    def __init__(self, blocks: Sequence[Dict[str, Any]], *,
                 embedder: Any = None) -> None:
        self.blocks: List[Dict[str, Any]] = list(blocks)
        self.vectors: List[List[float]] = []
        self.embedder = embedder
        self.stats: Dict[str, Any] = {"n_blocks": len(self.blocks),
                                      "dim": 0, "embedded": 0,
                                      "fallback": False}

    def vectorize(self) -> Dict[str, Any]:
        if self.embedder is None:
            try:
                from ..vector.embedder import BgeEmbedder
                self.embedder = BgeEmbedder(model="bge-m3:latest")
            except Exception:  # noqa: BLE001
                self.embedder = None
        texts = [f"{b['heading']}\n{b['text'][:1200]}" for b in self.blocks]
        if self.embedder is not None:
            try:
                self.vectors = [list(map(float, v)) for v in
                                self.embedder.embed(texts)]
                self.stats.update({"dim": len(self.vectors[0]) if self.vectors else 0,
                                   "embedded": len(self.vectors)})
                return self.stats
            except Exception:  # noqa: BLE001
                self.embedder = None
        # 兜底：字符 3-gram 哈希向量（不假装是语义向量）
        self.vectors = [self._hash_vec(t) for t in texts]
        self.stats.update({"dim": len(self.vectors[0]) if self.vectors else 0,
                           "embedded": len(self.vectors), "fallback": True})
        return self.stats

    @staticmethod
    def _hash_vec(text: str, dim: int = 256) -> List[float]:
        v = [0.0] * dim
        low = re.sub(r"\W+", " ", (text or "").lower())
        for i in range(max(len(low) - 3, 1)):
            v[hash(low[i:i + 3]) % dim] += 1.0
        n = sum(x * x for x in v) ** 0.5 or 1.0
        return [x / n for x in v]

    def save(self, path: str | Path) -> str:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            for b, v in zip(self.blocks, self.vectors):
                fh.write(json.dumps({**b, "vector": v}, ensure_ascii=False) + "\n")
        return str(p)

    def search(self, query: str, *, top_k: int = 4,
               kind: Optional[str] = None) -> List[Dict[str, Any]]:
        q = self._query_vec(query)
        out = []
        for b, v in zip(self.blocks, self.vectors):
            if kind and b["kind"] != kind:
                continue
            score = sum(a * c for a, c in zip(q, v))
            out.append({"block_id": b["block_id"], "heading": b["heading"],
                        "kind": b["kind"], "score": round(score, 4),
                        "char_len": b["char_len"]})
        return sorted(out, key=lambda x: -x["score"])[:top_k]

    def _query_vec(self, query: str) -> List[float]:
        if self.embedder is not None and not self.stats.get("fallback"):
            try:
                return list(map(float, self.embedder.embed_one(query)))
            except Exception:  # noqa: BLE001
                pass
        return self._hash_vec(query)


def build_main_chain(graph: Any, *, paper_id: str,
                     sections: Dict[str, str],
                     plan: Dict[str, Any]) -> Dict[str, Any]:
    """Stage0：只用 main_chain 小节建「以 Paper 为根的主链」节点。

    表格、参考文献、相关论文节点**刻意不建**（用户要求留到第二步）。
    """
    kept = [h for h in plan.get("main_chain", []) if h in sections]
    made: List[str] = []
    for i, h in enumerate(kept):
        sid = f"section:{paper_id.split(':')[-1]}:main:{i}"
        if sid not in graph.nodes:
            graph.node(sid, "Section", h[:70], title=h, order=i,
                       paper_id=paper_id, in_main_chain=True,
                       provenance="heading_screen")
            graph.assert_rel(paper_id, sid, "HAS_SECTION")
            made.append(sid)
    return {"paper_id": paper_id, "main_chain_sections": kept,
            "n_created": len(made), "skipped_kinds":
            list((plan.get("blocks") or {}).keys()),
            "source": plan.get("source", "")}
