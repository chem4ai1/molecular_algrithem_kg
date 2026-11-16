"""动态类注册中心（S0，v2 扩到 10+ 类）。

类注册与实例写入分离：类非 active 时其实例只能停在 proposed。
单一写入者：只有本模块写 registry.json / PROMOTION_LOG.jsonl。
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, FrozenSet, List

from . import config, util

REGISTRY_FILE = config.DYNAMIC_TBOX / "registry.json"
PROMOTION_LOG = config.DYNAMIC_TBOX / "PROMOTION_LOG.jsonl"
SNAPSHOT_DIR = config.DYNAMIC_TBOX / "snapshots"

DEFAULT_CLASSES: Dict[str, Dict[str, Any]] = {
    "DomainProfile": {"parent_class": "ResearchQuestion", "producer_stage": "1b",
                      "fields": ["evidence_type", "reasoning_paradigm", "learning_confidence"]},
    "ResearchGap": {"parent_class": "ResearchQuestion", "producer_stage": "4broad",
                    "fields": ["gap_id", "gap_type", "statement", "evidence_ids"]},
    "IdeaNode": {"parent_class": "Algorithm", "producer_stage": "2",
                 "fields": ["insight", "novelty_delta", "falsifiable_claim", "gap_anchor"]},
    "GateVerdict": {"parent_class": "EvaluationResult", "producer_stage": "*",
                    "fields": ["stage", "state", "reason_code"]},
    "KnowledgeSignal": {"parent_class": "Evidence", "producer_stage": "*",
                        "fields": ["signal_id", "kind", "value", "count", "status"]},
    "SignalCluster": {"parent_class": "Evidence", "producer_stage": "*",
                      "fields": ["cluster_id", "members", "frequency"]},
    "MiningCoverage": {"parent_class": "Evidence", "producer_stage": "*",
                       "fields": ["coverage_ratio", "fields", "gap_candidates"]},
    "ExplorationFrontier": {"parent_class": "ResearchQuestion", "producer_stage": "*",
                            "fields": ["direction", "status", "source"]},
    "ChoicePoint": {"parent_class": "EvaluationResult", "producer_stage": "*",
                    "fields": ["choice_id", "stage", "mode", "options", "status"]},
    "HumanDecision": {"parent_class": "Evidence", "producer_stage": "*",
                      "fields": ["decision_id", "approver", "chosen_option_id", "ts"]},
    "HumanHypothesis": {"parent_class": "IdeaNode", "producer_stage": "2",
                        "fields": ["statement", "falsifiable_claim", "gap_anchor", "origin"]},
    "MethodAlternative": {"parent_class": "IdeaNode", "producer_stage": "5",
                          "fields": ["name", "rationale", "origin"]},
    "HumanIntent": {"parent_class": "Evidence", "producer_stage": "*",
                    "fields": ["statement", "scope"]},
    "HumanOverride": {"parent_class": "Evidence", "producer_stage": "*",
                      "fields": ["target_node", "field", "approver"]},
}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_registry(*, out_dir: str | Path | None = None) -> Dict[str, Any]:
    p = Path(out_dir) / "registry.json" if out_dir else REGISTRY_FILE
    if p.exists():
        try:
            return __import__("json").loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return {"schema_version": "1.0", "classes": {}, "version": config.DYNAMIC_TBOX_VERSION}


def _save(d: Dict[str, Any], *, out_dir: str | Path | None = None) -> None:
    p = Path(out_dir) / "registry.json" if out_dir else REGISTRY_FILE
    util.atomic_write(p, d)


def _log(row: Dict[str, Any], *, out_dir: str | Path | None = None) -> None:
    p = Path(out_dir) / "PROMOTION_LOG.jsonl" if out_dir else PROMOTION_LOG
    util.append_jsonl(p, row)


def seed_defaults(*, out_dir=None, approver: str = "system:seed") -> Dict[str, Any]:
    """幂等注册 v2 的 14 个动态类。"""
    n = 0
    for name, spec in DEFAULT_CLASSES.items():
        r = register_class({"name": name, **spec}, approver=approver,
                           out_dir=out_dir)
        n += int(bool(r.get("ok")))
    return {"ok": True, "n_registered": n, "total": len(DEFAULT_CLASSES)}


@util.with_lock
def register_class(spec: Dict[str, Any], *, approver: str,
                   out_dir: str | Path | None = None) -> Dict[str, Any]:
    from .tbox import PAPERAPP_CLASS_VOCAB
    name = str(spec.get("name") or "").strip()
    if name not in PAPERAPP_CLASS_VOCAB:
        return {"ok": False, "action": "reject", "reason_code": "class_not_in_vocab"}
    d = load_registry(out_dir=out_dir)
    classes = d.setdefault("classes", {})
    if name in classes and classes[name].get("status") == "active":
        return {"ok": False, "action": "noop", "reason_code": "already_active"}
    idx = len(classes) + 1
    item = {
        "registration_id": f"dcls:{idx:04d}", "name": name,
        "parent_class": spec.get("parent_class", "Evidence"),
        "layer": "application", "task": config.TASK,
        "producer_stage": spec.get("producer_stage", "*"),
        "producers": spec.get("producers", []), "consumers": spec.get("consumers", []),
        "fields": list(spec.get("fields", [])),
        "relation_bindings": list(spec.get("relation_bindings", ["DERIVED_FROM"])),
        "id_template": f"app{name.lower()}:<arxiv>:<slug>",
        "promotion_rule": spec.get("promotion_rule", "rule:default"),
        "status": "active", "tbox_version": d.get("version", config.DYNAMIC_TBOX_VERSION),
        "first_seen": _now(), "valid_from": _now(), "valid_to": None,
        "use_count": 0, "last_used": None, "source_runs": [],
        "evidence_ids": list(spec.get("evidence_ids", [])), "supersedes": "",
        "approver": approver,
    }
    classes[name] = item
    d["updated_at"] = _now()
    _save(d, out_dir=out_dir)
    _log({"ts": _now(), "proposal_id": f"class:{name}", "from": "proposed",
          "to": "active", "rule": "seed_or_human", "approver": approver,
          "run_id": "", "registry_version": d.get("version"), "canonical_id": name},
         out_dir=out_dir)
    return {"ok": True, "action": "registered", "reason_code": "ok",
            "registration_id": item["registration_id"], "files": ["registry.json"]}


@util.with_lock
def deprecate_class(name: str, *, reason: str,
                    out_dir: str | Path | None = None) -> Dict[str, Any]:
    d = load_registry(out_dir=out_dir)
    item = d.get("classes", {}).get(name)
    if not item:
        return {"ok": False, "action": "noop", "reason_code": "class_not_found"}
    item["status"] = "deprecated"
    item["valid_to"] = _now()
    item["deprecated_reason"] = reason
    _save(d, out_dir=out_dir)
    _log({"ts": _now(), "proposal_id": f"class:{name}", "from": "active",
          "to": "deprecated", "rule": reason, "approver": "system",
          "run_id": "", "registry_version": d.get("version"), "canonical_id": name},
         out_dir=out_dir)
    return {"ok": True, "action": "deprecated", "reason_code": "ok"}


def active_classes(task: str = "generation", *, out_dir=None) -> FrozenSet[str]:
    d = load_registry(out_dir=out_dir)
    return frozenset(k for k, v in d.get("classes", {}).items()
                     if v.get("status") == "active" and v.get("task") == task)


def validate_dynamic_tbox(*, out_dir=None) -> List[str]:
    from .tbox import PAPERAPP_CLASS_VOCAB, PAPERAPP_RELATION_VOCAB
    d = load_registry(out_dir=out_dir)
    out: List[str] = []
    for name, item in d.get("classes", {}).items():
        if name not in PAPERAPP_CLASS_VOCAB:
            out.append(f"unknown_class:{name}")
        if not item.get("fields"):
            out.append(f"no_fields:{name}")
        for r in item.get("relation_bindings", []):
            if r not in PAPERAPP_RELATION_VOCAB:
                out.append(f"unknown_relation:{name}:{r}")
    return out


def bump_usage(names, run_id: str, *, out_dir=None) -> Dict[str, Any]:
    @util.with_lock
    def _inner():
        d = load_registry(out_dir=out_dir)
        for name in names:
            item = d.get("classes", {}).get(name)
            if not item:
                continue
            item["use_count"] = int(item.get("use_count", 0)) + 1
            item["last_used"] = _now()
            runs = item.setdefault("source_runs", [])
            if run_id not in runs:
                runs.append(run_id)
        _save(d, out_dir=out_dir)
    _inner()
    return {"ok": True, "action": "bump_usage", "reason_code": "ok"}


def snapshot(*, out_dir=None) -> str:
    d = load_registry(out_dir=out_dir)
    base = Path(out_dir) / "snapshots" if out_dir else SNAPSHOT_DIR
    p = base / (d.get("version", config.DYNAMIC_TBOX_VERSION) + ".json")
    util.atomic_write(p, d)
    return str(p)
