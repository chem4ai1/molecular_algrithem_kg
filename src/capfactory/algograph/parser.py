"""L1 结构层：复刻 PKG 的 ``func_name → implementation → code_block`` 拆解.

对照 ``ref/ProgrammingKnowledgeGraph-main/src/core/function_analyzer.py``，
本实现修正其 5 个缺陷：

1. 用**递归 AST 访问**而非 ``ast.walk`` 的 BFS 顺序（后者会让父子判定错乱）；
2. 用 ``end_lineno`` / ``col_offset`` 而非"取起始行缩进"；
3. 补齐 ``else/elif/except/finally/async_for/async_with/try_star/match/case`` 块类型；
4. 无块函数不再 ``[0]`` 越界；
5. **新增 PKG 缺失的 ``function_id`` + ``PROJECTS_TO`` / ``IN_FUNCTION`` 反向投影**
   与显式 DFS 环检测，使"任何细粒度块都能投影回父函数"成为可查询事实。

块的 ``content`` 沿用 PKG 的关键设计：带缩进的**源码行切片且包含嵌套子块**，
因此子块文本必为父块文本的子串，可按行差集做上下文剪枝。
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .schema import stable_hash
from .store import AlgoGraph

_STMT_KINDS = (
    (ast.If, "if"), (ast.For, "for"), (ast.AsyncFor, "async_for"),
    (ast.While, "while"), (ast.Try, "try"), (ast.With, "with"),
    (ast.AsyncWith, "async_with"), (ast.FunctionDef, "function"),
    (ast.AsyncFunctionDef, "function"), (ast.ClassDef, "class"),
)
try:
    _STMT_KINDS += ((ast.TryStar, "try_star"), (ast.Match, "match"))  # type: ignore[attr-defined]
except AttributeError:  # pragma: no cover - Python < 3.10 / 3.11
    pass


def _block_kind(stmt: ast.AST) -> str:
    for cls, kind in _STMT_KINDS:
        if isinstance(stmt, cls):
            return kind
    return ""


def _body_of(stmt: ast.AST) -> List[ast.stmt]:
    body = getattr(stmt, "body", None)
    return list(body) if isinstance(body, list) else []


def _branches(stmt: ast.AST) -> List[Tuple[str, List[ast.stmt]]]:
    """返回 (分支块类型, 分支内语句列表)，用于 else / except / finally / case。"""
    out: List[Tuple[str, List[ast.stmt]]] = []
    orelse = getattr(stmt, "orelse", None) or []
    if orelse:
        # 单个 elif 在 AST 里是 If.orelse=[If]，用 elif 标注更贴近源码语义
        kind = "elif" if isinstance(stmt, ast.If) and len(orelse) == 1 and isinstance(orelse[0], ast.If) else "else"
        out.append((kind, list(orelse)))
    for handler in getattr(stmt, "handlers", None) or []:
        out.append(("except", list(getattr(handler, "body", []) or [])))
    finalbody = getattr(stmt, "finalbody", None) or []
    if finalbody:
        out.append(("finally", list(finalbody)))
    for case in getattr(stmt, "cases", None) or []:
        out.append(("case", list(getattr(case, "body", []) or [])))
    return out


def _line_span(stmts: Sequence[ast.AST]) -> Tuple[int, int, int]:
    starts = [getattr(s, "lineno", 0) for s in stmts if getattr(s, "lineno", 0)]
    ends = [getattr(s, "end_lineno", 0) or getattr(s, "lineno", 0)
            for s in stmts if getattr(s, "lineno", 0)]
    if not starts:
        return (0, 0, 0)
    return (min(starts), max(ends), min(getattr(s, "col_offset", 0) for s in stmts))


def _slice(lines: Sequence[str], start: int, end: int) -> str:
    if start <= 0 or end < start:
        return ""
    return "\n".join(lines[start - 1:min(end, len(lines))])


def _annotation(node: Optional[ast.AST]) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover
        return ""


class CodeGraphBuilder:
    """把 Python 源码拆成 PKG 三层结构图。默认函数级，块级可关闭。"""

    def __init__(self, include_blocks: bool = True):
        self.include_blocks = include_blocks

    # -- 主入口 -----------------------------------------------------------
    def build(self, source: str, module_qn: str, *, path: str = "",
              graph: Optional[AlgoGraph] = None) -> AlgoGraph:
        """构建（或增量追加）一个模块的结构子图。不执行被分析的代码。"""
        g = graph or AlgoGraph()
        source = source or ""
        tree = ast.parse(source)
        lines = source.splitlines()
        module_id = f"{module_qn}#module"
        g.node(module_id, "module", module_qn, path=path,
               docstring=ast.get_docstring(tree) or "",
               start_line=1, end_line=len(lines),
               source_hash=stable_hash(source))
        self._scope(tree, module_qn, module_id, "", lines, g)
        return g

    def build_file(self, path: str | Path, module_qn: str = "",
                   graph: Optional[AlgoGraph] = None) -> AlgoGraph:
        p = Path(path)
        return self.build(p.read_text(encoding="utf-8", errors="replace"),
                          module_qn or p.stem, path=str(p), graph=graph)

    def build_files(self, files: Sequence[Tuple[str, str]],
                    graph: Optional[AlgoGraph] = None) -> AlgoGraph:
        """``files = [(path, module_qn), ...]``；跨文件共享一张图。"""
        g = graph or AlgoGraph()
        for path, qn in files:
            try:
                self.build_file(path, qn, g)
            except (SyntaxError, OSError) as exc:
                g.meta.setdefault("parse_errors", []).append(f"{path}: {exc}")
        return g

    # -- 作用域遍历 -------------------------------------------------------
    def _scope(self, node: ast.AST, module_qn: str, owner_qn: str,
               prefix: str, lines: Sequence[str], g: AlgoGraph) -> None:
        for stmt in _body_of(node):
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._function(stmt, module_qn, owner_qn, prefix, lines, g)
            elif isinstance(stmt, ast.ClassDef):
                qual = prefix + stmt.name
                cqn = f"{module_qn}::{qual}#class"
                g.node(cqn, "class_unit", qual,
                       bases=[_annotation(b) for b in stmt.bases],
                       decorators=[_annotation(d) for d in stmt.decorator_list],
                       start_line=stmt.lineno, end_line=getattr(stmt, "end_lineno", stmt.lineno),
                       docstring=ast.get_docstring(stmt) or "")
                g.add_edge(owner_qn, cqn, "DECLARES", line=stmt.lineno)
                self._scope(stmt, module_qn, cqn, qual + ".", lines, g)

    def _function(self, fn: ast.AST, module_qn: str, owner_qn: str,
                  prefix: str, lines: Sequence[str], g: AlgoGraph) -> None:
        qual = prefix + getattr(fn, "name", "anonymous")
        func_qn = f"{module_qn}::{qual}#name"
        impl_qn = f"{func_qn}#impl"
        decorators = list(getattr(fn, "decorator_list", []) or [])
        start = min([d.lineno for d in decorators if getattr(d, "lineno", 0)] or [fn.lineno])
        end = int(getattr(fn, "end_lineno", 0) or fn.lineno)
        args = getattr(fn, "args", None)
        params: List[Dict[str, Any]] = []
        if args:
            positional = list(getattr(args, "posonlyargs", []) or []) + list(getattr(args, "args", []) or [])
            defaults = list(getattr(args, "defaults", []) or [])
            pad = len(positional) - len(defaults)
            for i, a in enumerate(positional):
                params.append({"name": a.arg, "index": i,
                               "annotation": _annotation(a.annotation),
                               "has_default": i >= pad})
            if getattr(args, "vararg", None):
                params.append({"name": args.vararg.arg, "index": len(params),
                               "annotation": _annotation(args.vararg.annotation),
                               "is_variadic": True, "has_default": False})
            for a in (getattr(args, "kwonlyargs", []) or []):
                params.append({"name": a.arg, "index": len(params),
                               "annotation": _annotation(a.annotation),
                               "is_kwonly": True, "has_default": True})
            if getattr(args, "kwarg", None):
                params.append({"name": args.kwarg.arg, "index": len(params),
                               "annotation": _annotation(args.kwarg.annotation),
                               "is_variadic": True, "has_default": False})

        g.node(func_qn, "func_name", qual,
               name=getattr(fn, "name", ""), qualified_name=f"{module_qn}.{qual}",
               docstring=ast.get_docstring(fn) or "", params=params,
               return_annotation=_annotation(getattr(fn, "returns", None)),
               decorators=[_annotation(d) for d in decorators],
               start_line=start, end_line=end, is_async=isinstance(fn, ast.AsyncFunctionDef))
        g.node(impl_qn, "implementation", f"{qual}() implementation",
               content=_slice(lines, start, end), start_line=start, end_line=end,
               hash=stable_hash(_slice(lines, start, end)), function_id=func_qn)
        g.add_edge(owner_qn, func_qn, "DECLARES", line=fn.lineno)
        g.add_edge(func_qn, impl_qn, "HAS_IMPL")

        if self.include_blocks:
            for stmt in _body_of(fn):
                self._block(stmt, impl_qn, impl_qn, func_qn, lines, g, depth=0)
        # 嵌套函数（含闭包）作为独立单元，qualname 带父作用域前缀
        self._scope(fn, module_qn, func_qn, qual + ".", lines, g)

    def _block(self, stmt: ast.stmt, parent_qn: str, impl_qn: str, func_qn: str,
               lines: Sequence[str], g: AlgoGraph, depth: int) -> None:
        kind = _block_kind(stmt)
        if not kind:
            return
        start = int(getattr(stmt, "lineno", 0) or 0)
        end = int(getattr(stmt, "end_lineno", 0) or start)
        col = int(getattr(stmt, "col_offset", 0) or 0)
        if not start or end < start:
            return
        bqn = f"{func_qn}#block@{start}:{col}"
        content = _slice(lines, start, end)
        g.node(bqn, "code_block", f"{kind}@{start}",
               content=content, block_kind=kind, start_line=start, end_line=end,
               col=col, depth=depth, function_id=func_qn,
               parent_block_id="" if parent_qn == impl_qn else parent_qn,
               header=_slice(lines, start, start))
        g.add_edge(parent_qn, bqn,
                   "HAS_BLOCK" if parent_qn == impl_qn else "NESTS")
        # PKG 缺失的反向投影：任意块 O(1) 回到父函数
        g.add_edge(bqn, impl_qn, "PROJECTS_TO")
        g.add_edge(bqn, func_qn, "IN_FUNCTION")

        for child in _body_of(stmt):
            self._block(child, bqn, impl_qn, func_qn, lines, g, depth + 1)
        for branch_kind, branch_stmts in _branches(stmt):
            b_start, b_end, b_col = _line_span(branch_stmts)
            if not b_start or b_end < b_start:
                continue
            br_qn = f"{func_qn}#branch@{branch_kind}@{b_start}:{b_col}"
            br_content = _slice(lines, b_start, b_end)
            g.node(br_qn, "code_block", f"{branch_kind}@{b_start}",
                   content=br_content, block_kind=branch_kind,
                   start_line=b_start, end_line=b_end, col=b_col,
                   depth=depth + 1, function_id=func_qn, parent_block_id=bqn,
                   header=f"{branch_kind}:")
            g.add_edge(bqn, br_qn, "NESTS")
            g.add_edge(br_qn, impl_qn, "PROJECTS_TO")
            g.add_edge(br_qn, func_qn, "IN_FUNCTION")
            for child in branch_stmts:
                self._block(child, br_qn, impl_qn, func_qn, lines, g, depth + 2)
