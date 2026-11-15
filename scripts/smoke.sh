#!/usr/bin/env bash
# 精简冒烟：起服务后检查关键 API 结构
set -e
cd "$(dirname "$0")/.."
BASE="${1:-http://127.0.0.1:8091}"
python - "$BASE" <<'PY'
import json, sys, urllib.request
base = sys.argv[1]
def get(p):
    with urllib.request.urlopen(base + p, timeout=30) as r:
        return r.status, json.loads(r.read().decode())
checks = []
st, d = get("/api/status");                       checks.append(("status", st == 200 and d.get("ok")))
st, d = get("/api/v6/data/tree?library=paper&facet=domain");   checks.append(("paper tree", st == 200 and bool(d["groups"])))
st, d = get("/api/v6/data/tree?library=algorithm&facet=family"); checks.append(("algorithm tree", st == 200 and bool(d["groups"])))
st, d = get("/api/v6/data/tree?library=dataset&facet=task");   checks.append(("dataset tree", st == 200 and bool(d["groups"])))
st, d = get("/api/v8/relations/instances?view=paper&limit=5"); checks.append(("relations", st == 200 and d["count"] > 0))
st, d = get("/api/v8/provenance/audit");          checks.append(("provenance", st == 200 and "by_type" in d))
st, d = get("/api/v8/task/specs");                checks.append(("task specs", st == 200 and "reproduction" in d["tasks"]))
st, d = get("/api/v8/extraction/batch-status");   checks.append(("batch status", st == 200 and d["total"] > 0))
st, d = get("/api/v9/repro/papers");              checks.append(("repro papers", st == 200 and d["count"] >= 0))
st, d = get("/api/v9/repro/2411.06608/status");   checks.append(("repro status", st == 200 and "stages" in d))
st, d = get("/api/v9/repro/2411.06608/verify");   checks.append(("repro verify", st == 200 and "ok" in d))
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(("[PASS] " if ok else "[FAIL] ") + n)
print(f"{len(checks)-len(bad)}/{len(checks)} 通过")
sys.exit(1 if bad else 0)
PY
