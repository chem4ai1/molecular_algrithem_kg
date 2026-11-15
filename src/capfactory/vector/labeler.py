"""LLM 元数据标注：给 chunk 打 section/chunk_role、D/A/P 代码、实体与摘要.

后端降级链（可用性优先，质量其次，代价第三）：

1. ``openrouter``：``nvidia/nemotron-3.5-super-vl:free``（免费，需网络，推理型，慢）；
2. ``qwen38``：本地 vLLM ``Qwen3.8-27B``（``http://127.0.0.1:8000/v1``，离线、稳定）；
3. ``ollama``：本地 ``qwen3.5``（9.7B，最轻）。

标注只做**规则做不到的事**：领域/算法族/问题归属、实体名、一句话摘要。
能由规则稳定判定的（section_role、numeric_facts）以规则为准，LLM 不覆盖，
避免同一字段在不同后端之间漂移。
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..po.vocab import ALGO_NAMES, DOMAIN_NAMES
from .meta import CHUNK_ROLES, EVIDENCE_LEVELS, QUERY_CLASSES, SECTION_ROLES

DEFAULT_VL_MODEL = "nvidia/nemotron-3.5-super-vl:free"
DEFAULT_VLLM_BASE = "http://127.0.0.1:8000/v1"
DEFAULT_VLLM_MODEL = "Qwen3.8-27B"
DEFAULT_OLLAMA = "http://127.0.0.1:11434"

_PROBLEM_HINTS = ("P01", "P02", "P03", "P04", "P05", "P06", "P07", "P08",
                  "P09", "P10", "P11")

LABEL_PROMPT = """你在给 AI 药物发现/分子设计论文的片段做语义标注。只依据片段内容，不确定就留空数组。

可选领域（最多 3 个）：{domains}
可选算法族（最多 3 个）：{algos}
可选问题（最多 3 个）：{problems}

输出 JSON，字段固定：
{{"section_role": "{sections}",
  "chunk_role": "{roles}",
  "query_class": "{qclasses}",
  "evidence_level": "{levels}",
  "domains": ["D1"],
  "algorithms": ["A09"],
  "problems": [],
  "entities": [{{"type": "Dataset|MetricDefinition|Algorithm|Target|Molecule|CodeArtifact", "name": "原文写法"}}],
  "summary": "<=40字，说明这块在讲什么"}}

片段（节：{section}）：
{text}

