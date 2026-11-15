"""生成侧本体扩展：让同一张图同时承载「已发表知识」与「生成/复现过程」。

问题诊断
--------
现有 27 类是**后验知识图**：从论文里抽取「已经成立的事实」。
但论文生成、代码复现、LLM 写代码是**前瞻过程**：需要记录
「谁在哪个相位、依据什么、生成了什么、被哪个门验过、结果锚到哪个字节」。

若把这些过程信息塞进现有节点属性，会出现三个后果：

* 复现结果改了，论文叙述不会失效（没有锚）；
* LLM 生成的代码与图中 ``CodeFunction`` 无因果链（不知道谁写的、验过没）；
* 同一张图里「论文 A 报告的事实」与「本次 run 生成的主张」混在一起（无视图隔离）。

设计
----
新增 13 类，分三组，**全部带 ``run_id`` / ``provenance`` 视图标记**：

======================  ==========================================================
组                       类
======================  ==========================================================
决策/过程               Proposal · MethodLock · RunPhase
代码生成与复现           CodeGenerationTask · StaticCheck · ExperimentNode ·
                        ReproductionResult
叙述与评审               ClaimAnchor · NarrativeConstraint · ManuscriptSection ·
                        Figure · ReviewVerdict · CompileReport
======================  ==========================================================

三条链路共享同一个**内容寻址根节点** ``ExperimentNode``：

```
ResearchQuestion → Proposal → MethodLock(hash-lock)
  → CodeGenerationTask(LLM prompt→code) → StaticCheck → ExperimentNode
  → ReproductionResult(toy/full) → Observation
  → CapabilityClaim(fidelity/polarity) → ClaimAnchor → ExperimentNode
  → ManuscriptSection + Figure → ReviewVerdict → CompileReport
```

于是「LLM 写的代码」「复现出的数值」「论文里的一句话」三者被同一组
``code_sha / inputs_sha / outputs_sha`` 锁在一起——这正是 SciForge
``NODES.json + CLAIM_ANCHORS.json`` 的图化版本。

视图隔离：``provenance = as_published | as_generated``，生成过程节点一律写
``run_id``；查询时可按 run 过滤，不污染已验证的主图。
"""

from __future__ import annotations

from typing import Dict, Tuple

from .model import ConceptV2, F

# ---------------------------------------------------------------------------
# 词表
# ---------------------------------------------------------------------------
PROVENANCE = ("as_published", "as_generated")
FIDELITY = ("symbolic", "numerical", "qualitative")
POLARITY = ("positive", "boundary", "negative")
CODEGEN_STATUS = ("draft", "static_checked", "smoke_passed", "dispatched",
                  "completed", "failed")
CHECK_TYPES = ("security_scan", "dep_gate", "smoke_gate", "method_parity",
               "claim_anchor", "leakage_scan", "compile_audit")
EXPERIMENT_KINDS = ("toy", "subset", "full", "ablation", "reproduction")
PHASE_IDS = ("intake", "question", "proposal", "method_lock", "codegen",
             "reproduce", "claim", "narrative", "review", "publish")
GATE_KINDS = ("script", "llm_review", "human")
VERDICT_STATES = ("PASS", "WARN", "FAIL", "NOT_APPLICABLE", "BLOCKED", "ERROR")
# 6 轴冻结权重（SciForge review.py RUBRIC_AXES）
RUBRIC_AXES = {
    "main_experiment_logic": 0.30, "evidence_sufficiency": 0.20,
    "novelty": 0.15, "soundness": 0.15, "clarity": 0.10,
    "citation_integrity": 0.10,
}
# 三档保真度允许的措辞（result-to-claim §3）
ALLOWED_WORDING = {
    "symbolic": ("proven", "established", "demonstrated"),
    "numerical": ("supported", "validated", "observed"),
    "qualitative": ("suggests", "indicates", "consistent with"),
}


def _g(extra: Tuple = ()) -> Tuple:
    """生成侧节点共有的视图字段。"""
    return (F("run_id", "derived", "must_have"),
            F("provenance", "derived", "must_have"),
            F("phase", "derived", "should_have"),
            F("created_at", "derived")) + tuple(extra)


