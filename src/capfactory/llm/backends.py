"""统一模型后端入口（收敛 4 套 LLM 客户端）。

现状的 4 套客户端各自维护 model / base_url / timeout / thinking 开关：

* ``llm/client.py::LLMClient``（主流水线，离线优先）
* ``kbpipe/extractor.py::OllamaChat``（抽取）
* ``vector/labeler.py::{VLLM,OpenRouter,Ollama}Backend``（标注）
* ``vision/vl_client.py::OpenRouterVL``（图像）

本模块不重写它们，只提供**唯一的配置与选择入口**，让新代码不再自行拼 URL：

    from capfactory.llm.backends import chat, BACKENDS
    text = chat(prompt, backend="vllm", max_tokens=32768)

失败自动按 ``auto`` 顺序降级；图像任务仍走 ``vision.OpenRouterVL``（payload 不同）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

DEFAULTS: Dict[str, Any] = {
    "ollama": {"model": "qwen3.5:latest", "base_url": "http://127.0.0.1:11434",
               "thinking": False, "timeout": 180, "max_tokens": 2200},
    "vllm": {"model": "Qwen3.8-27B", "base_url": "http://127.0.0.1:8000/v1",
             "thinking": False, "timeout": 900, "max_tokens": 32768},
    "openrouter": {"model": "nvidia/nemotron-3.5-super-vl:free",
                   "base_url": "https://openrouter.ai/api/v1",
                   "thinking": True, "timeout": 300, "max_tokens": 6000},
    "bge": {"model": "bge-m3", "base_url": "http://127.0.0.1:11434"},
}

# auto 顺序：本地 27B 质量优先 → 网络免费模型 → 本地 9.7B 兜底
AUTO_ORDER = ("vllm", "openrouter", "ollama")


@dataclass(frozen=True)
class BackendSpec:
    name: str
    model: str
    base_url: str
    kind: str = "chat"          # chat | embedding | vision
    thinking: bool = False
    timeout: int = 180
    max_tokens: int = 2200

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "model": self.model, "base_url": self.base_url,
                "kind": self.kind, "thinking": self.thinking,
                "timeout": self.timeout, "max_tokens": self.max_tokens}


BACKENDS: Dict[str, BackendSpec] = {
    name: BackendSpec(name=name, **{k: v for k, v in cfg.items()
                                    if k in BackendSpec.__dataclass_fields__})
    for name, cfg in DEFAULTS.items()
}
BACKENDS["bge"] = BackendSpec(name="bge", model="bge-m3",
                              base_url="http://127.0.0.1:11434", kind="embedding")


def spec(name: str) -> BackendSpec:
    if name not in BACKENDS:
        raise ValueError(f"未知后端 {name!r}；可选 {list(BACKENDS)}")
    return BACKENDS[name]


def available(name: str) -> bool:
    """探测后端是否可连接（只用于 auto 选择，不发起推理）。"""
    import json
    import urllib.request
    sp = spec(name)
    if name == "vllm":
        url = f"{sp.base_url}/models"
    elif name == "ollama" or name == "bge":
        url = f"{sp.base_url}/api/tags"
    else:
        return True                      # OpenRouter 需鉴权，交给实际调用判断
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            json.loads(r.read().decode())
        return True
    except Exception:  # noqa: BLE001
        return False


def _fn(name: str) -> Callable[..., str]:
    """取得各后端的 chat 调用（保留原实现，不复制逻辑）。"""
    if name == "vllm":
        from ..vector.labeler import VLLMBackend
        b = VLLMBackend()
        b.available()
        return lambda prompt, **kw: b.chat(prompt, **kw)
    if name == "openrouter":
        from ..vector.labeler import OpenRouterBackend
        b = OpenRouterBackend()
        return lambda prompt, **kw: b.chat(prompt, **kw)
    if name == "ollama":
        from ..kbpipe.extractor import OllamaChat
        sp = spec(name)
        c = OllamaChat(model=sp.model, num_predict=sp.max_tokens)
        return lambda prompt, **kw: c(prompt)
    raise ValueError(f"{name} 不是 chat 后端")


def chat(prompt: str, *, backend: str = "auto", max_tokens: Optional[int] = None,
         timeout: Optional[int] = None, allow_fallback: bool = True) -> str:
    """统一 chat 入口；``auto`` 时按 ``AUTO_ORDER`` 选第一个可用后端。

    返回纯文本；JSON 解析请统一用 ``capfactory.utils.parse_llm_json``。
    """
    order: List[str] = list(AUTO_ORDER) if backend == "auto" else [backend]
    errors: List[str] = []
    for name in order:
        sp = spec(name)
        if backend == "auto" and not available(name):
            continue
        try:
            kw: Dict[str, Any] = {}
            if max_tokens is not None:
                kw["max_tokens"] = max_tokens
            if timeout is not None:
                kw["timeout"] = timeout
            return _fn(name)(prompt, **kw)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {type(exc).__name__} {str(exc)[:100]}")
            if not allow_fallback:
                raise
    raise RuntimeError("全部后端失败：" + " | ".join(errors))
