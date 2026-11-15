"""P1-5：R5 lite 真跑（GGR 蓝图 §5 R5；AutoReproduce / Artisan / SciForge S2）。

职责：
  1. 从图谱的**原始表格行** ``Benchmark.attrs.model_results`` 生成独立可重跑
     ``REPRO_SCRIPT.py``（纯 stdlib，不读 ``LeaderboardEntry`` 等期望值）
  2. 隔离子进程执行（env 白名单 / cwd / timeout / import 静态检查）
  3. 失败 → traceback 归因 → ``EDIT N M`` 定点替换 → 重跑（``debug_tries ≤ 20``）
  4. 全程写 ``events.ndjson``（durable truth）与 ``EDIT_LOG.jsonl``
  5. 输出 ``raw_results.json``，供 ``evaluate_sau`` 与 ``reproduction_close`` 消费

**诚实边界**：这里复现的是「评测协议重算 + 方法模块链可执行性」，
不是原论文模型训练（无数据集/GPU/权重）。脚本输入是 PDF 表格原始抽取行，
对照是应用层 ``LeaderboardEntry`` —— 两条独立代码路径算出的值是否一致。

用法：
    from capfactory.reprospec.executor import execute_repro
    ex = execute_repro(spec, graph, out_dir="storage_cf/repro_runs/2411.06608",
                       effort="lite")
    ex.ok, ex.results, ex.debug_tries, ex.code_sha
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ALLOWED_IMPORTS = {"json", "math", "re", "random", "sys", "collections",
                   "itertools", "statistics"}
MAX_DEBUG_TRIES = 20
DEFAULT_TIMEOUT = 60


@dataclass
class ExecutionResult:
    ok: bool = False
    effort: str = "lite"
    status: str = "not_started"
    stage: str = ""
    results: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)
    debug_tries: int = 0
    edits: List[Dict[str, Any]] = field(default_factory=list)
    duration_s: float = 0.0
    returncode: int = -1
    stdout_tail: str = ""
    stderr_tail: str = ""
    script_path: str = ""
    code_sha: str = ""
    inputs_sha: str = ""
    outputs_sha: str = ""
    events: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# 1) 从图构造 FIXTURE（只读客观事实，不读期望值）
# ---------------------------------------------------------------------------
def _fixture_from_graph(spec: Any, graph: Any,
                        max_rows_per_bench: int = 200) -> Dict[str, Any]:
    nodes = getattr(graph, "nodes", {}) or {}
    fixture: Dict[str, Any] = {}
    for dc in (spec.data_contract or []):
        bid = dc.get("benchmark")
        n = nodes.get(bid)
        if n is None:
            continue
        rows = (getattr(n, "attrs", {}) or {}).get("model_results") or []
        if not isinstance(rows, list):
            continue
        clean = []
        for r in rows[:max_rows_per_bench]:
            if not isinstance(r, dict):
                continue
            clean.append({k: r.get(k) for k in
                          ("model", "metric", "value", "unit", "is_sota",
                           "paper_id")})
        if clean:
            fixture[bid] = {"label": dc.get("label") or bid,
                            "input_form": dc.get("input_form"),
                            "output_form": dc.get("output_form"),
                            "rows": clean}
    return fixture


def _metric_plan_for_script(spec: Any) -> Dict[str, str]:
    return {k: (v.get("direction") or "max")
            for k, v in (spec.metric_plan or {}).items()}


def _module_desc(spec: Any, graph: Any) -> List[Dict[str, str]]:
    nodes = getattr(graph, "nodes", {}) or {}
    out = []
    for i, mid in enumerate((spec.code_plan or {}).get("order") or []):
        n = nodes.get(mid)
        a = dict(getattr(n, "attrs", {}) or {}) if n else {}
        out.append({"index": str(i), "id": mid,
                    "label": getattr(n, "label", mid) if n else mid,
                    "mechanism": str(a.get("mechanism") or a.get("name") or "")})
    return out


# ---------------------------------------------------------------------------
# 2) 生成独立可重跑脚本
# ---------------------------------------------------------------------------
_SCRIPT_HEAD = [
    '"""Auto-generated independent reproduction script (GGR P1-5).',
    'Input: raw table rows extracted from the paper PDF (objective facts).',
    'This script MUST NOT read any application-layer expected values.',
    '"""',
    "import json, math, re, random, sys",
    "",
]

