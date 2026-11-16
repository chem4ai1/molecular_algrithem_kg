"""由配置渲染 prompt：与 extraction.prompts.render 逐字节等价（可测试）。"""
from __future__ import annotations
from typing import Any, Dict, Optional

from . import loader
from .schema import StageSpec

DEFAULT_SLOTS = {"title": "", "paper_text": "", "code_symbols": "",
                 "rule_hints": ""}


def contract_text(spec: StageSpec) -> str:
    """按 YAML 的 target.classes + contract.fields 生成契约块。"""
    lines = ["【语义层契约 · 只抽下面这些字段，其余一律不要输出】"]
    try:
        from ..tbox_v4 import SEMANTIC_CLASSES
        from ..extraction.contracts import NON_LLM
        for cls in spec.classes:
            # 与 extraction.contracts.contract_text 一致：
            # 字段来自类定义本身，不由 contract.fields（那是输出 JSON 键）裁剪。
            allowed = [f for f, _lv, _n in SEMANTIC_CLASSES[cls][1]
                       if f not in NON_LLM.get(cls, ())]
            if allowed:
                lines.append("- " + cls + ": " + ", ".join(allowed))
    except Exception:  # noqa: BLE001
        for cls in spec.classes:
            lines.append("- " + cls + ": " + ", ".join(spec.fields))
    if spec.note:
        lines.append(spec.note)
    return "\n".join(x for x in lines if x)


def catalogs(spec: StageSpec, text: str = "") -> str:
    from ..extraction.vocab import render as _vocab
    parts = [_vocab(text, stage=spec.stage), contract_text(spec)]
    return "\n".join(x for x in parts if x)


def render(stage: str, *, title: str = "", paper_text: str = "",
           code_symbols: str = "", rule_hints: str = "") -> str:
    """配置优先；无配置时退化到内置 prompts.render。"""
    specs = loader.stages()
    if not specs or stage not in specs:
        from ..extraction.prompts import render as _legacy
        return _legacy(stage, title=title, paper_text=paper_text,
                       code_symbols=code_symbols, rule_hints=rule_hints)
    spec = specs[stage]
    cm = loader.common()
    head_tpl = cm.get("template") or ""
    if not head_tpl:
        from ..extraction.prompts import COMMON as head_tpl
    body = spec.template
    cat = catalogs(spec, paper_text)
    head = head_tpl.replace("{catalogs}", cat)
    vals: Dict[str, Any] = dict(DEFAULT_SLOTS)
    vals.update({"title": title, "paper_text": paper_text,
                 "code_symbols": code_symbols, "rule_hints": rule_hints})
    for k, v in vals.items():
        body = body.replace("{" + k + "}", str(v or "(无)"))
    return head + body


def stages() -> tuple:
    specs = loader.stages()
    if not specs:
        from ..extraction.prompts import stages as _legacy
        return _legacy()
    return tuple(s.stage for s in sorted(specs.values(), key=lambda x: x.order))
