#!/usr/bin/env bash
# S6 一键全量回归：单测 → API 冒烟 → 16 硬门审计 → 12 指标报告。
# set -e：任何一步失败立刻非零退出，绝不吞异常。
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=src

echo "=== [1/4] 全量单元测试 ==="
python3 -m unittest discover -s tests -p "test_*.py" -v

echo "=== [2/4] API 冒烟（TestClient，无需启动服务） ==="
python3 - <<'PY'
from fastapi.testclient import TestClient
from capfactory.web import server
c = TestClient(server.app)
assert not server.app.state.api_registration_errors, server.app.state.api_registration_errors
for p in ("/api/status", "/paperapp", "/api/v10/paperapp/overview",
          "/api/v10/paperapp/choices", "/api/v10/paperapp/signals/audit",
          "/api/v10/paperapp/mining-coverage"):
    r = c.get(p)
    assert r.status_code == 200, (p, r.status_code)
print("API_SMOKE_OK", 6)
PY

echo "=== [3/4] 16 硬门审计 ==="
python3 -m capfactory.paperapp.cli audit-all

echo "=== [4/4] 12 指标报告 ==="
python3 -m capfactory.paperapp.cli report

echo "ALL_GREEN"