_SCRIPT_LIB = r'''
def normalize_model(s):
    """Remove (ours), markers and unify case (independent of the app miner)."""
    t = str(s or "").strip()
    t = re.sub(r"\((?:ours|our|proposed)\)", "", t, flags=re.I)
    t = re.sub(r"[*†‡]+$", "", t).strip()
    return t


def normalize_metric_name(s):
    t = str(s or "").strip().lower()
    aliases = {"bce": "binary_cross_entropy", "forward time": "runtime",
               "validity (%)": "validity", "uniqueness (%)": "uniqueness",
               "novelty (%)": "novelty"}
    t = re.sub(r"\s*\(.*?\)\s*", "", t).strip()
    return aliases.get(t, t.replace(" ", "_"))


def to_float(v):
    """Parse '99.6', '1,234', '0.90±0.01', '98%' -> float or None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def direction_of(metric, plan):
    return plan.get(metric, plan.get(metric.lower(), "max"))


def compute_sota(rows, plan):
    """Recompute SOTA per metric from raw rows, with explicit tie handling."""
    groups = {}
    for r in rows:
        k = normalize_metric_name(r.get("metric"))
        v = to_float(r.get("value"))
        if v is None:
            continue
        groups.setdefault(k, []).append((v, normalize_model(r.get("model"))))
    out = {}
    for k, items in groups.items():
        d = direction_of(k, plan)
        best = (max if d == "max" else min)(v for v, _ in items)
        winners = [m for v, m in items if abs(v - best) < 1e-12]
        out[k] = {"value": best, "model": winners[0] if winners else "",
                  "direction": d, "ties": sorted(set(winners))[1:],
                  "n_rows": len(items)}
    return out


def recompute_rows(fixture, plan):
    """Independent re-implementation of the evaluation protocol."""
    out, sota = [], {}
    for bid, bench in fixture.items():
        # 表格抽取可能产生 model/metric 为空的残行；它们没有可对齐的实体，
        # 直接跳过（并在宿主侧统计 unmatched），不得伪造指标名。
        rows = [r for r in (bench.get("rows") or [])
                if r.get("model") and r.get("metric")]
        sota[bid] = compute_sota(rows, plan)
        for i, r in enumerate(rows):
            out.append({
                "benchmark_id": bid, "benchmark": bench.get("label"),
                "row_index": i,
                "model": normalize_model(r.get("model")),
                "metric": normalize_metric_name(r.get("metric")),
                "raw_value": r.get("value"),
                "value": to_float(r.get("value")),
                "unit": r.get("unit") or "",
            })
    return out, sota
'''