GENERATION_CLASSES: Dict[str, ConceptV2] = {

    # ---------------- 决策 / 过程 ----------------
    "Proposal": ConceptV2("Proposal", "generation",
        "研究提案：假设、锚定的图谱缺口、新颖性判定与人工选择", _g((
            F("gap_id", "extracted", "must_have"),
            F("hypothesis", "extracted", "must_have"),
            F("novelty", "derived", "should_have"),
            F("observed_pairs", "derived"),
            F("rationale", "extracted", "should_have"),
            F("selected_by", "derived", "should_have"),
            F("status", "derived"),
        ))),
    "MethodLock": ConceptV2("MethodLock", "generation",
        "方法预注册：结果出来之前冻结方法选择，防事后改方法", _g((
            F("registry_hash", "derived", "must_have"),
            F("scope", "extracted", "must_have"),
            F("locked_modules", "extracted", "should_have"),
            F("approved_by", "derived", "should_have"),
            F("locked_at", "derived"),
            F("evaluation_protocol", "extracted"),
        ))),
    "RunPhase": ConceptV2("RunPhase", "generation",
        "一次 run 的相位实例：状态、门、预算与回退", _g((
            F("phase_id", "derived", "must_have"),
            F("state", "derived", "must_have"),
            F("gate_kind", "derived"),
            F("verdict", "derived", "should_have"),
            F("artifacts", "derived"),
            F("budget_left", "derived"),
            F("loopback_from", "derived"),
        ))),

    # ---------------- 代码生成与复现 ----------------
    "CodeGenerationTask": ConceptV2("CodeGenerationTask", "generation",
        "LLM 写代码的请求与产物：prompt、模型、目标文件、静态检查状态", _g((
            F("prompt", "extracted", "must_have"),
            F("model", "derived", "should_have"),
            F("target_files", "extracted", "must_have"),
            F("generated_files", "derived"),
            F("status", "derived", "should_have"),
            F("registry_hash", "derived"),
            F("code_sha", "derived"),
        ))),
    "StaticCheck": ConceptV2("StaticCheck", "generation",
        "派发前的机器门结果：security/dep/smoke/parity/claim-anchor", _g((
            F("check_type", "derived", "must_have"),
            F("verdict", "derived", "must_have"),
            F("findings", "derived"),
            F("script", "derived"),
            F("exit_code", "derived"),
        ))),
    "ExperimentNode": ConceptV2("ExperimentNode", "generation",
        "★ 内容寻址实验节点：code/inputs/outputs 哈希 + 重执行命令", _g((
            F("kind", "derived", "must_have"),
            F("code_sha", "derived", "must_have"),
            F("inputs_sha", "derived", "must_have"),
            F("outputs_sha", "derived", "must_have"),
            F("reexec_cmd", "derived", "must_have"),
            F("seeds", "extracted"),
            F("status", "derived"),
            F("claim_ids", "derived"),
            F("parent", "derived"),
        ))),
    "ReproductionResult": ConceptV2("ReproductionResult", "generation",
        "toy/subset/full 复现结果：解析解 sanity band 与 ladder 判定", _g((
            F("kind", "extracted", "must_have"),
            F("baseline", "extracted", "must_have"),
            F("candidate", "extracted", "must_have"),
            F("direction", "extracted", "should_have"),
            F("sanity_band", "extracted"),
            F("analytic_truth", "extracted"),
            F("ladder_state", "derived", "should_have"),
            F("relative_gain_pct", "derived"),
        ))),

    # ---------------- 叙述与评审 ----------------
    "ClaimAnchor": ConceptV2("ClaimAnchor", "generation",
        "★ 主张锚：把论文里的一句话锁到产生它的代码/数据字节", _g((
            F("claim_id", "derived", "must_have"),
            F("node_id", "derived", "must_have"),
            F("tex_file", "extracted"),
            F("line", "extracted"),
            F("resolved", "derived", "must_have"),
            F("evidence_refs", "derived"),
            F("drift", "derived"),
        ))),
    "NarrativeConstraint": ConceptV2("NarrativeConstraint", "generation",
        "叙述纪律：三档保真度、极性、允许措辞、负面结果不得进 Abstract", _g((
            F("fidelity", "derived", "must_have"),
            F("polarity", "derived", "must_have"),
            F("allowed_wording", "derived", "should_have"),
            F("claim_text", "extracted"),
            F("protagonist_test", "derived"),
        ))),
    "ManuscriptSection": ConceptV2("ManuscriptSection", "generation",
        "章节草稿：只引用已锚定的 claim 与已审计的图", _g((
            F("section_role", "extracted", "must_have"),
            F("text", "extracted", "must_have"),
            F("claim_refs", "derived", "should_have"),
            F("figure_refs", "derived"),
            F("draft_version", "derived"),
            F("leakage_scrub", "derived"),
        ))),
    "Figure": ConceptV2("Figure", "generation",
        "图：spec 由 LLM 写、布局由渲染器锁死、数据来自 Observation", _g((
            F("claim", "extracted", "must_have"),
            F("archetype", "extracted", "should_have"),
            F("spec_path", "derived"),
            F("render_path", "derived"),
            F("audit_verdict", "derived", "should_have"),
            F("observation_ids", "derived", "must_have"),
            F("caption", "extracted"),
        ))),
    "ReviewVerdict": ConceptV2("ReviewVerdict", "generation",
        "独立盲审：冻结 6 轴 rubric、角色隔离、最强拒稿论证", _g((
            F("role", "derived", "must_have"),
            F("rubric_scores", "extracted", "must_have"),
            F("overall", "derived", "must_have"),
            F("kill_argument", "extracted"),
            F("reread_from_files", "derived", "should_have"),
            F("still_unresolved", "extracted"),
        ))),
    "CompileReport": ConceptV2("CompileReport", "generation",
        "成稿验收：零警告编译、图表嵌入、术语 scrub、产物集合完整", _g((
            F("zero_warnings", "derived", "must_have"),
            F("embedded_figures", "derived"),
            F("artifact_manifest", "derived", "should_have"),
            F("leakage_scrub", "derived"),
            F("tier", "derived", "should_have"),
        ))),
}

