#!/usr/bin/env python3
"""字段同步自检：YAML 声明 → validator 归一化 → apply 写回 → tbox 定义。

四份清单任一漏掉，字段就静默丢失（我踩过两次：E1 加 5 字段、E2 加 3 字段）。
用法：python3 scripts/check_field_sync.py [--stage E1_paper]
"""
from __future__ import annotations
import argparse, ast, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capfactory.semantic.extractspec import loader
from capfactory.semantic.tbox_v4 import SEMANTIC_CLASSES

VALIDATOR = ROOT / "src/capfactory/semantic/extraction/validator.py"
APPLY = ROOT / "src/capfactory/semantic/apply.py"


def _func_keys(path: Path, func: str) -> set:
    """AST：取函数内 out = {...} 的键 + out["x"]= 的赋值键。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    keys = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign):
                    for t in sub.targets:
                        # out = {...}
                        if isinstance(t, ast.Name) and isinstance(sub.value, ast.Dict):
                            for k in sub.value.keys:
                                if isinstance(k, ast.Constant):
                                    keys.add(str(k.value))
                        # out["x"] = ...
                        if isinstance(t, ast.Subscript):
                            sl = t.slice
                            if isinstance(sl, ast.Constant):
                                keys.add(str(sl.value))
    return keys


def _apply_whitelist(path: Path) -> set:
    """AST：取 for k in ("a","b",...) 的字符串常量。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Tuple):
            vals = [e.value for e in node.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            if len(vals) >= 6:          # 只认长白名单
                out |= set(vals)
    return out


# 已知例外：这些字段不走「apply 属性白名单」的正常路径
EXEMPT = {
    "name": "作为节点 label + name 属性显式处理",
    "modules": "走 AlgorithmModule 节点创建，不写进 alg.attrs",
    "evidence": "aux_fields，prompt 专用不落图",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="E1_paper")
    a = ap.parse_args()
    cls = {"E1_paper": "Paper", "E2_algorithm": "Algorithm",
           "E3_benchmark": "Benchmark"}.get(a.stage, "Paper")
    sp = (loader.load(force=True)["stages"] or {}).get(a.stage)
    if sp is None:
        print(f"✗ 未找到 stage {a.stage}")
        return 1
    yaml_f = set(sp.fields)                       # LLM 要抽的
    val_f = _func_keys(VALIDATOR, "_" + a.stage.split("_")[0].lower())   # _e1/_e2/_e3
    apply_f = _apply_whitelist(APPLY)
    tbox_f = {f for f, _, _ in SEMANTIC_CLASSES[cls][1]}

    print(f"stage={a.stage}  class={cls}")
    print(f"  ① YAML all_fields      : {len(yaml_f)}")
    print(f"  ② validator 归一化输出  : {len(val_f)}")
    print(f"  ③ apply 写回白名单      : {len(apply_f)}")
    print(f"  ④ tbox 类字段定义       : {len(tbox_f)}")

    bad = 0
    miss1 = sorted(yaml_f - val_f)
    print(f"\n  ①→② YAML 声明但 validator 不输出（必丢）: {miss1 or '无 ✅'}")
    bad += len(miss1)
    miss2_raw = sorted(val_f - apply_f)
    miss2 = [f for f in miss2_raw if f not in EXEMPT]
    exempt_hit = [f for f in miss2_raw if f in EXEMPT]
    print(f"  ②→③ validator 有但 apply 不写回（必丢）: {miss2 or '无 ✅'}")
    if exempt_hit:
        print(f"       （已知例外: {', '.join(f'{f}={EXEMPT[f]}' for f in exempt_hit)}）")
    bad += len(miss2)
    # apply 是跨类共享的大白名单，只能检查「该类字段是否被 apply 覆盖」
    miss3 = sorted((tbox_f & (yaml_f | val_f)) - apply_f - set(EXEMPT))
    print(f"  ③→④ 该类字面字段未被 apply 覆盖（会丢）: {miss3 or '无 ✅'}")
    bad += len(miss3)

    print(f"\n结论：{'✗ 发现 ' + str(bad) + ' 处不一致' if bad else '✅ 四份清单一致'}")
    return 0 if bad == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