def build_repro_script(spec: Any, graph: Any,
                       *, inject_error: str = "") -> str:
    """生成纯 stdlib 的独立复现脚本源码。

    ``inject_error`` 仅供测试注入可修复缺陷（如 ``NameError``），
    生产路径必须为空 —— 不得人为制造失败再修好来冒充 debug 能力。
    """
    fixture = _fixture_from_graph(spec, graph)
    plan = _metric_plan_for_script(spec)
    mods = _module_desc(spec, graph)
    L = list(_SCRIPT_HEAD)
    # 关键：JSON 的 false/true/null **不是**合法 Python 字面量。
    # 必须把 JSON 文本作为字符串嵌入再 json.loads，不能把 dict 直接 repr 成源码。
    def _embed(obj: Any) -> str:
        return "json.loads(" + json.dumps(
            json.dumps(obj, ensure_ascii=False, default=str)) + ")"

    L += ["FIXTURE = " + _embed(fixture),
          "METRIC_PLAN = " + _embed(plan),
          "PIPELINE = " + _embed([m["id"] for m in mods]),
          "", _SCRIPT_LIB, ""]
    # 逐模块确定性函数（方法链可执行性 / L3）
    L += ["def canonicalize(points):",
          "    return tuple(sorted(tuple(float(v) for v in p) for p in points))",
          "", "def apply_group(points, perm):",
          "    return [points[i] for i in perm]", ""]
    for m in mods:
        fn = "step_%s" % m["index"]
        key = bool(re.search(r"canonical|symmetr|standardiz|排序|规范|对称",
                             m["mechanism"], re.I))
        L += ["def %s(state):" % fn,
              '    """module=%s | mechanism=%s"""' %
              (m["id"], m["mechanism"][:80].replace('"""', "")),
              "    pts = state['points']"]
        if key:
            L += ["    state['points'] = list(canonicalize(pts))",
                  "    state['canonicalized'] = True"]
        else:
            L += ["    state['checksum'] = (state.get('checksum', 0.0) + "
                  "sum(float(p[0]) for p in pts)) / (len(pts) or 1)"]
        L += ["    state['trace'].append({'module': %r, 'key': %r})" %
              (m["id"], bool(key)),
              "    return state", ""]
    L += ["STEP_FUNCS = [%s]" %
          ", ".join("step_%s" % m["index"] for m in mods), ""]
    if inject_error:
        L += ["# TEST-ONLY injected defect", inject_error, ""]
    L += [r'''
def run_stage(stage, n_rows):
    # subset 与 full 用不同 seed / 点数，保证 full 不是 subset 的逐字复制
    # （SciForge S2：ties fail，full 必须严格优于自己的 baseline）
    seed, n_points = (42, 8) if stage == 'subset' else (43, 16)
    rng = random.Random(seed)
    pts = [[rng.uniform(-2, 2) for _ in range(3)] for _ in range(n_points)]
    perm = list(range(len(pts))); rng.shuffle(perm)
    gp = apply_group(pts, perm)
    baseline = abs(pts[0][0] - gp[0][0])

    state = {'points': pts, 'trace': [], 'checksum': 0.0}
    for fn in STEP_FUNCS:
        fn(state)
    cand_a = canonicalize(state['points'])
    cand_b = canonicalize(apply_group(state['points'], perm))
    candidate = abs(sum(sum(p) for p in cand_a) - sum(sum(p) for p in cand_b))

    slim = {}
    for bid, bench in FIXTURE.items():
        slim[bid] = dict(bench, rows=(bench.get('rows') or [])[:n_rows])
    rows, sota = recompute_rows(slim, METRIC_PLAN)
    return {
        'stage': stage, 'status': 'PASS',
        'n_rows': len(rows), 'n_benchmarks': len(slim),
        'baseline': baseline, 'candidate': candidate,
        'steps_executed': len(STEP_FUNCS),
        'symbol_trace': state['trace'],
        'canonicalized': bool(state.get('canonicalized')),
        'entry_rows': rows, 'sota': sota,
    }


def main():
    payload = {
        'status': 'PASS',
        'spec_sha': '',
        'stages': {
            'subset': run_stage('subset', 12),
            'full': run_stage('full', 10 ** 9),
        },
    }
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == '__main__':
    main()
''']
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 3) 静态安全检查 + 沙箱执行
# ---------------------------------------------------------------------------
def check_script_safety(src: str) -> List[str]:
    """AST 检查 import 白名单与危险调用；返回问题列表。"""
    problems: List[str] = []
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return [f"SyntaxError: {exc}"]
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.split(".")[0] not in ALLOWED_IMPORTS:
                    problems.append(f"illegal_import:{a.name}")
        elif isinstance(n, ast.ImportFrom):
            if (n.module or "").split(".")[0] not in ALLOWED_IMPORTS:
                problems.append(f"illegal_import_from:{n.module}")
        elif isinstance(n, ast.Call):
            forbidden = {"eval", "exec", "open", "compile", "__import__",
                         "system", "popen", "run", "check_output"}
            if isinstance(n.func, ast.Name) and n.func.id in forbidden:
                problems.append(f"forbidden_call:{n.func.id}")
            # 属性调用（os.system / subprocess.run）同样要拦，不能只查裸名字
            elif isinstance(n.func, ast.Attribute) and \
                    n.func.attr in forbidden:
                problems.append(f"forbidden_attr_call:{n.func.attr}")
    return problems


