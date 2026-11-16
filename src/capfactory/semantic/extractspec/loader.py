"""读取 data/extract_target 下的 YAML，带缓存与校验。

设计：文件缺失时返回 None，调用方退化到内置常量（contracts/prompts），
保证迁移期行为不变；文件存在则以文件为准。
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .schema import (RefineSpec, StageSpec, parse_refine, parse_stage,
                     slots_of)

ROOT = Path(os.environ.get("CAPFACTORY_EXTRACT_TARGET",
                           "data/extract_target"))
_CACHE: Dict[str, Any] = {"sig": None, "stages": None, "refines": None,
                          "common": None, "errors": []}


def _sig() -> Tuple:
    if not ROOT.exists():
        return ("missing",)
    out = []
    for p in sorted(ROOT.rglob("*.yaml")):
        st = p.stat()
        out.append((str(p), st.st_mtime_ns, st.st_size))
    return tuple(out)


def _yaml(path: Path) -> Dict[str, Any]:
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _validate_stage(sp: StageSpec) -> List[str]:
    errs = []
    if not sp.stage:
        errs.append("stage 为空")
    if not sp.template:
        errs.append(f"{sp.stage}: template 为空")
    builtin = {"title", "paper_text", "code_symbols", "rule_hints", "catalogs"}
    missing = [s for s in slots_of(sp.template)
               if s not in sp.slots and s not in builtin]
    if missing:
        errs.append(f"{sp.stage}: 模板占位未在 slots 声明 {missing}")
    try:
        from ..tbox_v4 import SEMANTIC_CLASSES
        from ..extraction.contracts import NON_LLM
        for cls in sp.classes:
            if cls not in SEMANTIC_CLASSES:
                errs.append(f"{sp.stage}: 未知类 {cls}")
                continue
            # contract.fields 是「输出 JSON 键」，可能是嵌套数组或关系名
            # （modules / from / to / kind），与类字段不是同一套，故不校验；
            # 真正的字段一致性由 render.contract_text 直接读类定义保证。
            _ = SEMANTIC_CLASSES[cls]
    except Exception as exc:  # noqa: BLE001
        errs.append(f"{sp.stage}: 依赖校验失败 {type(exc).__name__}")
    return errs


def _validate_refine(rf: RefineSpec) -> List[str]:
    errs = []
    if not rf.refine or not rf.cls:
        errs.append("refine/target.class 为空")
    if "{arxiv_id}" not in rf.node_id:
        errs.append(f"{rf.refine}: node_id 必须以 {{arxiv_id}} 起头保证唯一")
    missing = [s for s in slots_of(rf.template)
               if s not in ("existing", "context", "fields", "parent")]
    if missing:
        errs.append(f"{rf.refine}: 模板占位未知 {missing}")
    names = [f.name for f in rf.fields]
    if len(names) != len(set(names)):
        errs.append(f"{rf.refine}: 字段重名")
    if not rf.field_names:
        errs.append(f"{rf.refine}: fields 为空")
    if rf.merge not in ("append", "overwrite"):
        errs.append(f"{rf.refine}: merge 只能是 append/overwrite")
    return errs


def load(*, force: bool = False) -> Dict[str, Any]:
    """返回 {stages, refines, common, errors, source}。"""
    sig = _sig()
    if not force and _CACHE["sig"] == sig:
        return _CACHE
    stages: Dict[str, StageSpec] = {}
    refines: Dict[str, RefineSpec] = {}
    common: Dict[str, Any] = {}
    errors: List[str] = []
    if ROOT.exists():
        for p in sorted((ROOT / "stages").glob("*.yaml")):
            try:
                d = _yaml(p)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{p.name}: YAML 解析失败 {exc}")
                continue
            if p.name.startswith("_"):
                if "common" in d:
                    common = dict(d["common"] or {})
                continue
            sp = parse_stage(d)
            errors += _validate_stage(sp)
            stages[sp.stage] = sp
        for p in sorted((ROOT / "refine").glob("*.yaml")):
            try:
                d = _yaml(p)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{p.name}: YAML 解析失败 {exc}")
                continue
            rf = parse_refine(d)
            errors += _validate_refine(rf)
            refines[rf.refine] = rf
    _CACHE.update({"sig": sig, "stages": stages, "refines": refines,
                   "common": common, "errors": errors,
                   "source": str(ROOT) if ROOT.exists() else "(missing)"})
    return _CACHE


def stages() -> Optional[Dict[str, StageSpec]]:
    d = load()
    return d["stages"] or None


def refines() -> Optional[Dict[str, RefineSpec]]:
    d = load()
    return d["refines"] or None


def common() -> Dict[str, Any]:
    return load()["common"]


def errors() -> List[str]:
    return load()["errors"]
