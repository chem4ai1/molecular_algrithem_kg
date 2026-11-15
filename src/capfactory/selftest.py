"""离线自检：不依赖网络与 LLM，验证整条闭环可运行.

流程：合成肽数据 → 构造能力节点 → 方案规划（模板回退）→ 代码生成 →
沙箱验证 → 结果回写图谱 → 覆盖度与方向建议。用于 CI 与交付前的快速回归。
"""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import Any, Dict

from .config import DEFAULT_CONFIG, Settings, _deep_merge, get_settings
from .kg import KnowledgeGraph
from .llm import LLMClient, set_client
from .replicate.dataset import materialise
from .replicate.replicator import Replicator
from .research.advisor import ResearchAdvisor
from .schema import Capability, Evidence, IOField, MetricSpec
from .utils import write_json

logger = logging.getLogger(__name__)

AA = "ACDEFGHIKLMNPQRSTVWY"
HYDRO = set("AILMFWV")
POS = set("KR")


def _make_peptides(n: int = 320, seed: int = 7):
    """生成可学习的合成肽数据（标签由电荷/疏水规则决定，带少量噪声）。"""
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        length = rng.randint(8, 18)
        seq = "".join(rng.choice(AA) for _ in range(length))
        charge = sum(1 for c in seq if c in POS) - sum(1 for c in seq if c in "DE")
        hydro = sum(1 for c in seq if c in HYDRO) / length
        score = 0.6 * charge + 6 * (hydro - 0.35)
        label = 1 if score > 0.9 else 0
        if rng.random() < 0.05:  # 5% 噪声
            label = 1 - label
        rows.append((seq, label))
    return rows


def _selftest_settings() -> Settings:
    base = get_settings().as_dict()
    storage = Path("storage_cf/selftest")
    override = {
        "llm": {"offline": True},
        "paths": {
            "storage": str(storage),
            "kg_dir": str(storage / "kg"),
            "raw_dir": str(storage / "raw"),
            "cache_dir": str(storage / "cache"),
            "workspace": str(storage / "workspace"),
            "reports": str(storage / "reports"),
            "logs": str(storage / "logs"),
        },
        "replicate": {"max_candidates": 2, "max_repair_rounds": 2, "stability_repeats": 2},
    }
    settings = Settings(data=_deep_merge(base, override))
    settings.path("storage")
    for key in ("kg_dir", "raw_dir", "cache_dir", "workspace", "reports", "logs"):
        settings.path(key)
    return settings


def run_selftest(verbose: bool = True) -> bool:
    """执行离线端到端自检，返回是否全部通过。"""
    settings = _selftest_settings()
    set_client(LLMClient(settings, offline=True))
    dataset_dir = settings.path("storage") / "datasets" / "selftest_peptides"
    meta = materialise(_make_peptides(), dataset_dir, "selftest_peptides",
                       source="synthetic(charge+hydrophobicity rule)")
    if not meta:
        logger.error("自检失败：数据集生成异常")
        return False
    meta["dataset_json"] = str(dataset_dir / "dataset.json")
    write_json(settings.path("storage") / "datasets" / "registry.json", [meta])

    graph = KnowledgeGraph(settings)
    cap = Capability(
        id="cap_selftest_toxicity",
        name="Composition-based peptide toxicity predictor",
        summary="二肽组成 + 集成学习预测肽毒性",
        category="model", task="peptide_toxicity_prediction",
        method=("Compute amino-acid and dipeptide composition of each peptide, "
                "train a class-balanced ensemble classifier, and threshold the "
                "predicted probability at 0.5 to label a peptide as toxic."),
        inputs=[IOField(name="sequences", dtype="list[str]", shape="[N]",
                        description="one-letter peptide sequences")],
        outputs=[IOField(name="probability", dtype="float", shape="[N]",
                         description="toxicity probability")],
        metrics=[MetricSpec(name="accuracy", reported=0.86, dataset="synthetic")],
        conditions=["labelled peptide dataset"], constraints=["ignores 3D structure"],
        dependencies=["numpy", "scikit-learn"],
        evidence=[Evidence(source_id="selftest", quote="synthetic self-test", locator="N/A")],
        tags=["toxicity", "composition"], confidence=0.8,
        provenance={"paper_title": "selftest", "extractor": "manual"},
    )
    graph.add_capability(cap)
    graph.save()

    replicator = Replicator(graph, settings,
                            progress=(lambda l, m: print(f"  [{l}] {m}")) if verbose else None)
    result = replicator.run(cap.id, meta)
    best = result["best"]
    ok_rep = bool(best["passed"])
    if verbose:
        print(f"  → 复刻结果：{'通过' if ok_rep else '未通过'} "
              f"score={best['score']:.3f} plan={best['plan']}")
        print(f"  → 指标：{best['metrics']}")
        for c in result["candidates"]:
            print(f"     candidate {c['plan']['name'][:44]:<46} "
                  f"score={c['report']['overall_score']:.3f} passed={c['passed']}")

    advisor = ResearchAdvisor(graph, settings=settings)
    advice = advisor.run(needs=["多肽毒性预测", "抗菌肽活性预测", "多肽成药性评估"])
    ok_res = bool(advice["directions"])
    if verbose:
        print(f"  → 覆盖度：{advice['coverage']['summary']}")
        print(f"  → 方向 {len(advice['directions'])} 条")
    return ok_rep and ok_res


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    ok = run_selftest()
    print("SELFTEST", "PASS" if ok else "FAIL")
