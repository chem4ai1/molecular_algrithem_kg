"""模块级抽取与论文↔代码对齐（解决「论文组件名 ≠ 代码实现名」）。

思路（按用户要求）：

1. **抽取阶段不再只抽算法名词**，而是把方法**分解成模块节点**
   （``AlgorithmStep`` 承载 module_name / mechanism / inputs / outputs / parameters）；
2. **读仓库的代码架构**（AST → 类/函数/签名/因果角色），
   把这份结构清单**注入同一个 prompt**，让大模型同时看论文与代码；
3. 模型直接给出每个模块对应的 `code_symbols` 与 `grounding_status`，
   再用确定性规则（mechanism ↔ 因果角色 + IO 关键词）做兜底校验。

这样 `EGCL`（论文）与 `EGNN.forward/message`（代码）不需要同名也能对齐。
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..po import POGraph
from ..utils import now_iso, parse_llm_json
from .layers import CAUSAL_TYPES, MECHANISMS, GROUNDING_STATUS

# 代码符号名 → 机制（用于确定性兜底）
MECHANISM_HINTS: Dict[str, Tuple[str, ...]] = {
    "message_compute": ("message", "edge", "phi_e", "msg"),
    "coordinate_update": ("coord", "coors", "pos", "x_", "update_x"),
    "feature_update": ("feat", "hidden", "h_", "node", "phi_h"),
    "aggregation": ("aggregate", "sum", "pool", "reduce", "scatter"),
    "edge_inference": ("edge", "adj", "knn", "radius", "neighbor"),
    "normalization": ("norm", "scale", "bn", "layernorm"),
    "attention": ("attn", "attention"),
    "readout": ("readout", "global", "graph_emb", "pooling"),
    "loss": ("loss", "criterion", "objective"),
    "scoring": ("score", "predict", "classifier", "eval"),
    "initialization": ("init", "reset", "setup"),
    "encoding": ("encode", "embedd", "embed"),
    "sampling": ("sample", "sampler", "decode"),
}


def infer_causal_role(name: str, signature: str) -> str:
    """从函数名/签名推断 CAD 七类因果角色。"""
    low = f"{name} {signature}".lower()
    if any(k in low for k in ("input", "load", "read", "feature")) and "output" not in low:
        return "input"
    if any(k in low for k in ("predict", "classifier", "score", "output", "final")):
        return "decision"
    if any(k in low for k in ("aggregate", "sum", "pool", "reduce", "propagate")):
        return "aggregation"
    if any(k in low for k in ("message", "edge", "attention", "attn", "forward", "update")):
        return "mechanism"
    if any(k in low for k in ("init", "embedd", "encode", "norm")):
        return "state"
    if any(k in low for k in ("weight", "param", "bias")):
        return "parameter"
    return "output" if "return" in low else "state"


def infer_mechanism(name: str, signature: str) -> str:
    low = f"{name} {signature}".lower()
    for mech, hints in MECHANISM_HINTS.items():
        if any(h in low for h in hints):
            return mech
    return "other"


# ---------------------------------------------------------------------------
# ① 代码架构读取
# ---------------------------------------------------------------------------
def _ast_func_type(node, owner: str, sig: str, tree) -> str:
    """AST 优先判定函数类型（替代纯名称猜测）。"""
    if isinstance(node, ast.ClassDef):
        return "class"
    name = (node.name or "").lower()
    if name == "__init__":
        return "init"
    # 生成器：函数体内有 yield
    if any(isinstance(x, (ast.Yield, ast.YieldFrom)) for x in ast.walk(node)):
        return "generator"
    if name == "forward":
        return "forward"
    for kw, t in (("loss", "loss"), ("criterion", "loss"),
                  ("optim", "optimizer"), ("schedule", "scheduler"),
                  ("_load", "io"), ("load_", "io"), ("save", "io"),
                  ("read", "io"), ("write", "io"), ("dump", "io"),
                  ("parse", "transform"), ("process", "transform"),
                  ("normalize", "transform"), ("canonical", "transform"),
                  ("_get", "accessor"), ("get_", "accessor")):
        if kw in name:
            return t
    return "helper"


def code_structure(repo_root: str | Path, *, max_files: int = 12,
                   max_symbols: int = 60) -> Dict[str, Any]:
    """AST 解析仓库 → 结构化符号清单（绝不执行源码）。"""
    root = Path(repo_root)
    out: Dict[str, Any] = {"repo": str(root), "files": [], "symbols": [],
                           "n_files": 0, "n_symbols": 0}
    if not root.exists():
        return out
    for fp in sorted([p for p in root.rglob("*.py") if ".git" not in p.parts])[:max_files]:
        try:
            tree = ast.parse(fp.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, OSError):
            continue
        rel = str(fp.relative_to(root))
        out["files"].append(rel)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            args = [a.arg for a in getattr(node, "args", ast.arguments(
                args=[], vararg=None, kwonlyargs=[], kw_defaults=[], kwarg=None,
                defaults=[])).args][:10]
            sig = f"{node.name}({', '.join(args)})"
            doc = (ast.get_docstring(node) or "")[:100].replace("\n", " ")
            owner = ""
            if isinstance(node, ast.ClassDef):
                methods = [m.name for m in node.body
                           if isinstance(m, ast.FunctionDef)][:8]
                sig = f"class {node.name} methods={methods}"
            else:
                # 找所属类
                for parent in ast.walk(tree):
                    if isinstance(parent, ast.ClassDef) and node in parent.body:
                        owner = parent.name
                        break
            is_func = not isinstance(node, ast.ClassDef)
            ret = ""
            if is_func and getattr(node, "returns", None) is not None:
                try:
                    ret = ast.unparse(node.returns)[:60]
                except Exception:  # noqa: BLE001
                    ret = ""
            ftype = _ast_func_type(node, owner, sig, tree)
            qualified = f"{owner}.{node.name}" if owner else node.name
            item = {"file": rel, "name": node.name,
                    "params": ", ".join(args),
                    "returns": ret,
                    "func_type": ftype,
                    "qualified": qualified,
                    "kind": "class" if isinstance(node, ast.ClassDef) else "function",
                    "signature": sig, "owner": owner, "doc": doc,
                    "lineno": getattr(node, "lineno", 0),
                    "causal_role": infer_causal_role(node.name, sig),
                    "mechanism": infer_mechanism(node.name, sig)}
            out["symbols"].append(item)
            if len(out["symbols"]) >= max_symbols:
                break
        if len(out["symbols"]) >= max_symbols:
            break
    out["n_files"] = len(out["files"])
    out["n_symbols"] = len(out["symbols"])
    return out


def _symbol_index(struct: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """符号索引：同时支持 ``message`` / ``EGNN_Sparse.message`` /
    ``egnn_pytorch.py::message`` 三种写法（模型常给限定名）。"""
    idx: Dict[str, Dict[str, Any]] = {}
    for s in struct.get("symbols", []):
        for key in (s.get("name"), s.get("qualified"),
                    f"{s.get('file')}::{s.get('name')}"):
            if key:
                idx.setdefault(str(key), s)
    return idx


def _compact_structure(struct: Dict[str, Any], *, limit: int = 40) -> str:
    """把代码结构压成 prompt 可读的短清单。"""
    lines: List[str] = []
    for s in struct.get("symbols", [])[:limit]:
        owner = f"{s['owner']}." if s.get("owner") else ""
        lines.append(f"- {s.get('qualified') or s['name']} @ {s['file']} "
                     f"[{s['kind']}/{s['causal_role']}/{s['mechanism']}] "
                     f"{s['signature'][:80]}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ② 模块级抽取 prompt（论文 + 代码架构同时给模型）
# ---------------------------------------------------------------------------
MODULE_PROMPT = """你在把一篇 AI4Science 论文的方法**分解成模块**，并把每个模块对齐到代码仓库的真实符号。

