"""指标可比性键：从「name|dataset|split|protocol」升级为 15 维契约.

报告 CQ3：两个成功率是否在**相同输入条件、数据集版本、采样预算、top-k 和阈值**下产生？
CQ4：命中率除以提名数还是入测数？ CQ5：IC50 是否有相同底物/pH/物种/构建体/重复数？
§3 表格进一步指出同名 `success` 可能阈值/分母/预算不同，禁止横排。

原 ``domain.bio_schema.MetricProfile.comparable_key()`` 只有 5 段，无法回答这些问题。
本模块把可比性键扩展为 15 维，并给出「哪些维度不同导致不可比」的可解释差异。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Mapping, Sequence

# 硬阻断：这些维度不同，两个观测绝不可直接比大小
BLOCKING = (
    "metric", "dataset_id", "dataset_version", "split_type", "input_condition",
    "sample_budget", "top_k", "threshold", "stage", "assay_id", "endpoint_id",
    "condition_hash", "direction", "unit",
)
# 软警示：被测对象/靶标不同，数值可并列展示但不可当作同一总体
ADVISORY = ("subject", "target")


def _norm(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return str(value).strip().lower()


def condition_hash(condition: Mapping[str, Any] | None) -> str:
    """把 ExperimentalCondition 规范化成稳定 hash（pH/底物/剂量/物种/构建体…）。"""
    if not condition:
        return ""
    keys = ("pH", "substrate", "system", "dose", "time", "duration", "frequency",
            "species", "construct", "nBiological", "n_biological", "threshold",
            "comparator", "processing", "temperature")
    picked = {k: _norm(condition.get(k)) for k in keys
              if condition.get(k) not in (None, "", [])}
    if not picked:
        return ""
    raw = json.dumps(picked, ensure_ascii=False, sort_keys=True)
    return hashlib.blake2b(raw.encode("utf-8"), digest_size=8).hexdigest()


@dataclass(frozen=True)
class ComparabilityKey:
    """一次观测的完整可比性上下文。"""

    metric: str = ""
    dataset_id: str = ""
    dataset_version: str = ""
    split_type: str = ""
    input_condition: str = ""
    sample_budget: str = ""
    top_k: str = ""
    threshold: str = ""
    stage: str = ""
    assay_id: str = ""
    endpoint_id: str = ""
    condition_hash: str = ""
    subject: str = ""
    target: str = ""
    direction: str = "higher"
    unit: str = ""

    def key(self) -> str:
        return "|".join(_norm(getattr(self, f)) for f in self.fields())

    def blocking_key(self) -> str:
        """只含 13 个阻断维度：用于**榜单分组**。

        ``subject``（被测方法/对象）与 ``target`` 是「条目身份」而非「可比条件」，
        把它们放进分组键会让每个方法各自成组，SOTA 永远不成立。
        """
        return "|".join(_norm(getattr(self, f)) for f in BLOCKING)

    @staticmethod
    def fields() -> Sequence[str]:
        return ("metric", "dataset_id", "dataset_version", "split_type",
                "input_condition", "sample_budget", "top_k", "threshold", "stage",
                "assay_id", "endpoint_id", "condition_hash", "direction",
                "unit", "subject", "target")

    def diff(self, other: "ComparabilityKey") -> List[Dict[str, Any]]:
        out = []
        for f in self.fields():
            a, b = _norm(getattr(self, f)), _norm(getattr(other, f))
            if a != b:
                out.append({"dimension": f, "a": a, "b": b,
                            "severity": "blocking" if f in BLOCKING else "advisory"})
        return out

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def comparability_key(observation: Any) -> ComparabilityKey:
    """从 ``Concept`` / ``MetricObservation-like dict`` / ``MetricProfile`` 构造键。"""
    if hasattr(observation, "attrs"):
        a: Dict[str, Any] = dict(observation.attrs)
        a.setdefault("metric", observation.label)
    elif hasattr(observation, "comparable_key"):     # domain.MetricProfile
        a = {"metric": getattr(observation, "name", ""),
             "dataset_id": getattr(observation, "dataset", ""),
             "split_type": getattr(observation, "split", ""),
             "direction": getattr(observation, "direction", "higher"),
             "unit": getattr(observation, "unit", ""),
             "protocol": getattr(observation, "protocol", "")}
    elif isinstance(observation, Mapping):
        a = dict(observation)
    else:
        a = {}
    cond = a.get("condition") or a.get("experimental_condition") or {}
    if not isinstance(cond, Mapping):
        cond = {}
    return ComparabilityKey(
        metric=_norm(a.get("metric") or a.get("metric_name") or a.get("name")),
        dataset_id=_norm(a.get("dataset_id") or a.get("dataset")),
        dataset_version=_norm(a.get("dataset_version") or a.get("version")),
        split_type=_norm(a.get("split_type") or a.get("split") or a.get("protocol")),
        input_condition=_norm(a.get("input_condition") or a.get("inputCondition")),
        sample_budget=_norm(a.get("sample_budget") or a.get("sampleBudget")),
        top_k=_norm(a.get("top_k") or a.get("topK")),
        threshold=_norm(a.get("threshold")),
        stage=_norm(a.get("stage")),
        assay_id=_norm(a.get("assay_id") or a.get("assay")),
        endpoint_id=_norm(a.get("endpoint_id") or a.get("endpoint")),
        condition_hash=a.get("condition_hash") or condition_hash(cond),
        subject=_norm(a.get("subject")),
        target=_norm(a.get("target")),
        direction=_norm(a.get("direction") or "higher"),
        unit=_norm(a.get("unit") or a.get("unit_scale")),
    )


def compare_observations(a: Any, b: Any) -> Dict[str, Any]:
    """判定两个观测能否直接比较，并给出阻断原因（用于禁止错误排行榜）。"""
    ka, kb = comparability_key(a), comparability_key(b)
    diffs = ka.diff(kb)
    blocking = [d for d in diffs if d["severity"] == "blocking"]
    advisory = [d for d in diffs if d["severity"] == "advisory"]
    comparable = not blocking
    return {
        "comparable": comparable,
        "key_a": ka.key(), "key_b": kb.key(),
        "blocking_differences": blocking,
        "advisory_differences": advisory,
        "verdict": ("可直接比较" if comparable else
                    f"不可直接比较：{len(blocking)} 个硬维度不一致"
                    f"（{', '.join(d['dimension'] for d in blocking[:5])}）"),
        "rule": "报告 CQ3/CQ4/CQ5：同名指标在不同数据集版本、划分、预算、top-k、"
                "阈值、筛选阶段、assay/终点或实验条件下不得横排或平均",
    }