# ---------------------------------------------------------------------------
# 关系：三组
# ---------------------------------------------------------------------------
DECISION_LINKS: Dict[str, Tuple[str, str, str]] = {
    "HAS_PROPOSAL": ("Paper", "Proposal", "本次 run 从哪篇/哪个问题出发"),
    "ANCHORS_GAP": ("Proposal", "ResearchQuestion", "提案锚定图谱缺口"),
    "LOCKED_BY": ("Proposal", "MethodLock", "方法选择被 hash-lock 冻结"),
    "GOVERNS": ("MethodLock", "CodeGenerationTask", "预注册约束代码生成范围"),
    "HAS_PHASE": ("Paper", "RunPhase", "一次 run 的相位轨迹"),
    "GATED_BY": ("RunPhase", "StaticCheck", "相位被哪个机器门放行"),
    "LOOPS_BACK_TO": ("RunPhase", "RunPhase", "失败回退到哪个相位"),
}

REPRO_LINKS: Dict[str, Tuple[str, str, str]] = {
    "GENERATES": ("CodeGenerationTask", "CodeFunction", "LLM 生成的代码符号"),
    "GENERATES_MODULE": ("CodeGenerationTask", "CodeModule", "LLM 生成的代码文件"),
    "CHECKED_BY": ("CodeGenerationTask", "StaticCheck", "派发前静态检查结果"),
    "RUNS_IN": ("CodeGenerationTask", "ExperimentNode", "代码在哪个内容寻址节点执行"),
    "EMITS": ("ExperimentNode", "ReproductionResult", "实验节点产出的数值结果"),
    "CORROBORATES": ("ReproductionResult", "Observation", "复现结果对应图上的观测"),
    "IMPLEMENTS_STEP": ("CodeFunction", "AlgorithmStep", "代码实现了方法栈的哪一步"),
    "BINDS_BENCHMARK": ("ExperimentNode", "Benchmark", "跑在哪个基准契约上"),
}

