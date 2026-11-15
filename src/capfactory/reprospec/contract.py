"""P0-2：ReproSpec / SAU 数据契约（GGR 蓝图 §4.2、§4.3）。

SAU（Semantic Alignment Unit）= 原子且可验证的实现声明，对齐 SA-Bench
(arXiv 2608.24252) 的概念，但**从既有图谱确定性编译**，不调 LLM。

五类 SAU 与节点来源（蓝图 §4.3）：
    method         Algorithm + AlgorithmModule
    code_grounding MODULE_IMPLEMENTED_BY → CodeFunction
    protocol       Benchmark + DataContract
    numeric        LeaderboardEntry + MetricDefinition
    ordering       AlgorithmModule.inputs/outputs 依赖闭包

所有 SAU 都带 ``source_node_ids``（语义层/应用层节点 id）与 ``check``，
因此 R6 的每条判定都可回溯到图和原文。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

SAU_KINDS: tuple = ("method", "code_grounding", "protocol", "numeric", "ordering")

# 编译期默认预算（蓝图 §5 R0 / R5）
DEFAULT_BUDGETS: Dict[str, Any] = {
    "effort": "dry",
    "debug_tries_max": 20,          # AutoReproduce 实测 5–8 次收敛
    "engineer_rounds_max": 2,       # SciForge S2 ladder
    "deviation_tolerance": 0.05,    # gates.reproduction_close 的 5%
    "allow_execution": False,       # dry 模式；R5 真跑需显式切 lite/full
}


@dataclass
class SAU:
    """一条原子可验证的实现声明。"""
    id: str
    kind: str
    statement: str
    source_node_ids: List[str] = field(default_factory=list)
    evidence_ids: List[str] = field(default_factory=list)
    check: Dict[str, Any] = field(default_factory=dict)
    required: bool = True
    provenance: str = "derived"      # extracted | derived | inferred
    relation_hint: str = ""          # 编译时依据的规范关系名
    # ---- 层次化 rubric 树（任务层派生，不参与 spec_hash）----
    parent_id: str = ""              # 挂载到的图节点 id
    path: str = ""                   # paper/algorithm/module 可读路径
    depth: int = 0                   # 0=根下，越大越细
    weight: float = 1.0              # 树加权聚合用

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def stable_key(self) -> Dict[str, Any]:
        """参与 spec_hash 的稳定字段（不含运行期判定结果）。"""
        return {"id": self.id, "kind": self.kind, "statement": self.statement,
                "source_node_ids": sorted(self.source_node_ids),
                "check": self.check, "required": self.required}


@dataclass
class ReproSpec:
    """一篇论文的复现规格；由 ``compile_reprospec`` 从图确定性编译。"""
    paper_id: str
    arxiv_id: str
    sau: List[SAU] = field(default_factory=list)
    method_lock: Dict[str, Any] = field(default_factory=dict)
    data_contract: List[Dict[str, Any]] = field(default_factory=list)
    metric_plan: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    lineage: List[Dict[str, Any]] = field(default_factory=list)
    code_plan: Dict[str, Any] = field(default_factory=dict)
    budgets: Dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_BUDGETS))
    spec_hash: str = ""
    graph_path: str = ""
    graph_stats: Dict[str, int] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    gaps: List[Dict[str, str]] = field(default_factory=list)

    # ---- 派生视图 ---------------------------------------------------------
    def by_kind(self, kind: str) -> List[SAU]:
        return [s for s in self.sau if s.kind == kind]

    def counts(self) -> Dict[str, int]:
        return {k: len(self.by_kind(k)) for k in SAU_KINDS}

    def required_ids(self) -> List[str]:
        return [s.id for s in self.sau if s.required]

    # ---- 序列化 -----------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["sau_count"] = len(self.sau)
        d["sau_counts"] = self.counts()
        return d

    def compute_hash(self) -> str:
        payload = [s.stable_key() for s in sorted(self.sau, key=lambda x: x.id)]
        blob = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                          default=str)
        return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def save(self, out_dir: str | Path) -> Dict[str, str]:
        """写 ``REPRO_SPEC.json`` + ``SAU_LIST.json``；返回路径。"""
        p = Path(out_dir)
        p.mkdir(parents=True, exist_ok=True)
        spec_file = p / "REPRO_SPEC.json"
        sau_file = p / "SAU_LIST.json"
        spec_file.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8")
        sau_file.write_text(
            json.dumps({"paper_id": self.paper_id, "arxiv_id": self.arxiv_id,
                        "spec_hash": self.spec_hash,
                        "sau": [s.to_dict() for s in self.sau]},
                       ensure_ascii=False, indent=2),
            encoding="utf-8")
        return {"REPRO_SPEC.json": str(spec_file), "SAU_LIST.json": str(sau_file)}

    @classmethod
    def load(cls, path: str | Path) -> "ReproSpec":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        d.pop("sau_count", None)
        d.pop("sau_counts", None)
        sau = [SAU(**x) for x in (d.pop("sau", []) or [])]
        return cls(sau=sau, **d)

    @classmethod
    def empty(cls, paper_id: str, arxiv_id: str,
              reason: str = "") -> "ReproSpec":
        s = cls(paper_id=paper_id, arxiv_id=arxiv_id)
        if reason:
            s.gaps.append({"phase": "R0", "reason": reason})
        s.spec_hash = s.compute_hash()
        return s
