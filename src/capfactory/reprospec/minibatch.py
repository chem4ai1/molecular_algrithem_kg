"""P3-2：真实 mini-batch shape 实测（替代纯词表推断）。

P1-7 的 ``probe.shape_probe()`` 是**静态封闭词表推断**，所有结果都带
``runtime_verified=False``，并且图上两个兜底 benchmark 的形式是占位串
``"unknown"``，词表里没有对应项 —— 这就是 4 处 ``unknown_forms`` 的来源。

本模块不改变 ``shape_probe()`` 的既有契约（旧测试锁定 6 个 probe /
``method=vocab_inference``），而是新增一条独立实测链路：

1. **表单补全**：``unknown`` 不是编造一个 shape，而是按确定性规则从
   同族/同名 benchmark 继承已声明的形式，并标 ``form_source`` 与
   ``inherited_from``。继承来的形式明确标 ``paper_declared=False``。
2. **真跑 mini-batch**：生成纯 stdlib 的 ``MINIBATCH_SCRIPT.py``，在隔离
   子进程里**实际构造** batch_size=4 的样本，用递归测量得到真实
   ``shape / dtype / dims / n_scalars``，结果经 stdout 回传。
3. **回填**：写 ``MINIBATCH_PROBE.json`` / ``OBSERVED_SHAPES.json``，
   每个探针标 ``runtime_verified``；无法构造的形式如实留在
   ``unknown_forms``，绝不伪装成实测。

脚本不读写任何文件、不读期望值、import 只允许 stdlib，且复用
``executor.check_script_safety()`` 做 AST 白名单检查。

    from capfactory.reprospec.minibatch import write_runtime_probe
    summary = write_runtime_probe(spec, "storage_cf/repro_runs/2411.06608")
    summary["n_runtime_verified"], summary["n_unknown_remaining"]
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .executor import check_script_safety
from .probe import shape_probe

_UNKNOWN = {"", "unknown", "none", "null", "n/a", "未标注", "未登记"}
DEFAULT_BATCH = 4
DEFAULT_TIMEOUT = 30

_SCRIPT_TEMPLATE = '''\
"""Auto-generated mini-batch shape probe (GGR P3-2).
Pure stdlib. Constructs real mini-batches, measures observed shapes.
No file IO, no expected values, no model weights.
"""
import json

PROBES = json.loads({probes!r})
BATCH = {batch}

SMILES = ["CCO", "c1ccccc1", "CC(=O)O", "C1CCCCC1", "CN1C=NC2=C1C(=O)N(C)C(=O)N2C"]


def construct(form, b):
    f = str(form or "").strip()
    low = f.lower()
    if low == "smiles":
        return [SMILES[i % len(SMILES)] for i in range(b)]
    if f == "向量":
        return [[float((i + j) % 7) / 7.0 for j in range(8)] for i in range(b)]
    if f == "标量":
        return [0.5 + 0.1 * i for i in range(b)]
    if f in ("3D坐标", "坐标"):
        return [[[float((i + j + k) % 9) / 9.0 for k in range(3)]
                 for j in range(3)] for i in range(b)]
    if f in ("图", "分子图"):
        return {{
            "x": [[float((i + j) % 5) / 5.0 for j in range(8)] for i in range(b)],
            "edge_index": [[i for i in range(b)], [(i + 1) % b for i in range(b)]],
        }}
    if f == "序列":
        return [[(i + j) % 20 for j in range(12)] for i in range(b)]
    if f == "分布":
        return [[float((i + j) % 11) / 11.0 for j in range(16)] for i in range(b)]
    return None


def count_scalars(x):
    if isinstance(x, dict):
        return sum(count_scalars(v) for v in x.values())
    if isinstance(x, (list, tuple)):
        return sum(count_scalars(v) for v in x)
    return 1


def inspect(x):
    if isinstance(x, dict):
        return {{"kind": "struct",
                 "fields": {{k: inspect(v) for k, v in x.items()}},
                 "n_scalars": count_scalars(x)}}
    dims = []
    cur = x
    while isinstance(cur, (list, tuple)) and len(cur) > 0:
        dims.append(len(cur))
        cur = cur[0]
    shape = "(" + ", ".join(str(d) for d in dims)
    if len(dims) == 1:
        shape += ","
    shape += ")"
    return {{"kind": "array", "shape": shape, "dims": dims,
             "dtype": type(cur).__name__, "n_scalars": count_scalars(x)}}


def main():
    out = []
    for p in PROBES:
        rec = {{"benchmark": p["benchmark"], "label": p["label"]}}
        for side in ("input", "output"):
            form = p[side + "_form"]
            obj = construct(form, BATCH)
            rec[side] = {{
                "form": form,
                "constructed": obj is not None,
                "observed": inspect(obj) if obj is not None else None,
                "reason": "" if obj is not None else "form_not_declared_or_unregistered",
            }}
        out.append(rec)
    print(json.dumps({{"batch_size": BATCH, "probes": out}},
                     ensure_ascii=False, sort_keys=True))


main()
'''


def _is_unknown(v: Any) -> bool:
    return str(v or "").strip().lower() in _UNKNOWN


def resolve_forms(probes: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]],
                                                        List[Dict[str, Any]]]:
    """把 ``unknown`` 形式按同族规则补全；返回 (脚本输入, 继承审计)。

    优先级：精确同 label → label 首词同族。两者都明确记录来源，
    继承结果不是论文原文声明（``paper_declared=False``）。
    """
    resolved: List[Dict[str, Any]] = []
    log: List[Dict[str, Any]] = []
    for i, p in enumerate(probes):
        label = str(p.get("label") or "")
        first = label.split()[0].lower() if label.split() else ""
        rec: Dict[str, Any] = {"benchmark": p.get("benchmark"),
                               "label": label}
        for side in ("input", "output"):
            key = f"{side}_form"
            raw = p.get(key)
            if not _is_unknown(raw):
                rec[key] = raw
                continue
            cands: List[Tuple[int, int, str, str]] = []
            for j, q in enumerate(probes):
                if j == i or _is_unknown(q.get(key)):
                    continue
                qlabel = str(q.get("label") or "").lower()
                if qlabel == label.lower():
                    score = 2
                elif first and qlabel.startswith(first):
                    score = 1
                else:
                    continue
                cands.append((score, j, str(q.get(key)),
                              str(q.get("benchmark") or "")))
            if cands:
                cands.sort(key=lambda x: (-x[0], x[1]))
                _, _, form, src = cands[0]
                rec[key] = form
                log.append({"benchmark": p.get("benchmark"), "side": key,
                            "declared": str(raw), "effective": form,
                            "inherited_from": src, "rule":
                            "exact_label" if cands[0][0] == 2 else "label_prefix",
                            "paper_declared": False})
            else:
                rec[key] = ""
                log.append({"benchmark": p.get("benchmark"), "side": key,
                            "declared": str(raw), "effective": "",
                            "inherited_from": "", "rule": "unresolved",
                            "paper_declared": False})
        resolved.append(rec)
    return resolved, log


def build_minibatch_script(probes: List[Dict[str, Any]],
                           batch_size: int = DEFAULT_BATCH) -> str:
    """生成纯 stdlib 的 mini-batch 实测脚本（JSON 文本用 repr 安全内嵌）。"""
    return _SCRIPT_TEMPLATE.format(
        probes=json.dumps(probes, ensure_ascii=False, sort_keys=True),
        batch=int(batch_size))


def write_runtime_probe(spec: Any, out_dir: str | Path, *,
                        batch_size: int = DEFAULT_BATCH,
                        timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """生成 → 静态检查 → 隔离子进程真跑 → 回填，写 ``MINIBATCH_PROBE.json``。"""
    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)
    probes = shape_probe(spec)
    resolved, inheritance = resolve_forms(probes)
    src = build_minibatch_script(resolved, batch_size)
    problems = check_script_safety(src)
    summary: Dict[str, Any] = {
        "paper_id": spec.paper_id, "spec_hash": spec.spec_hash,
        "method": "mini_batch_runtime", "batch_size": batch_size,
        "script_sha": "sha256:" + hashlib.sha256(
            src.encode("utf-8")).hexdigest(),
        "n_probes": len(probes), "n_inherited_forms": len(inheritance),
        "inheritance": inheritance, "probes": [], "ok": False,
        "warnings": [], "files": [],
    }
    if problems:
        summary["warnings"].append(f"脚本安全检查未通过：{problems}")
        _write(summary, p)
        return summary

    script = p / "MINIBATCH_SCRIPT.py"
    script.write_text(src, encoding="utf-8")
    summary["files"].append("MINIBATCH_SCRIPT.py")
    env = {"PATH": os.environ.get("PATH", ""), "LANG": "C.UTF-8",
           "PYTHONHASHSEED": "0"}
    try:
        r = subprocess.run([sys.executable, str(script.resolve())],
                           cwd=str(p.resolve()), env=env, timeout=timeout,
                           capture_output=True, text=True, check=False)
    except Exception as exc:  # noqa: BLE001
        summary["warnings"].append(f"mini-batch 子进程失败：{type(exc).__name__}: {exc}")
        _write(summary, p)
        return summary
    if r.returncode != 0:
        summary["warnings"].append(
            f"mini-batch 退出码 {r.returncode}: {r.stderr.strip()[:300]}")
        _write(summary, p)
        return summary
    try:
        observed = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        summary["warnings"].append(f"mini-batch 输出无法解析：{exc}")
        _write(summary, p)
        return summary
    (p / "OBSERVED_SHAPES.json").write_text(
        json.dumps(observed, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["files"].append("OBSERVED_SHAPES.json")
    by_id = {x.get("benchmark"): x for x in observed.get("probes") or []}

    n_verified = 0
    n_unknown = 0
    for orig, eff in zip(probes, resolved):
        obs = by_id.get(orig.get("benchmark")) or {}
        row: Dict[str, Any] = {
            "benchmark": orig.get("benchmark"), "label": orig.get("label"),
            "declared_input_form": orig.get("input_form"),
            "declared_output_form": orig.get("output_form"),
            "effective_input_form": eff.get("input_form"),
            "effective_output_form": eff.get("output_form"),
            "vocab_input_shape": orig.get("input_shape"),
            "vocab_output_shape": orig.get("output_shape"),
            "input_observed": obs.get("input"),
            "output_observed": obs.get("output"),
            "form_sources": [x for x in inheritance
                             if x["benchmark"] == orig.get("benchmark")],
            "unknown_forms": [], "runtime_verified": False,
        }
        for side in ("input", "output"):
            o = obs.get(side) or {}
            if not o.get("constructed"):
                row["unknown_forms"].append(f"{side}_form")
        row["runtime_verified"] = not row["unknown_forms"]
        row["method"] = "mini_batch_runtime" if row["runtime_verified"] \
            else "mini_batch_partial"
        if row["runtime_verified"]:
            n_verified += 1
        n_unknown += len(row["unknown_forms"])
        summary["probes"].append(row)

    summary["n_runtime_verified"] = n_verified
    summary["n_unknown_remaining"] = n_unknown
    summary["ok"] = n_unknown == 0
    if n_unknown:
        summary["warnings"].append(
            f"{n_unknown} 处形式无法构造 mini-batch，已如实保留为 unknown")
    if inheritance:
        summary["warnings"].append(
            f"{len(inheritance)} 处表单来自同族继承，非论文原文声明")
    _write(summary, p)
    return summary


def _write(summary: Dict[str, Any], p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)
    (p / "MINIBATCH_PROBE.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if "MINIBATCH_PROBE.json" not in summary["files"]:
        summary["files"].append("MINIBATCH_PROBE.json")
