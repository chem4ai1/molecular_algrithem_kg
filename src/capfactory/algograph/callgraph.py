"""L1 调用/数据流层：作用域符号表 + 站点级 CALLS + 简化 FLOWS_TO.

借鉴 ``code-graph-rag``（站点属性、one-edge-per-site、resolution 标签、
单向前向 tainted 表）与 ``axiomcodegraph``（binding identity = scope‖name、
LEGB 结构链接、未解析显式留痕、两阶段解析），但**只用标准库 ast**：

* Pass 1 收集全库定义 / import 绑定 / 作用域 / 继承；
* Pass 2 逐调用站点解析目标，**禁止按函数名模糊匹配**；
* Pass 3 单函数内前向数据流扫描（Copy / Transform / Kill），生成 arg/return 流边。

任何解析不了的调用都写入 ``unresolved_site``，绝不静默丢弃；
``AlgoGraph.reachability()`` 会同时返回 ``unresolved_count``。
"""

from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .schema import make_qn, stable_hash
from .store import AlgoGraph

BUILTINS = set(dir(builtins))
# 接收者类型未知、但可明确判定为「外部容器/字符串 API」的方法：
# 不按名字扇出到本地同名函数（Axiom 的 NO NAME MATCHING），
# 而是显式标 heuristic 指向内置 API，避免把噪声误报成"未解析调用"。
BUILTIN_METHODS = {
    "append", "extend", "insert", "pop", "remove", "clear", "copy", "count",
    "index", "sort", "reverse", "keys", "values", "items", "get", "setdefault",
    "update", "add", "discard", "union", "intersection", "difference",
    "strip", "lstrip", "rstrip", "split", "rsplit", "join", "replace",
    "startswith", "endswith", "lower", "upper", "format", "encode", "decode",
    "reshape", "astype", "tolist", "sum", "mean", "max", "min", "ravel",
}


@dataclass
class Binding:
    """作用域绑定；identity 由 (scope_qn, name) 确定性生成，不做名字猜测。"""

    name: str
    scope_qn: str
    kind: str = "local"            # import | param | local | attr | global | class | self
    target_qn: str = ""
    type_qn: str = ""

    @property
    def qn(self) -> str:
        return make_qn("binding", self.scope_qn, self.name)


@dataclass
class Scope:
    qn: str
    kind: str                       # module | class | function
    parent: str = ""
    bindings: Dict[str, Binding] = field(default_factory=dict)
    owner_class_qn: str = ""

    def lookup(self, name: str, scopes: Dict[str, "Scope"]) -> Optional[Binding]:
        """LEGB：Local → Enclosing → Global(module) → Builtin。"""
        cur: Optional[Scope] = self
        guard = 0
        while cur and guard < 32:
            b = cur.bindings.get(name)
            if b:
                return b
            cur = scopes.get(cur.parent) if cur.parent else None
            guard += 1
        return None


