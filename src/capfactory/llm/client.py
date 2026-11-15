"""LLM 客户端（OpenAI 兼容协议）.

特性
----
- 兼容 OpenRouter / vLLM / OpenAI / 任何 OpenAI 协议网关
- 磁盘缓存（相同请求不重复计费）
- 指数退避重试（429 / 5xx / 超时）
- 并发闸门，避免免费模型触发限流
- 「推理型」模型空回复自动扩容重试
- 离线模式：不发起网络请求，交由上层规则回退
"""

from __future__ import annotations

import json
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import Settings, api_key, get_settings
from ..utils import parse_json_block, read_json, short_hash, write_json

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 520, 522, 524}


class LLMError(RuntimeError):
    """LLM 调用失败。"""


class OfflineError(LLMError):
    """离线模式下的调用。"""


@dataclass
class LLMResponse:
    """单次 LLM 调用结果。"""

    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency: float = 0.0
    cached: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def json(self) -> Any:
        return parse_json_block(self.text)


class LLMClient:
    """带缓存与重试的同步 LLM 客户端（线程安全）。"""

    _semaphores: Dict[int, threading.Semaphore] = {}
    _stats_lock = threading.Lock()
    _stats: Dict[str, int] = {"calls": 0, "cache_hits": 0, "prompt_tokens": 0, "completion_tokens": 0}

    def __init__(self, settings: Optional[Settings] = None, offline: Optional[bool] = None):
        self.settings = settings or get_settings()
        cfg = self.settings.llm
        self.base_url = str(cfg.get("base_url", "")).rstrip("/")
        self.api_key = api_key(self.settings)
        self.default_model = cfg.get("model")
        self.temperature = float(cfg.get("temperature", 0.2))
        self.max_tokens = int(cfg.get("max_tokens", 6000))
        self.max_retries = int(cfg.get("max_retries", 4))
        self.timeout = int(cfg.get("timeout", 180))
        self.offline = bool(cfg.get("offline", False)) if offline is None else offline
        self.cache_dir = self.settings.path("cache_dir") / "llm"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        limit = int(cfg.get("max_concurrency", 2))
        if limit not in LLMClient._semaphores:
            LLMClient._semaphores[limit] = threading.Semaphore(limit)
        self._sem = LLMClient._semaphores[limit]

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------
    def available(self) -> bool:
        """是否具备真实调用条件。"""
        return bool(self.api_key) and not self.offline

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        json_mode: bool = False,
        use_cache: bool = True,
        tag: str = "",
    ) -> LLMResponse:
        """发起一次对话补全。"""
        model = model or self.default_model
        max_tokens = int(max_tokens or self.max_tokens)
        temperature = self.temperature if temperature is None else temperature

        if self.offline or not self.api_key:
            raise OfflineError("LLM 处于离线模式或未配置 API Key")

        cache_key = short_hash(
            model, json.dumps(messages, ensure_ascii=False, sort_keys=True),
            max_tokens, temperature, json_mode, length=32,
        )
        cache_file = self.cache_dir / f"{cache_key}.json"
        if use_cache:
            cached = read_json(cache_file)
            if cached and cached.get("text"):
                with LLMClient._stats_lock:
                    LLMClient._stats["cache_hits"] += 1
                return LLMResponse(
                    text=cached["text"],
                    model=cached.get("model", model),
                    prompt_tokens=cached.get("prompt_tokens", 0),
                    completion_tokens=cached.get("completion_tokens", 0),
                    cached=True,
                )

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        resp = self._post_with_retry(payload, tag=tag)
        text = resp.text
        # 推理型模型可能把预算耗在 reasoning 上导致 content 为空 → 扩容重试一次
        if not text.strip() and resp.completion_tokens:
            logger.warning("LLM 返回空内容（可能被 reasoning 占满预算），扩容重试：%s", tag)
            payload["max_tokens"] = min(max_tokens * 2, 16000)
            resp = self._post_with_retry(payload, tag=tag)

        if use_cache and resp.text.strip():
            write_json(cache_file, {
                "text": resp.text,
                "model": resp.model,
                "prompt_tokens": resp.prompt_tokens,
                "completion_tokens": resp.completion_tokens,
                "tag": tag,
            })

        with LLMClient._stats_lock:
            LLMClient._stats["calls"] += 1
            LLMClient._stats["prompt_tokens"] += resp.prompt_tokens
            LLMClient._stats["completion_tokens"] += resp.completion_tokens
        return resp

    def complete_json(
        self,
        system: str,
        user: str,
        *,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        tag: str = "",
        retries: int = 1,
    ) -> Any:
        """要求模型输出 JSON 并解析；解析失败时带纠错提示重试。"""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        last_err: Optional[Exception] = None
        for attempt in range(retries + 1):
            resp = self.chat(
                messages, model=model, max_tokens=max_tokens, json_mode=False, tag=tag
            )
            parsed = resp.json
            if parsed is not None:
                return parsed
            last_err = LLMError(f"JSON 解析失败: {resp.text[:200]}")
            logger.warning("JSON 解析失败（%s，第 %d 次），追加纠错提示重试", tag, attempt + 1)
            messages = messages[:2] + [
                {"role": "assistant", "content": resp.text[:2000]},
                {
                    "role": "user",
                    "content": "上面的输出不是合法 JSON。请只输出合法 JSON，不要任何解释、不要 Markdown 围栏。",
                },
            ]
        raise LLMError(f"LLM 未返回合法 JSON: {last_err}")

    @classmethod
    def stats(cls) -> Dict[str, int]:
        with cls._stats_lock:
            return dict(cls._stats)

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------
    def _post_with_retry(self, payload: Dict[str, Any], tag: str = "") -> LLMResponse:
        import requests  # 延迟导入，便于离线环境使用其它模块

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/zjunlp/xKG",
            "X-Title": "CapFactory",
        }
        last_error = ""
        for attempt in range(self.max_retries + 1):
            start = time.time()
            try:
                with self._sem:
                    r = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
                latency = time.time() - start
                if r.status_code in RETRYABLE_STATUS:
                    wait = self._backoff(attempt, r.headers.get("Retry-After"))
                    logger.warning(
                        "LLM %s 返回 %s（%s），%.1fs 后重试 [%d/%d]",
                        tag, r.status_code, r.text[:160], wait, attempt + 1, self.max_retries,
                    )
                    time.sleep(wait)
                    last_error = f"HTTP {r.status_code}"
                    continue
                if r.status_code >= 400:
                    raise LLMError(f"LLM HTTP {r.status_code}: {r.text[:500]}")

                data = r.json()
                choice = (data.get("choices") or [{}])[0]
                message = choice.get("message") or {}
                text = message.get("content") or ""
                if not text and isinstance(message.get("reasoning"), str):
                    text = ""  # 明确不把 reasoning 当正文
                usage = data.get("usage") or {}
                return LLMResponse(
                    text=text.strip(),
                    model=data.get("model", payload.get("model", "")),
                    prompt_tokens=int(usage.get("prompt_tokens") or 0),
                    completion_tokens=int(usage.get("completion_tokens") or 0),
                    latency=latency,
                    raw=data,
                )
            except LLMError:
                raise
            except Exception as exc:  # 网络异常
                wait = self._backoff(attempt)
                logger.warning("LLM %s 调用异常 %s: %s，%.1fs 后重试", tag, type(exc).__name__, exc, wait)
                time.sleep(wait)
                last_error = str(exc)
        raise LLMError(f"LLM 调用失败（重试 {self.max_retries} 次）: {last_error}")

    @staticmethod
    def _backoff(attempt: int, retry_after: Optional[str] = None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), 60.0)
            except (TypeError, ValueError):
                pass
        return min(2 ** attempt + random.random(), 30.0)