NARRATIVE_LINKS: Dict[str, Tuple[str, str, str]] = {
    "ANCHORED_TO": ("CapabilityClaim", "ClaimAnchor", "主张的字节级锚点"),
    "PRODUCED_BY": ("ClaimAnchor", "ExperimentNode", "锚点指向产生结果的实验节点"),
    "DERIVED_FROM": ("ClaimAnchor", "Observation", "锚点同时指向图上的观测"),
    "CONSTRAINED_BY": ("CapabilityClaim", "NarrativeConstraint", "措辞受保真度约束"),
    "GROUNDS": ("Observation", "CapabilityClaim", "观测支撑主张"),
    "ASSERTS": ("ManuscriptSection", "CapabilityClaim", "章节断言了哪些主张"),
    "USES_FIGURE": ("ManuscriptSection", "Figure", "章节引用的图"),
    "EMBEDS": ("Figure", "Observation", "图嵌入的观测数据"),
    "REVIEWS": ("ReviewVerdict", "ManuscriptSection", "盲审作用于哪个章节"),
    "REPORTS_ON": ("CompileReport", "ManuscriptSection", "编译/验收结果"),
}


def relation_matrix() -> Dict[str, Dict[str, Tuple[str, str, str]]]:
    return {"decision": DECISION_LINKS, "reproduction": REPRO_LINKS,
            "narrative": NARRATIVE_LINKS}


# 相位定义：门类型写进配置（SciForge 教训：README 说有门、实际没接线）
GENERATION_PHASES: Dict[str, Dict[str, object]] = {
    "intake":     {"order": 0, "gate": "script", "produces": ("census",),
                   "reads": ("Paper", "CodeRepository", "ResearchQuestion")},
    "question":   {"order": 1, "gate": "script", "produces": ("gap_report",),
                   "reads": ("ResearchQuestion", "ProblemCategory")},
    "proposal":   {"order": 2, "gate": "human", "produces": ("proposal",),
                   "reads": ("Algorithm", "AlgorithmFamily", "Domain")},
    "method_lock": {"order": 3, "gate": "human", "produces": ("method_lock",),
                    "reads": ("AlgorithmComposition", "AlgorithmStep")},
    "codegen":    {"order": 4, "gate": "script", "produces": ("code", "static_checks"),
                   "reads": ("CodeFunction", "AlgorithmStep")},
    "reproduce":  {"order": 5, "gate": "script", "produces": ("experiment_node", "result"),
                   "reads": ("Benchmark", "MetricDefinition")},
    "claim":      {"order": 6, "gate": "script", "produces": ("claims", "anchors"),
                   "reads": ("Observation", "CapabilityClaim")},
    "narrative":  {"order": 7, "gate": "llm_review", "produces": ("sections", "figures"),
                   "reads": ("ClaimAnchor", "Figure")},
    "review":     {"order": 8, "gate": "llm_review", "produces": ("review",),
                   "reads": ("ManuscriptSection", "ReviewVerdict")},
    "publish":    {"order": 9, "gate": "script", "produces": ("compile_report",),
                   "reads": ("CompileReport", "RunPhase")},
}


# 模块内短别名（flow.py 使用）；ontology 包级导出用 GENERATION_PHASES 避免与
# layers.PHASES（training/inference/init/operational）冲突。
PHASES = GENERATION_PHASES


def summary() -> Dict[str, object]:
    m = relation_matrix()
    return {"generation_classes": len(GENERATION_CLASSES),
            "relations": sum(len(x) for x in m.values()),
            "by_group": {k: len(v) for k, v in m.items()},
            "phases": len(GENERATION_PHASES),
            "script_gates": sum(1 for p in PHASES.values() if p["gate"] == "script"),
            "llm_review_gates": sum(1 for p in PHASES.values() if p["gate"] == "llm_review"),
            "human_gates": sum(1 for p in PHASES.values() if p["gate"] == "human"),
            "total_classes_with_core": 27 + len(GENERATION_CLASSES)}
