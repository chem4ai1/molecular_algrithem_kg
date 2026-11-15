#!/usr/bin/env bash
# 启动前端（默认 8091）
set -e
cd "$(dirname "$0")/.."
exec python stages/5_frontend/serve.py "${1:-8091}"
