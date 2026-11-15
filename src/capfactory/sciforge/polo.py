"""Polo API 客户端 + 逐次消耗统计（纯标准库）。

配置来自 ``/home/zengshuxin/API_KEY/polo``：

```
sk-AFK...                       # 第一行 token
base url：https://poloapi.top   # 中文/英文冒号均可
model:gemini-3.8-flash
```

返回体带 ``usage.prompt_tokens / completion_tokens / total_tokens`` 与
``usage.billing_usage``，这里逐次记录，供「换生成器不换判定」实验做成本对照。
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

KEY_FILE = Path("/home/zengshuxin/API_KEY/polo")
DEFAULT_BASE = "https://poloapi.top/v1"
DEFAULT_MODEL = "gemini-3.8-flash"


def load_config(path: str | Path = KEY_FILE) -> Dict[str, str]:
    p = Path(path)
    if not p.exists():
        return {}
    lines = [l.strip() for l in p.read_text(encoding="utf-8",
                                             errors="replace").splitlines() if l.strip()]
    key = next((l for l in lines if re.match(r"^sk-", l)), "")
    base, model = DEFAULT_BASE, DEFAULT_MODEL
    for l in lines:
        m = re.search(r"https?://[^\s,;]+", l)
        if m and "base" in l.lower():
            base = m.group(0).rstrip("/")
            if not base.endswith("/v1"):
                base += "/v1"
        m = re.search(r"model\s*[:：]\s*([\w.\-]+)", l, re.I)
        if m:
            model = m.group(1)
    return {"key": key, "base_url": base, "model": model}


@dataclass
class CallRecord:
    ts: float
    model: str
    task: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_s: float = 0.0
    ok: bool = True
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UsageMeter:
    """跨调用累计消耗；可按任务分组，也可序列化成报告。"""
    records: List[CallRecord] = field(default_factory=list)
    # 可选单价（USD / 1K tokens），仅用于估算；None 时只报 token 数
    price_in: Optional[float] = None
    price_out: Optional[float] = None

    def add(self, r: CallRecord) -> None:
        self.records.append(r)

    def summary(self, *, by_task: bool = True) -> Dict[str, Any]:
        tot_in = sum(r.prompt_tokens for r in self.records)
        tot_out = sum(r.completion_tokens for r in self.records)
        lat = sum(r.latency_s for r in self.records)
        out: Dict[str, Any] = {
            "calls": len(self.records),
            "ok": sum(1 for r in self.records if r.ok),
            "failed": sum(1 for r in self.records if not r.ok),
            "prompt_tokens": tot_in,
            "completion_tokens": tot_out,
            "total_tokens": tot_in + tot_out,
            "latency_s": round(lat, 2),
            "avg_latency_s": round(lat / max(len(self.records), 1), 2),
        }
        if self.price_in is not None and self.price_out is not None:
            out["estimated_cost_usd"] = round(
                tot_in / 1000 * self.price_in + tot_out / 1000 * self.price_out, 6)
            out["price_basis"] = "用户配置单价，非 API 官方报价"
        if by_task:
            g: Dict[str, Dict[str, int]] = {}
            for r in self.records:
                s = g.setdefault(r.task, {"calls": 0, "prompt_tokens": 0,
                                          "completion_tokens": 0, "total_tokens": 0})
                s["calls"] += 1
                s["prompt_tokens"] += r.prompt_tokens
                s["completion_tokens"] += r.completion_tokens
                s["total_tokens"] += r.total_tokens
            out["by_task"] = g
        return out

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"summary": self.summary(),
                                 "records": [r.to_dict() for r in self.records]},
                                ensure_ascii=False, indent=2), encoding="utf-8")
        return p


class PoloClient:
    """OpenAI-compatible chat，带 usage 计量与可选降级。"""

    def __init__(self, *, config: Optional[Dict[str, str]] = None,
                 meter: Optional[UsageMeter] = None,
                 model: str = "", timeout: int = 120) -> None:
        cfg = config or load_config()
        self.key = cfg.get("key", "")
        self.base_url = cfg.get("base_url", DEFAULT_BASE)
        self.model = model or cfg.get("model", DEFAULT_MODEL)
        self.timeout = timeout
        self.meter = meter or UsageMeter()

    @property
    def available(self) -> bool:
        return bool(self.key)

    def chat(self, prompt: str, *, task: str = "generic",
             max_tokens: int = 3000, temperature: float = 0.1,
             retries: int = 1) -> str:
        if not self.available:
            raise RuntimeError("polo key 不可用")
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens, "temperature": temperature,
        }).encode()
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body,
            headers={"Authorization": f"Bearer {self.key}",
                     "Content-Type": "application/json"})
        last_err = ""
        for attempt in range(max(1, retries + 1)):
            t0 = time.time()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    data = json.loads(r.read().decode())
                usage = data.get("usage") or {}
                rec = CallRecord(
                    ts=time.time(), model=self.model, task=task,
                    prompt_tokens=int(usage.get("prompt_tokens") or 0),
                    completion_tokens=int(usage.get("completion_tokens") or 0),
                    total_tokens=int(usage.get("total_tokens") or 0),
                    latency_s=round(time.time() - t0, 2), ok=True)
                self.meter.add(rec)
                return str(data["choices"][0]["message"]["content"] or "")
            except Exception as exc:  # noqa: BLE001
                last_err = f"{type(exc).__name__}: {str(exc)[:120]}"
                self.meter.add(CallRecord(ts=time.time(), model=self.model,
                                          task=task, latency_s=round(time.time()-t0, 2),
                                          ok=False, error=last_err))
        raise RuntimeError(last_err)
