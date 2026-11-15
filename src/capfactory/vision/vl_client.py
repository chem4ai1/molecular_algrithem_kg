"""OpenRouter 视觉语言模型客户端（默认 ``nvidia/nemotron-3.5-super-vl:free``）.

用途：把 PDF 页面/图表转成**结构化图注**（图类型、坐标轴、关键数值、结论、
是否表格/分子结构），再入图片库并向量化。

工程要点：
- 图片以 ``data:image/png;base64,...`` 内联，避免公网可访问性要求；
- free 模型有速率限制：遇 429/5xx 指数退避重试，并记录 ``usage``/延迟；
- API key 默认从 ``/home/zengshuxin/API_KEY/openrouter`` 解析（不落日志）；
- 失败返回结构化错误而不是抛异常，便于批量跑时跳过单张图。
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_MODEL = "nvidia/nemotron-3.5-super-vl:free"
DEFAULT_BASE = "https://openrouter.ai/api/v1"
DEFAULT_KEY_FILE = "/home/zengshuxin/API_KEY/openrouter"


def key_from_file(path: str | Path = DEFAULT_KEY_FILE) -> str:
    """从说明文件里解析 ``OPENROUTER_API_KEY=sk-or-v1-...``。"""
    p = Path(path)
    if not p.exists():
        return ""
    txt = p.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"OPENROUTER_API_KEY\s*=\s*(sk-or-v1-[A-Za-z0-9]+)", txt)
    if m:
        return m.group(1)
    m = re.search(r"(sk-or-v1-[A-Za-z0-9]{20,})", txt)
    return m.group(1) if m else ""


def repair_json(text: str) -> Optional[Dict[str, Any]]:
    """兼容转发：唯一实现在 ``capfactory.utils.parse_llm_json``。"""
    from ..utils import parse_llm_json
    return parse_llm_json(text)

def _mime(png: bytes) -> str:
    return "image/png" if png[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"


class OpenRouterVL:
    """最小可用的 OpenRouter 视觉客户端。"""

    def __init__(self, api_key: Optional[str] = None,
                 model: str = DEFAULT_MODEL, base_url: str = DEFAULT_BASE,
                 *, timeout: int = 120, retries: int = 3,
                 referer: str = "https://capfactory.local",
                 title: str = "CapFactory Knowledge Pipeline") -> None:
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "") \
            or key_from_file()
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.referer = referer
        self.title = title
        self.stats = {"calls": 0, "errors": 0, "total_seconds": 0.0,
                      "prompt_tokens": 0, "completion_tokens": 0}

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    # -- HTTP -------------------------------------------------------------
    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        last: Optional[Exception] = None
        for attempt in range(self.retries):
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions", data=data,
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json",
                         "HTTP-Referer": self.referer,
                         "X-Title": self.title})
            try:
                t0 = time.time()
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                self.stats["calls"] += 1
                self.stats["total_seconds"] += time.time() - t0
                usage = body.get("usage") or {}
                self.stats["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
                self.stats["completion_tokens"] += int(usage.get("completion_tokens") or 0)
                body["_latency"] = round(time.time() - t0, 2)
                return body
            except urllib.error.HTTPError as exc:
                last = exc
                status = getattr(exc, "code", 0)
                if status in (429, 500, 502, 503, 504):
                    time.sleep(min(2 ** attempt, 20))
                    continue
                detail = ""
                try:
                    detail = exc.read().decode("utf-8", errors="replace")[:400]
                except Exception:  # noqa: BLE001
                    pass
                self.stats["errors"] += 1
                return {"error": f"HTTP {status}", "detail": detail}
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(min(2 ** attempt, 8))
        self.stats["errors"] += 1
        return {"error": "request_failed", "detail": str(last)[:300]}

    # -- 视觉理解 ---------------------------------------------------------
    def describe(self, png: bytes, prompt: str, *,
                 max_tokens: int = 6000, temperature: float = 0.1,
                 json_mode: bool = False) -> Dict[str, Any]:
        """对单张图调用 VL，返回 ``{ok, text, json, usage, latency, model}``。

        实测结论（``nvidia/nemotron-3.5-super-vl:free``）：
        它是**推理模型**，``response_format=json_object`` 会让 reasoning 吃满
        ``max_tokens`` 而 content 为空；因此默认关闭 json_mode、max_tokens=6000，
        并在“content 为空且 reasoning 占满”时自动降级重试一次。
        """
        if not self.api_key:
            return {"ok": False, "error": "missing_api_key"}
        b64 = base64.b64encode(png).decode("ascii")
        payload = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url",
                     "image_url": {"url": f"data:{_mime(png)};base64,{b64}"}},
                ],
            }],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        body = self._post(payload)
        if "error" in body:
            return {"ok": False, **body, "model": self.model}
        try:
            text = body["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError):
            return {"ok": False, "error": "malformed_response",
                    "raw": json.dumps(body)[:400], "model": self.model}
        usage = body.get("usage") or {}
        reasoning = int((usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0)
        completion = int(usage.get("completion_tokens") or 0)
        # 推理模型把预算全用在 reasoning 上 → 自动降级重试
        if not text.strip() and reasoning > 0 and reasoning >= completion * 0.9:
            payload.pop("response_format", None)
            payload["max_tokens"] = max(max_tokens * 2, 8000)
            retry = self._post(payload)
            if "error" not in retry:
                body = retry
                try:
                    text = body["choices"][0]["message"]["content"] or ""
                except (KeyError, IndexError):
                    text = ""
        parsed = repair_json(text)
        try:
            finish = body["choices"][0].get("finish_reason")
        except (KeyError, IndexError):
            finish = None
        return {"ok": True, "text": text, "json": parsed,
                "finish_reason": finish,
                "partial": bool(parsed and parsed.get("_partial")),
                "usage": body.get("usage") or {},
                "latency": body.get("_latency"),
                "model": body.get("model", self.model)}

    def models(self) -> Dict[str, Any]:
        """查询可用模型（用于确认目标模型存在）。"""
        try:
            req = urllib.request.Request(f"{self.base_url}/models",
                                         headers={"Authorization": f"Bearer {self.api_key}"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode("utf-8"))
            ids = [m.get("id") for m in data.get("data", [])]
            return {"ok": True, "count": len(ids),
                    "target_present": self.model in ids,
                    "nemotron": [i for i in ids if "nemotron" in (i or "").lower()][:8]}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": str(exc)[:200]}
