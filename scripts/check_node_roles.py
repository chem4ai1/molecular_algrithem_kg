#!/usr/bin/env python3
"""检查每个语义层/应用层节点类型都有 role/source/phases。"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import yaml
from capfactory.semantic.tbox_v4 import SEMANTIC_CLASSES
from capfactory.applayer.tbox import APP_CLASSES

REG = ROOT / "data/node_roles.yaml"


def main():
    d = yaml.safe_load(REG.read_text(encoding="utf-8"))
    errors = []
    for layer, classes in (("semantic", set(SEMANTIC_CLASSES)),
                           ("application", set(APP_CLASSES))):
        reg = set((d.get(layer) or {}).keys())
        missing = sorted(classes - reg)
        extra = sorted(reg - classes)
        if missing:
            errors.append(f"{layer}: 未登记 {missing}")
        if extra:
            errors.append(f"{layer}: 多余登记 {extra}")
        for cls in sorted(classes & reg):
            v = d[layer][cls]
            for k in ("role", "source", "phases"):
                if not str(v.get(k) or "").strip():
                    errors.append(f"{layer}.{cls}: 缺 {k}")
    if errors:
        print("\n".join("✗ " + e for e in errors))
        return 1
    print(f"✅ 节点作用登记完整：语义层 {len(SEMANTIC_CLASSES)} / 应用层 {len(APP_CLASSES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
