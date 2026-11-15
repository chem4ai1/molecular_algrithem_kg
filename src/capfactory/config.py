"""CapFactory 全局配置.

配置优先级（高 → 低）::

    构造参数 > 环境变量 > config.yaml > 内置默认值

所有路径均解析为绝对路径，避免不同工作目录下行为不一致。
"""

from __future__ import annotations

import copy
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent

DEFAULT_CONFIG: Dict[str, Any] = {
    "llm": {
        # 兼容 OpenAI 协议的任意网关；默认使用 OpenRouter
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "model": "nvidia/nemotron-3.5-super-vl:free",
        "paper_model": "nvidia/nemotron-3.5-super-vl:free",
        "code_model": "nvidia/nemotron-3.5-super-vl:free",
        "temperature": 0.2,
        "max_tokens": 6000,
        "max_retries": 4,
        "timeout": 180,
        "max_concurrency": 2,
        "offline": False,
    },
    "paths": {
        "storage": "storage_cf",
        "kg_dir": "storage_cf/kg",
        "raw_dir": "storage_cf/raw",
        "cache_dir": "storage_cf/cache",
        "workspace": "storage_cf/workspace",
        "reports": "storage_cf/reports",
        "logs": "storage_cf/logs",
    },
    "ingest": {
        "arxiv_max_results": 8,
        "arxiv_rate_limit_seconds": 3.0,
        "clone_depth": 1,
        "max_repo_files": 400,
        "max_file_bytes": 200_000,
    },
    "kg": {
        "dedup_similarity": 0.90,
        "embedding_dim": 512,
        "top_k_retrieval": 8,
    },
    "replicate": {
        "max_candidates": 3,
        "max_repair_rounds": 3,
        "exec_timeout_seconds": 300,
        "stability_repeats": 2,
        "min_metric_score": 0.5,
    },
    "domain": {
        # 业务目标：来自佩德生物企业介绍（多肽创新药研发）
        "name": "天然多肽药物研发",
        "needs": [
            "多肽毒性预测",
            "抗菌肽活性预测",
            "多肽结构与靶点结合预测",
            "多肽成药性评估（半衰期/稳定性/免疫原性）",
            "多肽虚拟筛选与生成式设计",
            "多肽理化性质预测",
        ],
        # 中英术语桥接：文献能力多为英文，靠别名做跨语言检索对齐
        "need_aliases": {
            "多肽毒性预测": "peptide toxicity prediction toxin toxic hemolytic cytotoxicity",
            "抗菌肽活性预测": "antimicrobial peptide activity prediction AMP minimum inhibitory concentration",
            "多肽结构与靶点结合预测": "peptide structure prediction binding affinity molecular docking target interaction",
            "多肽成药性评估（半衰期/稳定性/免疫原性）": "druggability ADMET stability half-life proteolysis immunogenicity permeability",
            "多肽虚拟筛选与生成式设计": "virtual screening generative design diffusion model language model de novo peptide",
            "多肽理化性质预测": "physicochemical property prediction charge hydrophobicity isoelectric point solubility",
        },
    },
}

logger = logging.getLogger(__name__)


@dataclass
class Settings:
    """已解析的运行时配置。"""

    data: Dict[str, Any] = field(default_factory=dict)
    config_path: Optional[Path] = None

    # ---- 便捷访问器 -------------------------------------------------
    @property
    def llm(self) -> Dict[str, Any]:
        return self.data["llm"]

    @property
    def ingest(self) -> Dict[str, Any]:
        return self.data["ingest"]

    @property
    def kg(self) -> Dict[str, Any]:
        return self.data["kg"]

    @property
    def replicate(self) -> Dict[str, Any]:
        return self.data["replicate"]

    @property
    def domain(self) -> Dict[str, Any]:
        return self.data["domain"]

    def path(self, key: str) -> Path:
        """返回 paths 段中的绝对路径，并确保目录存在。"""
        raw = self.data["paths"][key]
        p = Path(raw)
        if not p.is_absolute():
            p = REPO_ROOT / p
        p = p.resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    def as_dict(self) -> Dict[str, Any]:
        return copy.deepcopy(self.data)


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """递归合并字典（override 覆盖 base），返回新字典。"""
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _expand_env(value: Any) -> Any:
    """递归展开 ``${VAR}`` 形式的环境变量引用。"""
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return os.getenv(value[2:-1], "")
    return value


def _load_dotenv() -> None:
    """轻量 .env 加载器（不依赖 python-dotenv）。"""
    for candidate in (REPO_ROOT / ".env", PACKAGE_ROOT / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)


_SETTINGS: Optional[Settings] = None


def get_settings(config_path: Optional[str] = None, reload: bool = False) -> Settings:
    """加载（并缓存）全局配置。"""
    global _SETTINGS
    if _SETTINGS is not None and not reload and config_path is None:
        return _SETTINGS

    _load_dotenv()
    path = Path(config_path) if config_path else (PACKAGE_ROOT / "config.yaml")
    user_cfg: Dict[str, Any] = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}

    merged = _expand_env(_deep_merge(DEFAULT_CONFIG, user_cfg))

    # 环境变量覆盖（便于 CI / 临时切换模型）
    if os.getenv("CAPFACTORY_MODEL"):
        merged["llm"]["model"] = os.environ["CAPFACTORY_MODEL"]
    if os.getenv("CAPFACTORY_BASE_URL"):
        merged["llm"]["base_url"] = os.environ["CAPFACTORY_BASE_URL"]
    if os.getenv("CAPFACTORY_OFFLINE", "").lower() in {"1", "true", "yes"}:
        merged["llm"]["offline"] = True

    _SETTINGS = Settings(data=merged, config_path=path if path.exists() else None)
    return _SETTINGS


def reset_settings() -> None:
    """清空配置缓存（测试用）。"""
    global _SETTINGS
    _SETTINGS = None


def api_key(settings: Optional[Settings] = None) -> str:
    """读取 LLM API Key。"""
    s = settings or get_settings()
    env_name = s.llm.get("api_key_env", "OPENROUTER_API_KEY")
    key = os.getenv(env_name) or os.getenv("OPENAI_API_KEY") or ""
    return key.strip()