左侧是论文片段，右侧是该仓库 AST 解析出的符号清单。注意：论文里的组件名与代码里的
类/函数名常常不同（例如论文叫 EGCL，代码叫 EGNN.forward），**请按机制与输入输出对齐，不要按名字**。

输出严格 JSON（不要代码块）：
{
  "method": {"name": "", "aliases": [""]},
  "modules": [
    {"module_name": "论文里的模块名",
     "mechanism": "message_compute|coordinate_update|feature_update|aggregation|edge_inference|normalization|attention|readout|pooling|encoding|decoding|sampling|loss|scoring|filtering|initialization|other",
     "causal_role": "input|parameter|mechanism|state|aggregation|decision|output",
     "inputs": ["张量/字段名"],
     "outputs": ["张量/字段名"],
     "parameters": ["可学习子网络/参数"],
     "equation_ref": "Eq.3 / Alg.1",
     "order": 1,
     "code_symbols": ["代码清单里真实存在的符号名"],
     "grounding_status": "matched|partial|conceptual_gap|implementation_gap|unresolved",
     "evidence": "论文里支持这个模块的一句话"
    }
  ],
  "conceptual_gaps": ["论文有、代码找不到的机制"],
  "implementation_gaps": ["代码有、论文没写的工程细节"]
}

