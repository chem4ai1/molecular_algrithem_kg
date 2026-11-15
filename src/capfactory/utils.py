"""通用工具：日志、文件、哈希、文本处理。"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, List, Optional

_LOG_CONFIGURED = False


def setup_logging(level: str = "INFO", log_file: Optional[Path] = None) -> None:
    """配置根日志器（控制台 + 可选文件）。幂等。"""
    global _LOG_CONFIGURED
    if _LOG_CONFIGURED:
        return
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s", datefmt="%H:%M:%S"
    )
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    # 第三方库降噪
    for noisy in ("httpx", "httpcore", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _LOG_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def now_iso() -> str:
    """UTC 时间戳（ISO8601，秒级）。"""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def short_hash(*parts: Any, length: int = 12) -> str:
    """稳定短哈希，用于 ID / 缓存键。"""
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8"))
    return h.hexdigest()[:length]


def slugify(text: str, max_len: int = 80) -> str:
    """把任意文本转为可用于文件名/ID 的 slug（保留中文）。"""
    text = re.sub(r"[^\w\u4e00-\u9fff\-. ]+", "", text or "")
    text = re.sub(r"\s+", "_", text.strip())
    text = text.strip("._-")
    return (text[:max_len] or "item").replace("/", "_")


def read_json(path: Path, default: Any = None) -> Any:
    """读取 JSON，文件不存在或格式错误时返回 default。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - 防御式
        logging.getLogger(__name__).warning("读取 JSON 失败 %s: %s", path, exc)
        return default


def write_json(path: Path, data: Any, indent: int = 2) -> Path:
    """写入 JSON（自动建目录）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)
    return path


def read_text(path: Path, limit: Optional[int] = None) -> str:
    """安全读取文本。"""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    return text[:limit] if limit else text


def truncate(text: str, max_chars: int, marker: str = "\n...[截断]...\n") -> str:
    """按字符数截断长文本，保留首尾。"""
    if not text or len(text) <= max_chars:
        return text or ""
    head = int(max_chars * 0.7)
    tail = max_chars - head
    return text[:head] + marker + text[-tail:]


# ---------------------------------------------------------------------------
# LLM 输出解析（全仓库唯一实现）
# ---------------------------------------------------------------------------
def parse_llm_json(text: str, *, allow_partial: bool = True) -> Optional[dict]:
    """宽容解析大模型输出的 JSON。

    覆盖四类真实失败：

    * 推理模型用 ````json` 代码块包裹；
    * ``max_tokens`` 截断导致 JSON 未闭合；
    * 前后带解释文字；
    * 完全不是 JSON（返回 ``None``，不把纯文本伪装成对象）。

    返回 dict；失败时 ``None``。截断救回的结果带 ``_partial: True``。
    """
    if not text:
        return None
    raw = re.sub(r"^\s*```(?:json)?|```\s*$", "", text.strip(), flags=re.M).strip()
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    if start < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(raw[start:])
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    if not allow_partial:
        return None
    # 截断：截到最后一个完整的 '}' 再试
    cut = raw.rfind("}")
    if cut > start:
        try:
            obj = json.loads(raw[start:cut + 1])
            if isinstance(obj, dict):
                obj.setdefault("_partial", True)
                return obj
        except json.JSONDecodeError:
            pass
    # 正则兜底：只救回可识别字段，且必须有有效字段才返回
    out: dict = {"_partial": True}
    m = re.search(r'"page_type"\s*:\s*"([^"]+)"', raw)
    if m:
        out["page_type"] = m.group(1)
    m = re.search(r'"summary"\s*:\s*"([^"]{0,300})', raw)
    if m:
        out["summary"] = m.group(1)
    figs = [{"label": x} for x in re.findall(r'"label"\s*:\s*"([^"]{0,40})"', raw)[:5]]
    if figs:
        out["figures"] = figs
    if len(out) == 1:
        return None
    out["raw_text"] = raw[:800]
    return out


def sliding_window(text: str, size: int = 3000, overlap: int = 200) -> List[str]:
    """按字符滑窗切分（与 ``kbpipe.chunker.chunk_text`` 的段落切分不同）。"""
    if not text:
        return []
    out: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        out.append(text[start:end])
        if end == len(text):
            break
        start = max(end - overlap, start + 1)
    return out


def chunk_text(text: str, size: int = 3000, overlap: int = 200) -> List[str]:
    """兼容别名（deprecated）：请改用 ``sliding_window``。"""
    return sliding_window(text, size=size, overlap=overlap)


def ensure_dir(path: Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_relpath(path: Path, root: Path) -> str:
    """相对路径字符串（失败时返回原路径）。"""
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def unique_preserve(items: Iterable[str]) -> List[str]:
    """去重且保持顺序。"""
    seen = set()
    out: List[str] = []
    for it in items:
        if it is None:
            continue
        key = str(it).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def parse_json_block(text: str) -> Any:
    """从 LLM 输出中稳健地提取 JSON 对象/数组。

    依次尝试：整体解析 → 去掉 ``` 围栏 → 扫描首个平衡的 ``{...}`` 或 ``[...]``。
    """
    if text is None:
        return None
    text = text.strip()
    # 1) 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 2) 去代码围栏
    fence = re.search(r"```(?:json|JSON)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        candidate = fence.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            text = candidate
    # 3) 扫描平衡括号
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        while start != -1:
            depth, in_str, esc = 0, False, False
            for i in range(start, len(text)):
                ch = text[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start : i + 1])
                        except json.JSONDecodeError:
                            break
            start = text.find(opener, start + 1)
    return None


def human_bytes(num: Optional[float]) -> str:
    if not num:
        return "0B"
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num) < 1024:
            return f"{num:.1f}{unit}"
        num /= 1024.0
    return f"{num:.1f}TB"


def env_flag(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}
