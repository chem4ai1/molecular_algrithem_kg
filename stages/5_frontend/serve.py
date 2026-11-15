#!/usr/bin/env python3
import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
os.chdir(ROOT)

"""启动 FastAPI 服务（三库 / 关系浏览器 / 溯源 / 任务层 / 复现页）。"""
from capfactory.cli import main as cli

if __name__ == "__main__":
    import sys
    sys.argv = [sys.argv[0], "serve", "--host", "0.0.0.0", "--port",
                (sys.argv[1] if len(sys.argv) > 1 else "8091")]
    cli()
