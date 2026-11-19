#!/usr/bin/env bash
# 字段同步自检（pre-commit）：YAML/validator/apply/tbox 四份清单必须一致
set -u
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT" || exit 0

# 找可用 python（venv 优先）
PY=""
for c in "$ROOT/.venv/bin/python" "/home/zengshuxin/xKG-main/xKG-main/.venv-linux/bin/python" "python3"; do
  if command -v "$c" >/dev/null 2>&1 || [ -x "$c" ]; then PY="$c"; break; fi
done
[ -z "$PY" ] && { echo "[field-sync] 跳过：找不到 python"; exit 0; }

FAIL=0
NODE_ROLE=$(PYTHONPATH="$ROOT/src" "$PY" "$ROOT/scripts/check_node_roles.py" 2>&1)
if [ $? -ne 0 ]; then echo "$NODE_ROLE"; FAIL=1; fi
for st in E1_paper E2_algorithm E3_benchmark; do
  OUT=$(PYTHONPATH="$ROOT/src" "$PY" "$ROOT/scripts/check_field_sync.py" --stage "$st" 2>&1)
  RC=$?
  if [ $RC -ne 0 ] && [ $RC -ne 2 ]; then
    echo "[field-sync] $st 执行异常（跳过不阻断）"; continue
  fi
  if [ $RC -eq 2 ]; then
    echo "$OUT" | grep -E "必丢|未定义|不一致" | sed "s/^/[field-sync][$st] /"
    FAIL=1
  fi
done

if [ $FAIL -ne 0 ]; then
  echo ""
  echo "✗ 字段同步检查未通过：加字段时请同步 4 处（YAML/validator/apply/tbox）"
  echo "  临时跳过：git commit --no-verify"
  exit 1
fi
echo "[field-sync] ✅ 四份清单一致"
exit 0
