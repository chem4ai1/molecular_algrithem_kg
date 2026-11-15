"""沙箱执行：以子进程隔离方式运行被测算法模块.

隔离手段
--------
1. 独立进程 + 超时强杀（防止死循环 / 阻塞）；
2. 环境变量白名单（不向被测代码暴露任何 API Key）；
3. 工作目录限定在本次运行的 artifact 目录；
4. 执行前做 AST 静态安全检查（见 ``contract.static_check``）。

说明：本地无 Docker 时，这是「足够好」的隔离；生产环境建议替换为
xKG 仓库中的 ``xkg-coderunner`` Docker 镜像（接口保持一致即可）。
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import REPO_ROOT
from ..utils import ensure_dir

logger = logging.getLogger(__name__)


@dataclass
class ExecResult:
    """一次沙箱执行的结果。"""

    ok: bool = False
    returncode: int = -1
    stdout: str = ""
    stderr: str = ""
    duration: float = 0.0
    payload: Dict[str, Any] = field(default_factory=dict)
    timed_out: bool = False
    command: List[str] = field(default_factory=list)

    @property
    def error_text(self) -> str:
        if self.payload.get("traceback"):
            return f"[stage={self.payload.get('stage')}] {self.payload.get('error')}\n{self.payload['traceback']}"
        if self.timed_out:
            return f"执行超时（{self.duration:.0f}s）"
        return (self.stderr or self.stdout or "未知错误")[-3000:]


def run_module(module_path: Path, dataset_path: Path, out_path: Path, *,
               work_dir: Path, seed: int = 42, subsample: float = 1.0,
               timeout: int = 300) -> ExecResult:
    """在子进程中执行评测器，返回结构化结果。"""
    module_path, dataset_path, out_path = Path(module_path), Path(dataset_path), Path(out_path)
    work_dir = ensure_dir(Path(work_dir))
    ensure_dir(out_path.parent)

    env = {
        "PYTHONPATH": str(REPO_ROOT),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONHASHSEED": "0",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "MPLBACKEND": "Agg",
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "TEMP": os.environ.get("TEMP", ""),
        "TMP": os.environ.get("TMP", ""),
        "USERPROFILE": os.environ.get("USERPROFILE", ""),
        "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", ""),
        "HOME": os.environ.get("HOME", ""),
    }
    cmd = [
        sys.executable, "-m", "capfactory.replicate.runner",
        "--module", str(module_path),
        "--dataset", str(dataset_path),
        "--out", str(out_path),
        "--seed", str(seed),
        "--subsample", str(subsample),
    ]
    start = time.time()
    timed_out = False
    try:
        proc = subprocess.run(cmd, cwd=str(work_dir), env=env, capture_output=True,
                              text=True, timeout=timeout, encoding="utf-8", errors="replace")
        stdout, stderr, rc = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        rc = -9
    duration = time.time() - start

    payload: Dict[str, Any] = {}
    if out_path.exists():
        try:
            payload = json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
    res = ExecResult(
        ok=bool(payload.get("ok")) and not timed_out,
        returncode=rc, stdout=stdout[-6000:], stderr=stderr[-6000:], duration=duration,
        payload=payload, timed_out=timed_out, command=cmd,
    )
    logger.info("沙箱执行结束：ok=%s rc=%s 用时=%.1fs", res.ok, rc, duration)
    return res