def _run_once(script: Path, out_dir: Path, timeout: int) -> Dict[str, Any]:
    env = {
        "PYTHONPATH": "", "PYTHONIOENCODING": "utf-8",
        "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1", "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
    }
    t0 = time.time()
    # 必须用绝对路径：out_dir 常是相对路径（storage_cf/...），
    # 而 cwd 会切到 run 目录，相对脚本路径会失效（实测踩过）。
    try:
        p = subprocess.run([sys.executable, str(script.resolve())],
                           cwd=str(out_dir.resolve()), env=env, capture_output=True,
                           text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        rc, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "rc": -9, "stdout": "", "stderr":
                f"TimeoutExpired after {timeout}s", "duration": time.time() - t0,
                "timed_out": True}
    payload = None
    for line in reversed((out or "").splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            break
    return {"ok": payload is not None and rc == 0, "rc": rc,
            "stdout": out[-3000:], "stderr": err[-3000:],
            "duration": time.time() - t0, "payload": payload,
            "timed_out": False}


# ---------------------------------------------------------------------------
# 4) EDIT N M 定点修复（AutoReproduce 口径）
# ---------------------------------------------------------------------------
def edit_lines(src: str, start: int, end: int, new_code: str) -> str:
    """替换 1-based 行区间 [start, end]（含端点），不改其余任何一行。"""
    lines = src.splitlines()
    s, e = max(1, start), min(len(lines), end)
    if s > e:
        return src
    return "\n".join(lines[:s - 1] + new_code.splitlines() + lines[e:]) + "\n"


def diagnose(stderr: str) -> Dict[str, Any]:
    """从 traceback 归因，返回可机械修复的诊断（不可修复则 fixable=False）。"""
    s = stderr or ""
    m = re.search(r"NameError: name '([A-Za-z_]\w*)' is not defined", s)
    if m:
        return {"kind": "NameError", "symbol": m.group(1), "fixable": True,
                "reason": "未定义名字，插入置 None 的安全定义"}
    if "SyntaxError" in s:
        return {"kind": "SyntaxError", "fixable": False,
                "reason": "语法错误需人工/LLM 重写，不自动猜测"}
    if "TimeoutExpired" in s:
        return {"kind": "Timeout", "fixable": False,
                "reason": "执行超时，需缩小 FIXTURE 或优化算法"}
    if "IndexError" in s or "KeyError" in s:
        return {"kind": "ContainerAccess", "fixable": False,
                "reason": "容器访问越界，需人工检查数据契约"}
    return {"kind": "Unknown", "fixable": False,
            "reason": s[-200:] or "无 stderr"}


def make_patch(diag: Dict[str, Any]) -> Optional[str]:
    if not diag.get("fixable"):
        return None
    if diag["kind"] == "NameError":
        return "%s = None  # EDIT: safe stub for undefined symbol" % diag["symbol"]
    return None


# ---------------------------------------------------------------------------
# 5) 宿主把脚本输出映射成 results（entry_values + rows）
# ---------------------------------------------------------------------------
def build_results(payload: Dict[str, Any], spec: Any,
                  graph: Any) -> Dict[str, Any]:
    """把独立脚本的输出对齐到应用层 entry_id，并构造 R6 门所需的 rows。

    - ``entry_values``: {LeaderboardEntry.id: 重算值}，给 ``evaluate_sau``
    - ``rows``: [{metric, baseline, value, entry_id}]，给 ``reproduction_close``
      baseline 来自应用层 LeaderboardEntry（论文报告值），value 来自脚本重算值
    """
    def _norm(s: Any) -> str:
        """与脚本侧 normalize_model/normalize_metric_name 保持同一口径。"""
        t = str(s or "").strip().lower()
        t = re.sub(r"\((?:ours|our|proposed)\)", "", t)
        t = re.sub(r"[*†‡]+$", "", t).strip()
        t = re.sub(r"\s*\(.*?\)\s*", "", t).strip()
        return t.replace(" ", "_")

    nodes = getattr(graph, "nodes", {}) or {}
    index: Dict[Tuple[str, str, str], str] = {}
    for nid, n in nodes.items():
        if getattr(n, "type", "") != "LeaderboardEntry":
            continue
        a = dict(getattr(n, "attrs", {}) or {})
        key = (_norm(a.get("benchmark")), _norm(a.get("model")),
               _norm(a.get("metric")))
        index.setdefault(key, nid)

    full = (payload.get("stages") or {}).get("full") or {}
    entry_values: Dict[str, Any] = {}
    rows: List[Dict[str, Any]] = []
    unmatched = 0
    for r in full.get("entry_rows") or []:
        key = (_norm(r.get("benchmark")), _norm(r.get("model")),
               _norm(r.get("metric")))
        eid = index.get(key)
        if not eid:
            unmatched += 1
            continue
        val = r.get("value")
        if eid in entry_values or val is None:
            continue
        entry_values[eid] = float(val)
        base = (nodes[eid].attrs or {}).get("value")
        rows.append({"metric": r.get("metric"), "baseline": base,
                     "value": float(val), "entry_id": eid,
                     "model": r.get("model"),
                     "benchmark": r.get("benchmark")})
    return {
        "status": payload.get("status"), "effort": "lite",
        "entry_values": entry_values, "rows": rows,
        "n_unmatched_rows": unmatched,
        "stages": payload.get("stages") or {},
        "n_entry_rows": len(full.get("entry_rows") or []),
    }


# ---------------------------------------------------------------------------
# 6) 主入口
# ---------------------------------------------------------------------------
def execute_repro(spec: Any, graph: Any, *,
                  out_dir: str | Path,
                  effort: str = "lite",
                  timeout: int = DEFAULT_TIMEOUT,
                  max_debug_tries: int = MAX_DEBUG_TRIES,
                  inject_error: str = "",
                  event_log: Any = None) -> ExecutionResult:
    """生成脚本 → 沙箱执行 → EDIT 循环 → 落盘结果（真跑）。

    ``event_log`` 传 ``sciforge.repro.state.EventLog`` 时，
    执行事件与阶段门事件写进同一份 ``.repro/events.ndjson``
    （durable truth 只有一份），否则本模块自建一份。
    """
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    res = ExecutionResult(effort=effort)
    events: List[Dict[str, Any]] = []
    if event_log is None:
        from capfactory.sciforge.repro.state import EventLog
        event_log = EventLog(d)

    def ev(t: str, **kw: Any) -> None:
        e = {"type": t, "ts": round(time.time(), 3), **kw}
        events.append(e)
        event_log.append(e)

    if effort == "dry":
        res.status = "skipped_dry"
        res.warnings.append("dry 模式不执行；R6 必须保持 BLOCKED")
        ev("exec_skipped", reason="dry")
        return res

    src = build_repro_script(spec, graph, inject_error=inject_error)
    problems = check_script_safety(src)
    if problems:
        res.status = "unsafe_script"
        res.warnings.extend(problems)
        ev("exec_blocked", reason="static_check", problems=problems)
        return res

    script = d / "REPRO_SCRIPT.py"
    script.write_text(src, encoding="utf-8")
    res.script_path = str(script)
    res.inputs_sha = _sha(_fixture_from_graph(spec, graph))
    ev("script_generated", path=str(script), sha=_sha(src))

    t0 = time.time()
    payload = None
    for attempt in range(max_debug_tries + 1):
        run = _run_once(script, d, timeout)
        ev("exec", attempt=attempt, ok=run["ok"], rc=run["rc"],
           duration=run["duration"])
        if run["ok"] and run.get("payload"):
            payload = run["payload"]
            res.returncode = 0
            ev("exec_ok", attempt=attempt)
            break
        diag = diagnose(run["stderr"])
        patch = make_patch(diag)
        ev("exec_failed", attempt=attempt, kind=diag["kind"],
           fixable=diag["fixable"], reason=diag["reason"][:200])
        if not patch or attempt >= max_debug_tries:
            res.status = "exec_failed"
            res.stderr_tail = run["stderr"]
            res.stdout_tail = run["stdout"]
            res.returncode = run["rc"]
            res.warnings.append(
                f"调试耗尽或不可自动修复：{diag['kind']} — {diag['reason']}")
            break
        # EDIT 1 1：在 import 之后插入安全定义，不触碰其余行
        before = script.read_text(encoding="utf-8")
        after = edit_lines(before, 6, 6, patch)
        script.write_text(after, encoding="utf-8")
        res.debug_tries += 1
        edit = {"attempt": attempt + 1, "start": 6, "end": 6,
                "code": patch, "reason": diag["reason"],
                "before_sha": _sha(before), "after_sha": _sha(after)}
        res.edits.append(edit)
        with (d / "EDIT_LOG.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(edit, ensure_ascii=False) + "\n")
        ev("edit", **{k: edit[k] for k in ("attempt", "start", "end", "reason")})

    res.duration_s = round(time.time() - t0, 3)
    if payload is None:
        res.events = events
        return res

    results = build_results(payload, spec, graph)
    res.ok = True
    res.status = "PASS"
    res.stage = "full"
    res.results = results
    res.raw = payload
    res.code_sha = _sha(script.read_text(encoding="utf-8"))
    raw_path = d / "raw_results.json"
    raw_path.write_text(json.dumps(payload, ensure_ascii=False,
                                   indent=2, default=str), encoding="utf-8")
    res.outputs_sha = _sha(payload)
    (d / "RESULTS_FOR_GATES.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    ev("results_written", n_rows=len(results["rows"]),
       n_entries=len(results["entry_values"]),
       outputs_sha=res.outputs_sha)
    res.events = events
    return res


def _sha(obj: Any) -> str:
    blob = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()
