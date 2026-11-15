"""统一 LLM 路由：本地 Qwen3.8-27B 动态预算 → 加预算重试一次 → polo 兜底。

用户要求：
1. 尽可能贴近模型上限：用 vLLM ``/tokenize`` **精确**算 prompt token，
   输出预算 = min(阶段上限, 65536 - prompt_tokens - 安全余量)；
2. 输出预算按阶段动态，失败时**加一次**预算（×1.8）重试；
3. 加一次仍失败才切换到 polo API（gemini-3.8-flash）；
4. 全链路记录 backend / 预算 / 延迟 / 输出长度 / 校验问题，可复盘。
"""
from __future__ import annotations
import json, time, urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

VLLM_BASE = "http://127.0.0.1:8000"
VLLM_MODEL = "Qwen3.8-27B"
MAX_MODEL_LEN = 65536
SAFETY_MARGIN = 1024          # 给特殊 token / 模板留余量
MIN_OUTPUT = 600

# 阶段硬上限（贴近模型能力，但由 /tokenize 动态收敛）
STAGE_CAPS: Dict[str, int] = {
    "heading_screen": 2000,
    "related_work": 6000,
    "method": 6000,
    "benchmark_profile": 5000,
    "benchmark_values": 5000,
    "paper": 3000,
    "algorithm": 5000,
    "benchmark": 5000,
}


def count_tokens(prompt: str, *, timeout: int = 8) -> Optional[int]:
    """vLLM 原生 /tokenize；失败返回 None 走字符估算。"""
    try:
        body = json.dumps({"model": VLLM_MODEL, "prompt": prompt}).encode()
        req = urllib.request.Request(f"{VLLM_BASE}/tokenize", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return int(json.loads(r.read().decode())["count"])
    except Exception:  # noqa: BLE001
        return None


def estimate_tokens(prompt: str) -> int:
    """兜底估算：英文约 3.6 字符/token，中文约 1.6 字/token，取保守值。"""
    return int(len(prompt) / 2.6) + 64


def output_budget(prompt: str, *, stage: str, boost: float = 1.0,
                  requested: int = 0) -> Dict[str, Any]:
    """精确计算本次可用输出 token 数。"""
    exact = count_tokens(prompt)
    ptok = exact if exact is not None else estimate_tokens(prompt)
    room = max(MIN_OUTPUT, MAX_MODEL_LEN - ptok - SAFETY_MARGIN)
    cap = STAGE_CAPS.get(stage, 5000)
    want = int((requested or cap) * boost)
    value = max(MIN_OUTPUT, min(want, room, int(MAX_MODEL_LEN * 0.45)))
    return {"prompt_tokens": ptok, "exact": exact is not None,
            "room": room, "stage_cap": cap, "boost": boost,
            "max_tokens": value}


@dataclass
class CallResult:
    backend: str
    attempt: int
    max_tokens: int
    prompt_tokens: int
    latency_s: float
    out: str = ""
    out_chars: int = 0
    error: str = ""
    issues: List[str] = field(default_factory=list)
    truncated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {"backend": self.backend, "attempt": self.attempt,
                "max_tokens": self.max_tokens,
                "prompt_tokens": self.prompt_tokens,
                "latency_s": round(self.latency_s, 2),
                "out_chars": self.out_chars, "error": self.error,
                "issues": self.issues[:8],
                "truncated": self.truncated, "head": self.out[:150]}


class LLMRouter:
    """本地优先 + 加预算一次 + polo 兜底。"""

    def __init__(self, *, local_fn: Optional[Callable[..., str]] = None,
                 polo_fn: Optional[Callable[..., str]] = None,
                 use_polo_fallback: bool = True,
                 timeout: int = 300) -> None:
        if local_fn is None:
            from ..llm.backends import chat as _chat
            local_fn = lambda p, **kw: _chat(p, backend="vllm", **kw)  # noqa: E731
        if polo_fn is None:
            from .polo import PoloClient
            _c = PoloClient(timeout=timeout)
            polo_fn = lambda p, **kw: _c.chat(p, task="multistage_fallback",  # noqa: E731
                                              max_tokens=kw.get("max_tokens", 6000))
        self.local_fn = local_fn
        self.polo_fn = polo_fn
        self.use_polo_fallback = use_polo_fallback
        self.timeout = timeout

    def _call(self, backend: str, prompt: str, max_tokens: int) -> str:
        fn = self.local_fn if backend == "local_qwen" else self.polo_fn
        return fn(prompt, max_tokens=max_tokens, timeout=self.timeout)

    def run(self, prompt: str, *, stage: str,
            validate: Callable[[str], List[str]],
            requested: int = 0,
            base_backend: str = "local_qwen") -> Dict[str, Any]:
        """校验驱动的三级升级：本地 → 本地加预算 → polo。"""
        attempts: List[CallResult] = []
        plan = [("local_qwen", 1.0), ("local_qwen", 1.8)]
        if self.use_polo_fallback:
            plan.append(("polo_gemini", 2.2))
        if base_backend != "local_qwen":
            plan = [(base_backend, 1.0), (base_backend, 1.8)]
        last_out = ""
        for i, (backend, boost) in enumerate(plan, 1):
            b = output_budget(prompt, stage=stage, boost=boost,
                              requested=requested)
            t0 = time.time()
            rec = CallResult(backend=backend, attempt=i,
                             max_tokens=b["max_tokens"],
                             prompt_tokens=b["prompt_tokens"],
                             latency_s=time.time() - t0)
            try:
                rec.out = self._call(backend, prompt, b["max_tokens"]) or ""
                rec.out_chars = len(rec.out)
                stripped = rec.out.rstrip()
                rec.truncated = bool(stripped) and not stripped.endswith(
                    ("}", "]", "```"))
                rec.issues = validate(rec.out)
                last_out = rec.out
            except Exception as exc:  # noqa: BLE001
                rec.error = f"{type(exc).__name__}:{str(exc)[:150]}"
                rec.issues = ["call_failed"]
            rec.latency_s = time.time() - t0
            attempts.append(rec)
            if not rec.issues and not rec.error:
                return {"ok": True, "out": rec.out, "attempts": attempts,
                        "backend": backend, "n_attempts": i,
                        "final_budget": b}
        return {"ok": False, "out": last_out, "attempts": attempts,
                "backend": plan[-1][0], "n_attempts": len(attempts),
                "final_budget": output_budget(prompt, stage=stage,
                                              requested=requested)}