硬性规则：
1. modules 数量 4–10，必须覆盖方法主干，不要只给一个整体方法名。
2. code_symbols 只能从下面的代码清单里选**真实存在**的符号；找不到就留空并写 conceptual_gap。
3. 一个函数可以实现多个机制（例如 forward 同时做 message/坐标/特征更新），
   允许被多个模块引用，但请优先给更具体的符号（如 EGNN_Sparse.message）。
4. inputs/outputs 写论文里的张量/变量（如 h^l, x^l, m_ij），不要写数据集名。
5. 输出 <= 3000 token。

## 代码符号清单
{code}

## 机制词表
{mechanisms}

## 论文片段
{paper}

只输出 JSON。"""


def module_prompt(paper_text: str, struct: Dict[str, Any], *,
                  paper_chars: int = 14000) -> str:
    return (MODULE_PROMPT.replace("{code}", _compact_structure(struct))
                        .replace("{mechanisms}", ", ".join(MECHANISMS))
                        .replace("{paper}", paper_text[:paper_chars]))


def extract_modules(paper_text: str, struct: Dict[str, Any], *,
                    chat_fn: Any, retries: int = 2) -> Dict[str, Any]:
    """调 LLM 拿模块分解；模型偶发格式漂移时重试，仍失败返回空 dict。"""
    prompt = module_prompt(paper_text, struct)
    for attempt in range(max(1, retries)):
        out = chat_fn(prompt)
        raw = parse_llm_json(out) or {}
        if raw.get("modules"):
            return raw
    return {}


# ---------------------------------------------------------------------------
# ③ 确定性兜底对齐
# ---------------------------------------------------------------------------
def deterministic_align(modules: Sequence[Dict[str, Any]],
                        struct: Dict[str, Any]) -> Dict[str, Any]:
    """按 mechanism + 签名关键词校正 LLM 给出的 code_symbols。"""
    symbols = _symbol_index(struct)
    out: Dict[str, Any] = {"checked": 0, "valid": 0, "hallucinated": [],
                           "suggested": [], "shared_implementations": []}
    used: Dict[str, int] = {}
    for m in modules:
        for sym in m.get("code_symbols") or []:
            out["checked"] += 1
            if sym in symbols:
                out["valid"] += 1
                used[sym] = used.get(sym, 0) + 1
            else:
                out["hallucinated"].append(sym)
        # 兜底建议：LLM 没给符号时按 mechanism 找
        if not m.get("code_symbols"):
            mech = m.get("mechanism")
            cands = [s["name"] for s in struct.get("symbols", [])
                     if s.get("mechanism") == mech][:3]
            if cands:
                out["suggested"].append({"module": m.get("module_name"),
                                         "mechanism": mech, "candidates": cands})
    # 一个 forward() 实现多个机制是常态，作为 shared_implementations 正常输出
    out["shared_implementations"] = [k for k, v in used.items() if v > 2]
    out["conflicts"] = out["shared_implementations"]      # 兼容旧调用方
    return out


# ---------------------------------------------------------------------------
# ④ 建图
# ---------------------------------------------------------------------------
def build_module_graph(raw: Dict[str, Any], struct: Dict[str, Any], *,
                       doc_id: str) -> Tuple[POGraph, Dict[str, Any]]:
    g = POGraph(f"modules::{doc_id}")
    st: Dict[str, Any] = {"nodes": 0, "edges": 0, "modules": 0,
                          "code_symbols": 0, "aligned": 0, "by_status": {},
                          "problems": []}
    by_name = _symbol_index(struct)

    def nid(prefix: str, key: str) -> str:
        return f"{prefix}:{re.sub(r'[^a-z0-9]+', '_', str(key).lower())[:50]}"

    method = raw.get("method") or {}
    mname = method.get("name") or doc_id
    aid = nid("algorithm", mname)
    g.node(aid, "Algorithm", mname, name=mname,
           aliases=method.get("aliases") or [], kind="method")
    st["nodes"] += 1

    cid = nid("algorithmcomposition", mname)
    g.node(cid, "AlgorithmComposition", f"{mname} pipeline", name=f"{mname} pipeline")
    g.assert_rel(aid, cid, "HAS_COMPOSITION")
    st["nodes"] += 1
    st["edges"] += 1

    # 代码侧节点（只建被引用的符号，避免 30 个孤立节点）
    code_ids: Dict[str, str] = {}
    for m in raw.get("modules") or []:
        for sym in m.get("code_symbols") or []:
            if sym in by_name and sym not in code_ids:
                s = by_name[sym]
                fid = nid("codefunction", f"{s['file']}::{sym}")
                g.node(fid, "CodeFunction", sym, name=sym,
                       purpose=(s.get("doc") or "").split(".")[0][:80]
                       or f"实现 {sym} 逻辑",
                       comment=s.get("doc", ""),
                       params=s.get("params", ""),
                       returns=s.get("returns", ""),
                       func_type=s.get("func_type", "helper"),
                       signature=s.get("signature", ""),
                       owner_class=s.get("owner", ""),
                       module_path=s["file"], lineno=s.get("lineno", 0))
                code_ids[sym] = fid
                st["nodes"] += 1
                st["code_symbols"] += 1

    for i, m in enumerate(raw.get("modules") or []):
        if not isinstance(m, dict) or not m.get("module_name"):
            continue
        name = str(m["module_name"])
        sid = nid("algorithmstep", f"{doc_id}:{i}:{name}")
        status = m.get("grounding_status") or "unresolved"
        if status not in GROUNDING_STATUS:
            status = "unresolved"
        g.node(sid, "AlgorithmStep", name, module_name=name,
               mechanism=m.get("mechanism") or "other",
               causal_role=m.get("causal_role") or "mechanism",
               inputs=m.get("inputs") or [], outputs=m.get("outputs") or [],
               parameters=m.get("parameters") or [],
               equation_ref=m.get("equation_ref") or "",
               order=m.get("order") or i + 1, role=m.get("role") or "tool",
               phase=m.get("phase") or "inference",
               algorithm_id=aid, is_baseline=False,
               code_symbols=m.get("code_symbols") or [],
               grounding_status=status, composition_id=cid,
               evidence=m.get("evidence") or "")
        g.assert_rel(cid, sid, "HAS_STEP")
        g.assert_rel(aid, sid, "HAS_MODULE_DETAIL")
        st["nodes"] += 1
        st["edges"] += 2
        st["modules"] += 1
        st["by_status"][status] = st["by_status"].get(status, 0) + 1
        for sym in m.get("code_symbols") or []:
            fid = code_ids.get(sym)
            if fid:
                g.assert_rel(fid, sid, "IMPLEMENTS_MODULE")
                g.assert_rel(fid, sid, "REALIZES")
                st["edges"] += 2
                st["aligned"] += 1

    # 模块拓扑
    steps = sorted([n for n in g.nodes.values() if n.type == "AlgorithmStep"],
                   key=lambda n: n.attrs.get("order", 0))
    for a, b in zip(steps, steps[1:]):
        g.assert_rel(a.id, b.id, "FLOWS_TO")
        st["edges"] += 1

    g.meta["modules"] = {"doc_id": doc_id, "at": now_iso(), "stats": st,
                         "conceptual_gaps": raw.get("conceptual_gaps") or [],
                         "implementation_gaps": raw.get("implementation_gaps") or []}
    return g, st
