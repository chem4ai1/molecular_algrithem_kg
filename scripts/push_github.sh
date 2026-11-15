#!/usr/bin/env bash
# git push 方式（需要 github.com:443 可达）
# 用法： GITHUB_TOKEN=ghp_xxx bash scripts/push_github.sh
set -e
cd "$(dirname "$0")/.."
TOKEN="${GITHUB_TOKEN:-${1:-}}"
OWNER="${GH_OWNER:-chem4ai1}"
REPO="${GH_REPO:-molecular_algrithem_kg}"
if [ -z "$TOKEN" ]; then
  echo "缺少 token：GITHUB_TOKEN=ghp_xxx bash scripts/push_github.sh"; exit 2
fi
git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/${OWNER}/${REPO}.git"
ASK=$(mktemp)
cat > "$ASK" <<EOF
#!/bin/sh
case "\$1" in
  *Username*) echo "${OWNER}" ;;
  *) echo "${TOKEN}" ;;
esac
EOF
chmod 700 "$ASK"
trap 'rm -f "$ASK"' EXIT
GIT_ASKPASS="$ASK" GIT_TERMINAL_PROMPT=0 git push -u origin main