class MockLLMClient(LLMClient):
    """测试用：按 tag 返回预置 JSON，不发网络请求。"""

    def __init__(self, responses: Optional[Dict[str, Any]] = None, **kwargs: Any):
        Settings_ = kwargs.pop("settings", None) or get_settings()
        super().__init__(settings=Settings_, offline=True)
        self._responses = responses or {}
        self.calls: List[Dict[str, Any]] = []

    def available(self) -> bool:  # noqa: D102
        return True

    def chat(self, messages, *, model=None, max_tokens=None, temperature=None,  # type: ignore[override]
             json_mode=False, use_cache=True, tag=""):
        self.calls.append({"tag": tag, "messages": messages})
        payload = self._responses.get(tag, self._responses.get("__default__", {}))
        text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        return LLMResponse(text=text, model=model or "mock", prompt_tokens=0, completion_tokens=0)

    def complete_json(self, system, user, *, model=None, max_tokens=None, tag="", retries=0):  # type: ignore[override]
        resp = self.chat([], tag=tag)
        return resp.json


_shared_client: Optional[LLMClient] = None
_shared_lock = threading.Lock()


def get_client(settings: Optional[Settings] = None) -> LLMClient:
    """获取进程级共享客户端。"""
    global _shared_client
    with _shared_lock:
        if _shared_client is None:
            _shared_client = LLMClient(settings)
        return _shared_client


def set_client(client: LLMClient) -> None:
    """替换共享客户端（测试 / 切换模型）。"""
    global _shared_client
    with _shared_lock:
        _shared_client = client
