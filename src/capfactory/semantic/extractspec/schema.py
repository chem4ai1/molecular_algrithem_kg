"""抽取配置的数据结构与校验（不依赖 pydantic）。"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_SLOT = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def slots_of(template: str) -> List[str]:
    return sorted(set(_SLOT.findall(template or "")))


@dataclass
class FieldSpec:
    name: str
    required: bool = False
    type: str = "str"          # str | list | int | float | bool
    enum: List[str] = field(default_factory=list)
    max_items: Optional[int] = None
    max_chars: Optional[int] = None


@dataclass
class StageSpec:
    stage: str
    order: int = 99
    enabled: bool = True
    classes: List[str] = field(default_factory=list)
    wrapper: Optional[str] = None
    target_desc: str = ""
    required: List[str] = field(default_factory=list)
    optional: List[str] = field(default_factory=list)
    note: str = ""
    all_fields: List[str] = field(default_factory=list)
    aux_fields: List[str] = field(default_factory=list)   # prompt 专用，不落图
    section_slice: str = "paper"
    slots: List[str] = field(default_factory=list)
    template: str = ""
    guards: Dict[str, Any] = field(default_factory=dict)

    @property
    def fields(self) -> List[str]:
        if self.all_fields:
            return list(dict.fromkeys(self.all_fields))
        return list(dict.fromkeys(self.required + self.optional))


@dataclass
class RefineSpec:
    refine: str
    order: int = 99
    enabled: bool = True
    cls: str = ""
    node_id: str = ""          # 支持 {arxiv_id} {n} {kind} {parent}
    relation: str = ""
    parent_class: str = ""
    section_hints: List[str] = field(default_factory=list)
    signal_words: List[str] = field(default_factory=list)
    locate: Dict[str, Any] = field(default_factory=dict)
    fields: List[FieldSpec] = field(default_factory=list)
    template: str = ""
    merge: str = "append"

    @property
    def field_names(self) -> List[str]:
        return [f.name for f in self.fields]


def parse_stage(d: Dict[str, Any]) -> StageSpec:
    t = d.get("target") or {}
    c = d.get("contract") or {}
    return StageSpec(
        stage=str(d.get("stage") or ""), order=int(d.get("order") or 99),
        enabled=bool(d.get("enabled", True)),
        classes=list(t.get("classes") or []), wrapper=t.get("wrapper"),
        target_desc=str(t.get("target_desc") or ""),
        required=list(c.get("required") or []),
        optional=list(c.get("optional") or []),
        note=str(c.get("note") or ""),
        all_fields=list(c.get("all_fields") or []),
        aux_fields=list(c.get("aux_fields") or []),
        section_slice=str(d.get("section_slice") or "paper"),
        slots=list(d.get("slots") or []),
        template=str(d.get("template") or ""),
        guards=dict(d.get("guards") or {}))


def parse_refine(d: Dict[str, Any]) -> RefineSpec:
    t = d.get("target") or {}
    fs = []
    for f in d.get("fields") or []:
        fs.append(FieldSpec(name=str(f.get("name") or ""),
                            required=bool(f.get("required", False)),
                            type=str(f.get("type") or "str"),
                            enum=list(f.get("enum") or []),
                            max_items=f.get("max_items"),
                            max_chars=f.get("max_chars")))
    return RefineSpec(
        refine=str(d.get("refine") or ""), order=int(d.get("order") or 99),
        enabled=bool(d.get("enabled", True)), cls=str(t.get("class") or ""),
        node_id=str(t.get("node_id") or ""), relation=str(t.get("relation") or ""),
        parent_class=str(t.get("parent_class") or ""),
        section_hints=list(d.get("section_hints") or []),
        signal_words=list(d.get("signal_words") or []),
        locate=dict(d.get("locate") or {}), fields=fs,
        template=str(d.get("template") or ""),
        merge=str(d.get("merge") or "append"))