只输出 JSON。"""


def _json_of(text: str) -> Dict[str, Any]:
    """兼容转发：唯一实现在 ``capfactory.utils.parse_llm_json``。"""
    from ..utils import parse_llm_json
    return parse_llm_json(text) or {}

def _post_json(url: str, payload: Dict[str, Any], headers: Dict[str, str],
               *, timeout: int = 120) -> Dict[str, Any]:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **headers})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = json.loads(r.read().decode("utf-8"))
    body["_latency"] = round(time.time() - t0, 2)
    return body


@dataclass
class Backend:
    name: str
    model: str
    ok: bool = True
    calls: int = 0
    errors: int = 0
    seconds: float = 0.0

    def chat(self, prompt: str, *, max_tokens: int = 900) -> str:  # pragma: no cover
        raise NotImplementedError


class OpenRouterBackend(Backend):
    def __init__(self, model: str = DEFAULT_VL_MODEL, key_file: str =
                 "/home/zengshuxin/API_KEY/openrouter") -> None:
        super().__init__("openrouter", model)
        self.key = os.environ.get("OPENROUTER_API_KEY", "")
        if not self.key:
            try:
                txt = open(key_file, encoding="utf-8", errors="replace").read()
                m = re.search(r"(sk-or-v1-[A-Za-z0-9]{20,})", txt)
                self.key = m.group(1) if m else ""
            except OSError:
                self.key = ""
        self.ok = bool(self.key)

    def chat(self, prompt: str, *, max_tokens: int = 3000) -> str:
        if not self.ok:
            raise RuntimeError("no openrouter key")
        body = _post_json("https://openrouter.ai/api/v1/chat/completions", {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            # 推理型 VL 模型：预算太小会把 token 全花在 reasoning 上，content 为空
            "max_tokens": max(max_tokens, 3000), "temperature": 0.1,
        }, {"Authorization": f"Bearer {self.key}",
            "HTTP-Referer": "https://capfactory.local",
            "X-Title": "CapFactory MetaVector"})
        self.calls += 1
        self.seconds += float(body.get("_latency") or 0)
        try:
            return body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError):
            self.errors += 1
            raise RuntimeError(str(body)[:200])


class VLLMBackend(Backend):
    def __init__(self, base_url: str = DEFAULT_VLLM_BASE,
                 model: str = DEFAULT_VLLM_MODEL) -> None:
        super().__init__("qwen38", model)
        self.base_url = base_url.rstrip("/")

    def available(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/models", timeout=3) as r:
                ids = [m.get("id") for m in json.loads(r.read().decode()).get("data", [])]
            if self.model not in ids and ids:
                self.model = ids[0]
            return bool(ids)
        except Exception:  # noqa: BLE001
            return False

    def chat(self, prompt: str, *, max_tokens: int = 32768,
             timeout: int = 900) -> str:
        """默认 32K 输出、900 s 超时：整篇抽取（40K 输入）需要数分钟。"""
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max(max_tokens, 900), "temperature": 0.1,  # 默认 32K 输出
            # Qwen3 默认开 thinking；标注任务关掉，否则 content 为空
            "chat_template_kwargs": {"enable_thinking": False},
        }
        try:
            body = _post_json(f"{self.base_url}/chat/completions", payload, {}, timeout=timeout)
        except urllib.error.HTTPError:
            payload.pop("chat_template_kwargs", None)   # 老版本 vLLM 不认该参数
            body = _post_json(f"{self.base_url}/chat/completions", payload, {}, timeout=timeout)
        self.calls += 1
        self.seconds += float(body.get("_latency") or 0)
        try:
            return body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError):
            self.errors += 1
            raise RuntimeError(str(body)[:200])


class OllamaBackend(Backend):
    def __init__(self, model: str = "qwen3.5:latest",
                 base_url: str = DEFAULT_OLLAMA) -> None:
        super().__init__("ollama", model)
        self.base_url = base_url.rstrip("/")

    def chat(self, prompt: str, *, max_tokens: int = 900) -> str:
        body = _post_json(f"{self.base_url}/api/generate", {
            "model": self.model, "prompt": prompt, "stream": False,
            "think": False, "format": "json",
            "options": {"temperature": 0.1, "num_predict": max_tokens},
        }, {})
        self.calls += 1
        self.seconds += float(body.get("_latency") or 0)
        return str(body.get("response") or body.get("thinking") or "")


@dataclass
class MetaLabeler:
    """规则 + LLM 混合标注；LLM 失败时保留规则结果并记 ``labeler=rule``。"""

    backends: List[Backend] = field(default_factory=list)
    max_chars: int = 1800
    prefer_llm: bool = True
    stats: Dict[str, Any] = field(default_factory=lambda: {
        "calls": 0, "ok": 0, "failed": 0, "by_backend": {}})

    @classmethod
    def auto(cls, *, prefer_llm: bool = True) -> "MetaLabeler":
        # 顺序即优先级：本地 27B 快且稳；OpenRouter 的推理型 VL 模型在纯文本
        # JSON 任务上常把预算花在 reasoning 上导致 content 为空，故降为备选。
        bs: List[Backend] = []
        v = VLLMBackend()
        if v.available():
            bs.append(v)
        orouter = OpenRouterBackend()
        if orouter.ok:
            bs.append(orouter)
        bs.append(OllamaBackend())
        return cls(backends=[b for b in bs if getattr(b, "ok", True)], prefer_llm=prefer_llm)

    def _prompt(self, text: str, section: str) -> str:
        return LABEL_PROMPT.format(
            domains=", ".join(f"{k}={v}" for k, v in DOMAIN_NAMES.items()),
            algos=", ".join(f"{k}" for k in ALGO_NAMES),
            problems=", ".join(_PROBLEM_HINTS),
            sections="|".join(sorted(set(SECTION_ROLES.values()) | {"other"})),
            roles="|".join(CHUNK_ROLES),
            qclasses="|".join(QUERY_CLASSES),
            levels="|".join(EVIDENCE_LEVELS),
            section=section or "unknown",
            text=(text or "")[: self.max_chars])

    def label(self, text: str, section: str = "") -> Dict[str, Any]:
        if not self.prefer_llm:
            return {}
        prompt = self._prompt(text, section)
        self.stats["calls"] += 1
        for b in self.backends:
            if not getattr(b, "ok", True):
                continue
            try:
                out = b.chat(prompt, max_tokens=700)
                data = _json_of(out)
                if not data:
                    raise RuntimeError("empty json")
                self.stats["ok"] += 1
                self.stats["by_backend"][b.name] = self.stats["by_backend"].get(b.name, 0) + 1
                data["_backend"] = b.name
                return data
            except Exception as exc:  # noqa: BLE001
                self.stats["by_backend"][f"{b.name}_fail"] = \
                    self.stats["by_backend"].get(f"{b.name}_fail", 0) + 1
                continue
        self.stats["failed"] += 1
        return {}

    def label_many(self, items: Sequence[Any], graph: Any, *,
                   workers: int = 4) -> List[Dict[str, Any]]:
        """并发标注一批 chunk，返回 ``[{id, text, meta}]``。"""
        from concurrent.futures import ThreadPoolExecutor
        from .meta import build_entity_lexicon, build_meta

        lexicon = build_entity_lexicon(graph)
        titles = {}
        for p in graph.by_type("Paper"):
            num = str(p.attrs.get("number") or "")
            if num:
                titles[num] = p.label

        def one(ch: Any) -> Dict[str, Any]:
            rule = build_meta(ch, graph, lexicon=lexicon, paper_titles=titles)
            llm = self.label(getattr(ch, "text", ""), getattr(ch, "section", ""))
            meta = self.merge(rule, llm)
            return {"id": getattr(ch, "id", ""), "text": getattr(ch, "text", ""),
                    "meta": meta}

        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            return list(ex.map(one, items))

    def merge(self, rule: Dict[str, Any], llm: Dict[str, Any]) -> Dict[str, Any]:
        """规则优先保护稳定字段；LLM 补语义字段。"""
        out = dict(rule)
        if not llm:
            return out
        for k in ("section_role", "chunk_role", "query_class", "evidence_level"):
            v = llm.get(k)
            if isinstance(v, str) and v.strip():
                # 只在规则判为 other/默认值时采纳 LLM，避免覆盖确定性判定
                if out.get(k) in ("other", "", None) or k == "query_class":
                    out[k] = v.strip()
        for src, dst in (("domains", "domain_codes"), ("algorithms", "algo_codes"),
                         ("problems", "problem_ids")):
            v = llm.get(src)
            if isinstance(v, list) and v:
                out[dst] = [str(x) for x in v if isinstance(x, (str, int, float))][:3]
        ents = llm.get("entities")
        if isinstance(ents, list) and ents:
            merged = {e["surface"].lower(): e for e in out.get("entities") or []}
            for e in ents[:8]:
                if not isinstance(e, dict) or not e.get("name"):
                    continue
                name = str(e["name"]).strip()
                if not name:
                    continue
                merged.setdefault(name.lower(), {
                    "surface": name, "type": str(e.get("type") or "unknown"),
                    "linked_id": "", "source": "llm"})
            out["entities"] = list(merged.values())[:12]
        if llm.get("summary"):
            out["summary"] = str(llm["summary"])[:200]
        out["labeler"] = f"rule+{llm.get('_backend', 'llm')}"
        return out