class CallGraphBuilder:
    """在已有结构图上补充 CALLS / IMPORTS / INHERITS / FLOWS_TO。"""

    def __init__(self) -> None:
        self.func_by_name: Dict[str, List[str]] = {}
        self.func_by_module: Dict[str, Dict[str, str]] = {}
        self.class_methods: Dict[str, Dict[str, str]] = {}
        self.class_by_name: Dict[str, str] = {}
        self.imports: Dict[str, Dict[str, str]] = {}
        self.scopes: Dict[str, Scope] = {}
        self.func_scope: Dict[str, str] = {}
        self.stats: Dict[str, Any] = {}

    # -- 主入口 -----------------------------------------------------------
    def enrich(self, graph: AlgoGraph, sources: Dict[str, str]) -> AlgoGraph:
        """``sources = {module_qn: python_source}``；两阶段 + 流分析。"""
        self._pass1_definitions(graph, sources)
        self._pass2_calls(graph, sources)
        self._pass3_flows(graph, sources)
        self.stats = {
            "modules": len(sources),
            "functions_indexed": sum(len(v) for v in self.func_by_name.values()),
            "calls": sum(1 for e in graph.edges if e.type == "CALLS"),
            "unresolved": len(graph.by_type("unresolved_site")),
            "flows": sum(1 for e in graph.edges if e.type == "FLOWS_TO"),
            "resolutions": {r: sum(1 for e in graph.edges
                                   if e.type == "CALLS" and e.attrs.get("resolution") == r)
                            for r in ("exact", "method", "multi", "heuristic", "unresolved")},
        }
        graph.meta["callgraph_stats"] = self.stats
        return graph

    # -- Pass 1 -----------------------------------------------------------
    def _pass1_definitions(self, g: AlgoGraph, sources: Dict[str, str]) -> None:
        for n in g.by_type("func_name"):
            self.func_by_name.setdefault(n.get("name", n.label), []).append(n.qn)
            mod = str(n.qn).split("::", 1)[0]
            self.func_by_module.setdefault(mod, {})[n.get("name", n.label)] = n.qn
            qual = n.get("qualified_name", "")
            if "." in qual.rsplit(".", 1)[0]:
                owner = qual.rsplit(".", 2)[0] if qual.count(".") >= 2 else ""
                for cqn, cname in [(c.qn, c.label) for c in g.by_type("class_unit")]:
                    if owner.endswith(cname) or cname in qual:
                        self.class_methods.setdefault(cqn, {})[n.get("name", n.label)] = n.qn
                        break
        for c in g.by_type("class_unit"):
            self.class_by_name[c.label] = c.qn
            for b in c.get("bases", []) or []:
                target = self.class_by_name.get(str(b).split(".")[-1])
                if not target:
                    target = self._external(g, str(b), "third_party")
                g.add_edge(c.qn, target, "INHERITS")

        for mod_qn, source in sources.items():
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            module_node = f"{mod_qn}#module"
            scope = Scope(qn=module_node, kind="module")
            self.scopes[module_node] = scope
            self.imports.setdefault(mod_qn, {})
            for stmt in ast.walk(tree):
                if isinstance(stmt, ast.Import):
                    for a in stmt.names:
                        full = a.name
                        local = a.asname or a.name.split(".")[0]
                        self.imports[mod_qn][local] = full
                        scope.bindings[local] = Binding(local, module_node, "import", full)
                        ext = self._external(g, full, "third_party")
                        g.add_edge(module_node, ext, "IMPORTS",
                                   alias=local, imported_name=full,
                                   line=stmt.lineno, col=stmt.col_offset)
                elif isinstance(stmt, ast.ImportFrom):
                    base = stmt.module or ""
                    for a in stmt.names:
                        full = f"{base}.{a.name}" if base else a.name
                        local = a.asname or a.name
                        self.imports[mod_qn][local] = full
                        scope.bindings[local] = Binding(local, module_node, "import", full)
                        ext = self._external(g, full, "third_party")
                        g.add_edge(module_node, ext, "IMPORTS",
                                   alias=local, imported_name=a.name,
                                   line=stmt.lineno, col=stmt.col_offset)
                elif isinstance(stmt, ast.ClassDef):
                    cqn = f"{mod_qn}::{stmt.name}#class"
                    self.class_by_name.setdefault(stmt.name, cqn)

        for mod_qn, source in sources.items():
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            self._collect_scopes(tree, mod_qn, f"{mod_qn}#module", "", g)

    def _collect_scopes(self, node: ast.AST, mod_qn: str, parent_scope: str,
                        prefix: str, g: AlgoGraph) -> None:
        for stmt in getattr(node, "body", []) or []:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = prefix + stmt.name
                fqn = f"{mod_qn}::{qual}#name"
                scope = Scope(qn=fqn, kind="function", parent=parent_scope)
                args = getattr(stmt, "args", None)
                if args:
                    allargs = (list(getattr(args, "posonlyargs", []) or []) +
                               list(getattr(args, "args", []) or []) +
                               list(getattr(args, "kwonlyargs", []) or []))
                    for a in allargs:
                        scope.bindings[a.arg] = Binding(a.arg, fqn, "param",
                                                        type_qn=_annotation(a.annotation))
                    if getattr(args, "vararg", None):
                        scope.bindings[args.vararg.arg] = Binding(args.vararg.arg, fqn, "param")
                    if getattr(args, "kwarg", None):
                        scope.bindings[args.kwarg.arg] = Binding(args.kwarg.arg, fqn, "param")
                if prefix.endswith("."):
                    owner = prefix[:-1].split(".")[-1]
                    scope.owner_class_qn = self.class_by_name.get(owner, "")
                    scope.bindings["self"] = Binding("self", fqn, "self",
                                                     type_qn=scope.owner_class_qn)
                    scope.bindings["cls"] = Binding("cls", fqn, "self",
                                                    type_qn=scope.owner_class_qn)
                # 局部赋值 /  annotated assign / for-target
                for sub in ast.walk(stmt):
                    if isinstance(sub, ast.Assign):
                        for t in sub.targets:
                            for nm in _target_names(t):
                                if nm not in scope.bindings:
                                    scope.bindings[nm] = Binding(nm, fqn, "local")
                    elif isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name):
                        scope.bindings.setdefault(
                            sub.target.id,
                            Binding(sub.target.id, fqn, "local",
                                    type_qn=_annotation(sub.annotation)))
                    elif isinstance(sub, (ast.For, ast.AsyncFor)):
                        for nm in _target_names(sub.target):
                            scope.bindings.setdefault(nm, Binding(nm, fqn, "local"))
                self.scopes[fqn] = scope
                self.func_scope[fqn] = fqn
                self._collect_scopes(stmt, mod_qn, fqn, qual + ".", g)
            elif isinstance(stmt, ast.ClassDef):
                cqn = f"{mod_qn}::{prefix + stmt.name}#class"
                self.class_by_name.setdefault(prefix + stmt.name, cqn)
                self._collect_scopes(stmt, mod_qn, parent_scope, prefix + stmt.name + ".", g)

    # -- Pass 2 -----------------------------------------------------------
    def _pass2_calls(self, g: AlgoGraph, sources: Dict[str, str]) -> None:
        for mod_qn, source in sources.items():
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            self._calls_in_scope(tree, mod_qn, "", g)

    def _calls_in_scope(self, node: ast.AST, mod_qn: str,
                        prefix: str, g: AlgoGraph) -> None:
        """每个调用站点**只归属一个 caller**：模块级非定义语句归 module，
        函数/方法内语句归该函数（嵌套函数单独归属，不重复计数）。"""
        module_caller = f"{mod_qn}#module"
        module_scope = self.scopes.get(module_caller) or Scope(module_caller, "module")
        for stmt in getattr(node, "body", []) or []:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for call in ast.walk(stmt):
                if isinstance(call, ast.Call):
                    self._resolve_call(g, mod_qn, module_caller, module_scope, call)

        for fn, qual_prefix in self._iter_callables(node, prefix):
            caller = f"{mod_qn}::{qual_prefix + fn.name}#name"
            scope = self.scopes.get(caller) or Scope(caller, "function")
            for call in self._own_calls(fn):
                self._resolve_call(g, mod_qn, caller, scope, call)

    @staticmethod
    def _iter_callables(node: ast.AST, prefix: str):
        """yield (函数节点, qualname 前缀)，含嵌套函数与类方法。"""
        for stmt in getattr(node, "body", []) or []:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield stmt, prefix
                yield from CallGraphBuilder._iter_callables(stmt, prefix + stmt.name + ".")
            elif isinstance(stmt, ast.ClassDef):
                yield from CallGraphBuilder._iter_callables(stmt, prefix + stmt.name + ".")

    @staticmethod
    def _own_calls(fn: ast.AST) -> List[ast.Call]:
        """只收集该函数自身语句中的调用，不下钻嵌套函数/类（避免重复归属）。"""
        out: List[ast.Call] = []
        for stmt in getattr(fn, "body", []) or []:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            out.extend(c for c in ast.walk(stmt) if isinstance(c, ast.Call))
        return out

    def _resolve_call(self, g: AlgoGraph, mod_qn: str, caller: str,
                      scope: Scope, call: ast.Call) -> None:
        written = _unparse(call.func)
        line, col = call.lineno, call.col_offset
        end_line = int(getattr(call, "end_lineno", 0) or line)
        end_col = int(getattr(call, "end_col_offset", 0) or col)
        kwarg_names = [k.arg or "" for k in call.keywords]
        common = {
            "line": line, "col": col, "end_line": end_line, "end_col": end_col,
            "site": f"{line}:{col}", "arg_count": len(call.args),
            "kwarg_names": kwarg_names, "callee_written": written,
        }

        target, resolution, receiver = "", "unresolved", ""
        if isinstance(call.func, ast.Name):
            name = call.func.id
            binding = scope.lookup(name, self.scopes)
            if binding and binding.target_qn and binding.target_qn in g.nodes:
                target, resolution = binding.target_qn, "exact"
            elif binding and binding.kind == "import":
                target, resolution = self._external(g, binding.target_qn, "third_party"), "exact"
            else:
                local = self.func_by_module.get(mod_qn, {}).get(name)
                if local:
                    target, resolution = local, "exact"
                elif name in BUILTINS:
                    target = self._external(g, f"builtins.{name}", "stdlib")
                    resolution = "exact"
                else:
                    candidates = self.func_by_name.get(name, [])
                    if len(candidates) == 1:
                        # 同名唯一定义且无歧义；仍标注为 heuristic，不冒充精确解析
                        target, resolution = candidates[0], "heuristic"
                    elif len(candidates) > 1:
                        target, resolution = candidates[0], "multi"
                        for c in candidates[1:]:
                            g.add_edge(caller, c, "CALLS",
                                       **{**common, "resolution": "multi",
                                          "note": "同名多定义，未做类型消歧"})
                    else:
                        target, resolution = self._external(g, name, "unresolved"), "unresolved"
        elif isinstance(call.func, ast.Attribute):
            attr = call.func.attr
            value = call.func.value
            recv_name = _unparse(value)
            receiver = recv_name
            binding = scope.lookup(recv_name, self.scopes) if isinstance(value, ast.Name) else None
            if binding and binding.kind == "self" and binding.type_qn:
                target = self.class_methods.get(binding.type_qn, {}).get(attr, "")
                if target:
                    resolution = "method"
                else:
                    target = self._external(g, f"{recv_name}.{attr}", "unresolved")
            elif binding and binding.kind == "import":
                target = self._external(g, f"{binding.target_qn}.{attr}", "third_party")
                resolution = "exact"
            elif isinstance(value, ast.Name) and value.id in self.imports.get(mod_qn, {}):
                full = self.imports[mod_qn][value.id]
                target = self._external(g, f"{full}.{attr}", "third_party")
                resolution = "exact"
            elif attr in BUILTIN_METHODS and attr not in self.func_by_name:
                # 明确是外部容器/字符串 API，不是本地方法歧义；标 heuristic 而非 unresolved
                target = self._external(g, f"builtins.<container>.{attr}", "stdlib")
                resolution = "heuristic"
            else:
                # Axiom 规则：接收者类型未知时绝不按 attr 名扇出同名方法
                target = self._external(g, f"{recv_name}.{attr}", "unresolved")
                resolution = "unresolved"
        else:
            target = self._external(g, written or "dynamic", "unresolved")

        if not target:
            target = self._external(g, written or "dynamic", "unresolved")
            resolution = "unresolved"
        g.add_edge(caller, target, "CALLS", **{**common, "resolution": resolution,
                                               "receiver_qn": receiver})
        if resolution == "unresolved":
            uqn = make_qn("unresolved", caller, f"{line}:{col}")
            g.node(uqn, "unresolved_site", written or "?",
                   caller_qn=caller, callee_written=written, line=line, col=col,
                   reason="no lexical/type binding resolved")

    # -- Pass 3 -----------------------------------------------------------
    def _pass3_flows(self, g: AlgoGraph, sources: Dict[str, str]) -> None:
        for mod_qn, source in sources.items():
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            self._flows_in_scope(tree, mod_qn, "", g)

    def _flows_in_scope(self, node: ast.AST, mod_qn: str,
                        prefix: str, g: AlgoGraph) -> None:
        for stmt in getattr(node, "body", []) or []:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._function_flows(stmt, mod_qn, prefix, g)
                self._flows_in_scope(stmt, mod_qn, prefix + stmt.name + ".", g)
            elif isinstance(stmt, ast.ClassDef):
                self._flows_in_scope(stmt, mod_qn, prefix + stmt.name + ".", g)

    def _function_flows(self, fn: ast.AST, mod_qn: str,
                        prefix: str, g: AlgoGraph) -> None:
        fqn = f"{mod_qn}::{prefix + fn.name}#name"
        in_qn = make_qn("artifact", "io", fqn, "in")
        out_qn = make_qn("artifact", "io", fqn, "out")
        g.node(in_qn, "data_artifact", f"{fn.name}() input", kind="param", dtype="args")
        g.node(out_qn, "data_artifact", f"{fn.name}() output", kind="result", dtype="return")
        params = {a.arg for a in
                  (list(getattr(getattr(fn, "args", None), "args", []) or []) +
                   list(getattr(getattr(fn, "args", None), "posonlyargs", []) or []))}
        tainted: Dict[str, str] = {p: in_qn for p in params}

        calls_by_line = {e.attrs.get("line"): e for e in g.outgoing(fqn, "CALLS")}
        for stmt in ast.walk(fn):
            if isinstance(stmt, ast.Call):
                edge = calls_by_line.get(stmt.lineno)
                if edge:
                    for i, arg in enumerate(stmt.args):
                        names = _name_refs(arg)
                        if any(nm in tainted for nm in names):
                            g.add_edge(in_qn, edge.target, "FLOWS_TO",
                                       kind="arg", via=f"arg:{i}", origin=in_qn,
                                       line=stmt.lineno, site=f"{stmt.lineno}:{i}")
            elif isinstance(stmt, ast.Assign):
                targets = [nm for t in stmt.targets for nm in _target_names(t)]
                value = stmt.value
                if isinstance(value, ast.Call):
                    edge = calls_by_line.get(value.lineno)
                    if edge:
                        g.add_edge(edge.target, out_qn, "FLOWS_TO",
                                   kind="return", via="return", origin=edge.target,
                                   line=value.lineno, site=f"{value.lineno}:ret")
                    for nm in targets:
                        tainted[nm] = edge.target if edge else in_qn
                elif isinstance(value, ast.Name) and value.id in tainted:
                    for nm in targets:
                        tainted[nm] = tainted[value.id]      # Copy
                elif isinstance(value, (ast.BinOp, ast.Subscript, ast.Call, ast.IfExp)):
                    for nm in targets:
                        tainted[nm] = in_qn                    # Transform
                else:
                    for nm in targets:
                        tainted.pop(nm, None)                  # Kill
            elif isinstance(stmt, ast.Return) and stmt.value is not None:
                for nm in _name_refs(stmt.value):
                    if nm in tainted and tainted[nm] != in_qn:
                        g.add_edge(tainted[nm], out_qn, "FLOWS_TO",
                                   kind="return", via="return", origin=tainted[nm],
                                   line=stmt.lineno, site=f"{stmt.lineno}:ret")

    # -- 工具 -------------------------------------------------------------
    @staticmethod
    def _external(g: AlgoGraph, name: str, provenance: str) -> str:
        qn = make_qn("external", name)
        g.node(qn, "external_symbol", name, written_name=name, provenance=provenance)
        return qn


def _unparse(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover
        return ""


def _annotation(node: Optional[ast.AST]) -> str:
    return _unparse(node) if node is not None else ""


def _target_names(node: ast.AST) -> List[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        return [nm for e in node.elts for nm in _target_names(e)]
    if isinstance(node, ast.Starred):
        return _target_names(node.value)
    return []


def _name_refs(node: ast.AST) -> Set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
