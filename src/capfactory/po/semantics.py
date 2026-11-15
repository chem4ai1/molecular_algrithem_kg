"""本体语义层：概念定义、关系语义、推理规则、任务协议与 LLM 上下文打包.

三层输出：

1. **人类可读**：每个概念的 ``definition / not_scope / examples / constraints``；
2. **机器可读**：``SemanticBundle.to_dict()``（JSON）、``to_jsonld_context()``、
   ``to_owl_turtle()``——可直接作为 LLM 的 tool schema / system 上下文，
   或导入 Neo4j / RDF 三库；
3. **任务协议**：``TASK_PROTOCOLS`` 规定知识抽取、推理、缺口发现、总结四类任务的
   输入、输出 schema 与后置校验，使 LLM 输出可被确定性校验器接住。

设计原则（沿用报告 §5.3）：定义必须带**边界**（``not_scope``）。
只说「MetricObservation 是一次观测」不够，还要说「它不是 MetricDefinition、
不是跨条件平均值」——否则 LLM 会把两者合并。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..utils import now_iso
from .concepts import CONCEPT_SPECS, DIMENSIONS, RELATION_DOMAIN_RANGE
from .keywords import keyword_stats, keyword_table
from .vocab import default_registry

ONTOLOGY_VERSION = "po_semantics_v1"
NAMESPACE = "https://capfactory.local/po#"

# ---------------------------------------------------------------------------
# 1. 概念语义（36 类）：定义 / 边界 / 示例 / 约束 / LLM 提示
# ---------------------------------------------------------------------------
CONCEPT_SEMANTICS: Dict[str, Dict[str, Any]] = {
    # ---- 问题 ----
    "ProblemCategory": {
        "definition": "分析者构建的可层级问题分类（P01–P11），用于聚合可检验子问题；不是领域穷尽清单，也不是作者原话。",
        "not_scope": "不是论文级研究问题（那是 ResearchQuestion），不是单一失败点（那是 ResearchProblem）。",
        "examples": ["P06 代理指标与实测终点脱节", "P10 实验闭环、复现和开放资源"],
        "constraints": ["必须标注 attribution=analyst_synthesis", "子问题通过 BROADER 反向归属"],
        "llm_hint": "只在文本明确讨论某类系统性研究障碍时抽取；不要为每篇论文都造一个分类。",
        "synonyms": ["问题分类", "problem taxonomy"],
    },
    "ResearchProblem": {
        "definition": "可检验的失败点或尚未满足的需求（P01a–P11b），带一个可回答的问题句。",
        "not_scope": "不是宽泛方向（ResearchDirection），不是已解决结论。",
        "examples": ["P06a 代理终点错位：结构置信/对接能否预测 Kd/IC50/细胞作用？"],
        "constraints": ["必须有 question", "status 默认 open_or_partially_addressed", "论文关联用三种语义边之一"],
        "llm_hint": "问题句应为疑问句，且能通过实验/评测回答；不要把方法名当问题。",
        "synonyms": ["研究子问题", "failure mode"],
    },
    "ResearchQuestion": {
        "definition": "针对单篇论文，把其研究目的（aim/objective）转写成一个可回答的问题句。",
        "not_scope": "不是跨论文归纳的问题（那是 ResearchProblem）。",
        "examples": ["如何在给定蛋白表面设计可结合的环肽并推进到直接结合验证？"],
        "constraints": ["必须挂在某篇 Paper 下", "attribution 区分作者自述与分析者提炼"],
        "llm_hint": "从摘要的 aim/objective 句改写，不要引入论文未声称的目标。",
        "synonyms": ["论文级问题"],
    },
    "ProblemContext": {
        "definition": "问题背后的疾病、生物学与技术动机，用于解释为什么这是一个值得解决的问题。",
        "not_scope": "不是数据集来源，不是实验条件（那是 ExperimentalCondition）。",
        "examples": ["抗生素耐药性使 AMP 发现成为公共健康优先事项"],
        "constraints": ["建议记录 assumptions，便于后续反驳"],
        "llm_hint": "只抽取能解释「为什么这是问题」的背景，不要复述方法。",
        "synonyms": ["问题背景", "motivation"],
    },
    # ---- 知识 ----
    "Paper": {
        "definition": "work-level 文献身份；一个 DOI 不代表一个实验、一个算法或一个结论。",
        "not_scope": "不是版本（PaperVersion），不是代码仓库（CodeArtifact）。",
        "examples": ["RFpeptides, Nature Chemical Biology 2025, doi:10.1038/s41589-025-01929-w"],
        "constraints": ["必须记录 reading_coverage 与 coverage_gap", "数字结论需绑定到具体版本"],
        "llm_hint": "标题/DOI/年份/期刊来自正文或参考文献，不要由模型补全 DOI。",
        "synonyms": ["论文", "work"],
    },
    "PaperVersion": {
        "definition": "期刊版、作者稿、补充材料或更正通知；证据严格绑定到版本。",
        "not_scope": "不是 work 身份；不同版本结论不自动等价。",
        "examples": ["version:08-author-v2 (bioRxiv v2)", "version:02-correction"],
        "constraints": ["source_kind ∈ 受控词表", "更正用 CORRECTED_BY 连接，不覆盖旧观测"],
        "llm_hint": "遇到 preprint/author manuscript/supplement 时建独立版本节点，不要挂到正式版下。",
        "synonyms": ["版本", "preprint", "author manuscript"],
    },
    "CapabilityClaim": {
        "definition": "主体 + 能力 + 适用条件 + 证据支撑的主张；不表示无限泛化，也不是算法的布尔属性。",
        "not_scope": "不是 Algorithm 的属性，不是 Task，不是 Workflow 的整体流程。",
        "examples": ["对所测 4 个靶标产生具可测结合的环肽候选（scope: 4 targets, limited candidates）"],
        "constraints": ["必须有 statement 与 scope", "必须有 evidence_level 与 attribution",
                        "必须经 ABOUT_METHOD 指向 Workflow 或 Algorithm",
                        "必须至少一条 EVALUATED_IN 与 SUPPORTED_BY"],
        "llm_hint": "把「在某条件下、对某对象、由某评测支持」写进 scope；不要写 canDiscoverDrug=true。",
        "synonyms": ["能力主张", "claim"],
    },
    "Limitation": {
        "definition": "作者明确局限或分析者推断的局限，必须区分归属并用 QUALIFIES 限制主张范围。",
        "not_scope": "不是负结果（NegativeOutcome），不是缺陷修复建议。",
        "examples": ["合成/环化失败需计入提名分母；结合不证明功能或递送"],
        "constraints": ["attribution=author_explicit 或 analyst_synthesis", "必须 QUALIFIES 某条 CapabilityClaim"],
        "llm_hint": "只在原文有 discussion/limitation 段或明确限制语时抽取；分析者推断需改 attribution。",
        "synonyms": ["局限", "caveat"],
    },
    "Evidence": {
        "definition": "原文定位：论文版本 + 节/页/图表 + 原始文件 hash，保留派生路径。",
        "not_scope": "不是结论本身，不是数据集，不是代码链接。",
        "examples": ["E01_008 @ Par10, section: De novo design of macrocyclic binders to MCL1"],
        "constraints": ["必须有 paper_version_id 与 locator", "有 quote 时建议做逐字锚定",
                        "extraction_file_sha256 用于识别提取文件而非依赖绝对路径"],
        "llm_hint": "locator 用 PDF 物理页或段落号；不要编造页码。",
        "synonyms": ["证据定位", "citation locator"],
    },
    "EvidenceFamily": {
        "definition": "共享平台/数据/队伍的依赖组；成员不自动构成独立复现。",
        "not_scope": "不是一篇论文的多个实验，也不是同一算法的不同版本。",
        "examples": ["family:Chemistry42 覆盖 16–20 五篇案例"],
        "constraints": ["independence_status 必填", "MEMBER_OF 从 Paper 指向家族"],
        "llm_hint": "识别到同一商业平台/同一团队/同一数据集时建立家族，避免把 5 篇案例算 5 次独立验证。",
        "synonyms": ["证据依赖组", "shared platform"],
    },
    "Assertion": {
        "definition": "属性图边的 RDF reification：subject-predicate-object + 证据 ID + 归属。",
        "not_scope": "不是节点，不是自然语言句子。",
        "examples": ["problem:P01a BROADER problem:P01, attribution=analyst_synthesis"],
        "constraints": ["predicate 必须在关系词表内", "evidence_ids 必须指向存在的 Evidence",
                        "attribution 必填"],
        "llm_hint": "每条关系都要能回答「谁说的、依据哪段原文」。",
        "synonyms": ["断言", "reification"],
    },
    # ---- 算法数据 ----
    "Task": {
        "definition": "定义输入、输出与前置条件的计算或实验任务；不是宽泛能力。",
        "not_scope": "不是能力（CapabilityClaim），不是方法（Algorithm）。",
        "examples": ["由靶标结构与结合界面生成环肽序列/构象（inputCondition: 已定义口袋）"],
        "constraints": ["必须有 task_family", "建议记录 input_condition / sample_budget / top_k"],
        "llm_hint": "任务句要能写出 I/O 契约；「药物发现」不是任务，「口袋→配体」才是。",
        "synonyms": ["任务", "task specification"],
    },
    "Algorithm": {
        "definition": "方法身份（架构族 + 版本状态）；共享平台不重复计独立算法。",
        "not_scope": "不是流程（Workflow），不是能力主张，不是某次运行。",
        "examples": ["RFdiffusion (diffusion, SE(3) equivariant)", "Chemistry42 (generative platform)"],
        "constraints": ["必须有 name", "architecture 建议落在 A01–A18 词表",
                        "version_status 记录是否可固定 commit"],
        "llm_hint": "同一平台的多篇案例共用 Algorithm 节点，不要按论文复制算法。",
        "synonyms": ["算法", "method", "model"],
    },
    "Workflow": {
        "definition": "生成→过滤→人工选择→实验等步骤组成的解决方案流程，含人工贡献说明。",
        "not_scope": "不是单一模型，不是一次评测。",
        "examples": ["生成 27 条→环化 14 条→SPR 测 3 条命中"],
        "constraints": ["必须有 steps", "human_contribution 建议非空，避免把人工筛选算作模型能力"],
        "llm_hint": "流程要按阶段写，并标出哪些步骤由人完成。",
        "synonyms": ["流程", "pipeline"],
    },
    "Dataset": {
        "definition": "数据来源身份与版本，记录出处与许可状态；不等于具体训练/测试切分。",
        "not_scope": "不是 DatasetSplit，不是 DataArtifact（共享文件）。",
        "examples": ["CrossDocked2020", "PDBBind", "PepMLM protein–peptide complex"],
        "constraints": ["必须记录 version_status", "HAS_SPLIT 指向切分规则"],
        "llm_hint": "数据集名与版本分开记；「3700 万候选」是候选集不是数据集。",
        "synonyms": ["数据集", "corpus"],
    },
    "DatasetSplit": {
        "definition": "train/validation/test 的划分规则：随机、时间、scaffold、靶点簇、口袋或同源过滤。",
        "not_scope": "不是数据集本身；不是泄漏结论。",
        "examples": ["100000训练/100测试口袋；序列划分；后处理键重建"],
        "constraints": ["必须有 rule", "overlap_risk 记录是否独立审计",
                        "leakage_audit=not_independently_rerun 时不得宣称无泄漏"],
        "llm_hint": "从 methods 的 data split 段抽取；没说就写 not_reported，不要假设随机划分。",
        "synonyms": ["数据划分", "split"],
    },
    "Objective": {
        "definition": "优化目标或约束，方向随疾病与组织目标而变（可能是最大化也可能是限制）。",
        "not_scope": "不是评测指标（MetricDefinition），不是结论。",
        "examples": ["提高菌株选择性（maximize）", "限制全身暴露（minimize，肠道限制性）"],
        "constraints": ["direction ∈ maximize/minimize/context_dependent/constraint"],
        "llm_hint": "同一「暴露」在系统性药物是最大化、在肠道限制性药物是最小化，必须记录方向。",
        "synonyms": ["优化目标", "objective function"],
    },
    # ---- 代码 ----
    "CodeArtifact": {
        "definition": "源码资源；核心实现与辅助脚本分开描述，开放性多轴记录。",
        "not_scope": "不是权重（WeightArtifact），不是数据（DataArtifact），不是论文。",
        "examples": ["github.com/RosettaCommons/RFdiffusion, BSD-3-Clause, availability=open_licensed"],
        "constraints": ["availability 与 license 都必须显式（可为 not_read）",
                        "checked_date 记录核查时间", "scope 区分 core/auxiliary"],
        "llm_hint": "「代码公开」≠「许可明确」；两者分别填，许可不明写 license_unverified。",
        "synonyms": ["代码", "repository", "source code"],
    },
    "WeightArtifact": {
        "definition": "模型权重的取得方式与使用许可（可能与源码条款不同）。",
        "not_scope": "不是源码仓库，不是训练数据。",
        "examples": ["AF3 weights: noncommercial_weights（与 Apache-2.0 源码不同）"],
        "constraints": ["availability 与 license 必填", "与源码条款冲突时分别记录"],
        "llm_hint": "权重条款常单独声明，不要用仓库 LICENSE 覆盖。",
        "synonyms": ["权重", "checkpoint", "pretrained weights"],
    },
    "DataArtifact": {
        "definition": "论文共享数据文件的可用性与许可，与数据集身份分开记录。",
        "not_scope": "不是 Dataset 身份，不是切分。",
        "examples": ["Supplementary Table 3, CC-BY-4.0"],
        "constraints": ["availability 与 license 必填", "缺失写 missing_reason"],
        "llm_hint": "区分「数据集本身」与「论文共享的数据文件」。",
        "synonyms": ["数据资源", "supplementary data"],
    },
    # ---- 指标 ----
    "EvaluationRun": {
        "definition": "特定模型/任务/条件下的作者报告实验；本项目未重跑模型。",
        "not_scope": "不是指标定义，不是观测本身。",
        "examples": ["evaluation:O001, author_reported_not_rerun, modality=biochemical"],
        "constraints": ["evaluation_kind 必填（默认 author_reported_not_rerun）",
                        "USES_METRIC 与 PRODUCES_OBSERVATION 至少各 1 条"],
        "llm_hint": "除非你真的跑了实验，否则 evaluation_kind 必须是 author_reported_not_rerun。",
        "synonyms": ["评测记录", "experiment run"],
    },
    "MetricDefinition": {
        "definition": "指标的稳定语义：定义、方向、单位量纲、取值类型与解释。",
        "not_scope": "不是某次数值（MetricObservation）；不同条件下的同名指标仍共享定义。",
        "examples": ["pose_success_percent: RMSD<2Å 的比例，方向 higher，unitScale percent"],
        "constraints": ["必须有 name 与 direction", "direction 可为 context_dependent",
                        "definition 应说明分子/分母与阈值"],
        "llm_hint": "定义里写清「算什么、除以什么、阈值多少」，否则后续不可比。",
        "synonyms": ["指标定义", "metric"],
    },
    "MetricObservation": {
        "definition": "一次报告值：值或缺失状态二选一，绑定单位、条件、对象与证据。",
        "not_scope": "不是定义，不是跨条件平均值，不是候选集合的分数。",
        "examples": ["IC50=0.63 nM @ pH7.4/cGAMP, ISM5939 vs human ENPP1, E19_019"],
        "constraints": ["value 与 missing_state 恰好一个（SHACL xone）",
                        "必须有 unit 与至少一个 HAS_CONDITION",
                        "必须有 SUPPORTED_BY 证据", "比例必须带 numerator/denominator/stage"],
        "llm_hint": "原文没给数值就写 missing_state=not_reported，绝不填 0 或估计值。",
        "synonyms": ["指标观测", "reported value"],
    },
    "ExperimentalCondition": {
        "definition": "计算与实验共有的条件对象：pH、底物、剂量、时间、物种、构建体、预算、阈值。",
        "not_scope": "不是指标，不是数据集划分（虽然可引用）。",
        "examples": ["pH=7.4, substrate=2,3-cGAMP, nBiological=2"],
        "constraints": ["同名指标在不同条件下必须建不同条件对象", "条件变更应新建而非覆盖"],
        "llm_hint": "同一 IC50 在 pH7.4/6.5 下是两条观测，不要平均。",
        "synonyms": ["实验条件", "assay condition"],
    },
    "Assay": {
        "definition": "测定或评测方法：生化 assay 或计算 benchmark protocol。",
        "not_scope": "不是终点（Endpoint），不是指标。",
        "examples": ["SPR single-cycle kinetics", "PoseBusters validity check"],
        "constraints": ["必须有 name", "modality 记录证据层级", "protocol_completion 记录未抽取字段"],
        "llm_hint": "区分测量手段（SPR）与测的量（Kd）。",
        "synonyms": ["测定方法", "protocol"],
    },
    "Endpoint": {
        "definition": "实际测量或估计的对象（结合亲和力、几何有效性、抗菌活性、临床安全…）。",
        "not_scope": "不是指标格式（percent/nM），不是 assay 名称。",
        "examples": ["binding_affinity", "geometric_validity", "clinical_safety"],
        "constraints": ["必须有 label", "modality 与 endpoint_type 建议填写"],
        "llm_hint": "代理终点（docking score）与真实终点（Kd/IC50）要分开标注。",
        "synonyms": ["观测终点", "endpoint"],
    },
    "Benchmark": {
        "definition": "可复现评测基准 = 数据 + 切分 + 指标 + 协议；不等于原始数据集。",
        "not_scope": "不是 Dataset（数据来源），不是单次评测（EvaluationRun）。",
        "examples": ["CrossDocked2020 + random holdout + RMSD<2Å + pose_success_percent"],
        "constraints": ["必须有 name", "input_schema/output_schema 必须显式（可为 not_extracted）",
                        "指标必须绑定 MetricDefinition", "必须记录 tested_by_papers/codes"],
        "llm_hint": "基准至少要能回答：输入是什么、输出是什么、怎么算分、和谁比。",
        "synonyms": ["基准", "benchmark suite", "评测基准"],
    },
    "LeaderboardEntry": {
        "definition": "某基准某指标上的一条可比成绩；SOTA 是同可比键下按方向的极值。",
        "not_scope": "不是 MetricObservation（原始观测），不是 MetricDefinition。",
        "examples": ["CrossDocked2020 · PB_valid_fraction · 0.74 · PhoreGen full model"],
        "constraints": ["必须有 benchmark_id / metric_id / value",
                        "必须带 comparability_key 或 group_key",
                        "组内少于 2 条时不得标 SOTA"],
        "llm_hint": "只有同一可比键且组内≥2 条时才可称 SOTA，否则只写「唯一报告值」。",
        "synonyms": ["榜单条目", "成绩", "SOTA entry"],
    },
    # ---- 分类 ----
    "Domain": {
        "definition": "应用领域 D0–D10；一篇论文/能力可属多个领域，多标签非互斥。",
        "not_scope": "不是任务类型（Task），不是算法族（AlgorithmFamily）。",
        "examples": ["D5 多肽与抗菌肽", "D0 通用算法（无生物语境）"],
        "constraints": ["code ∈ domain_code 词表", "D0 仅在无强领域关键词时使用"],
        "llm_hint": "先判断有没有生物/材料/化学语境；没有就 D0，不要硬塞到 D1。",
        "synonyms": ["领域", "application domain"],
    },
    "AlgorithmFamily": {
        "definition": "算法族 A01–A18；方法身份，与 Algorithm.architecture 互补（族更粗、架构更细）。",
        "not_scope": "不是具体实现（Algorithm），不是领域。",
        "examples": ["A04 扩散/分数模型", "A05 流匹配/最优传输"],
        "constraints": ["code ∈ algo_code 词表", "多标签上限 3"],
        "llm_hint": "按「生成机制」而不是「应用场景」归类；扩散 + 等变要同时标 A04 与 A10。",
        "synonyms": ["算法族", "method family"],
    },
    # ---- 支撑 ----
    "Molecule": {
        "definition": "有化学身份的单个化合物/肽；序列/SMILES/注册号未解析时保留本地名称。",
        "not_scope": "不是候选集合（CandidateSet），不是分子状态（构象/质子化）。",
        "examples": ["ISM5939", "MDB_D8 macrocycle"],
        "constraints": ["identifier_status 记录标识符解析状态", "不得猜造外部 ID"],
        "llm_hint": "「32 条候选」是 CandidateSet；只有具名单分子才是 Molecule。",
        "synonyms": ["分子", "compound"],
    },
    "CandidateSet": {
        "definition": "生成、提名或入测的样本群；保留选择逻辑与阶段。",
        "not_scope": "不是单分子，不是命中率分母本身。",
        "examples": ["27 条提名环肽", "32 条 PG-1 变体"],
        "constraints": ["记录 selection 与 sample_size", "与 SelectionStage 的分母对应"],
        "llm_hint": "候选集必须带来源阶段（生成/提名/合成/入测）。",
        "synonyms": ["候选集合", "candidate pool"],
    },
    "MoleculeState": {
        "definition": "分子的构象、质子化、立体化学与复合状态，同一分子可有多个并存状态。",
        "not_scope": "不是分子身份。",
        "examples": ["apo vs holo 构象", "质子化态 pH6.5"],
        "constraints": ["state_type 建议填写", "条件变更新建状态"],
        "llm_hint": "同一分子的不同构象是不同状态，不要互相覆盖。",
        "synonyms": ["分子状态", "conformer"],
    },
    "Target": {
        "definition": "蛋白/靶标构建体，记录物种与构建方式；不把数据集名当作靶点。",
        "not_scope": "不是数据集，不是物种（Organism）。",
        "examples": ["human ENPP1", "MCL1"],
        "constraints": ["external_id_status 记录解析状态", "species/construct 建议填写"],
        "llm_hint": "靶点与物种分开；「小鼠 PD-L1」是 Target + Organism。",
        "synonyms": ["靶标", "target protein"],
    },
    "Organism": {
        "definition": "物种或菌株；本地身份直到外部 ID 可核验。",
        "not_scope": "不是靶点。",
        "examples": ["E. coli ATCC 25922", "mouse"],
        "constraints": ["taxonomy_status 记录可核验程度"],
        "llm_hint": "抗菌谱实验的菌株必须单独建 Organism 节点。",
        "synonyms": ["物种", "strain"],
    },
    "DesignCampaign": {
        "definition": "在靶标与目标产品属性下的一轮或多轮研发活动。",
        "not_scope": "不是单次评测，不是完整论文。",
        "examples": ["RFpeptides 4 个 target campaigns"],
        "constraints": ["必须有 objective", "通过 REPORTS_CAMPAIGN 挂到 Paper"],
        "llm_hint": "有多轮设计/合成/测试时建 campaign，并用 HAS_STAGE 记录漏斗。",
        "synonyms": ["设计活动", "campaign"],
    },
    "SelectionStage": {
        "definition": "筛选漏斗阶段（生成→提名→合成→入测→命中），计数有明确分母。",
        "not_scope": "不是候选集合本身，不是成功率指标。",
        "examples": ["nominated=27, synthesized=14, hit=3"],
        "constraints": ["stage_type/stage ∈ 词表", "count 与 unit 必填", "与 MetricObservation.stage 对齐"],
        "llm_hint": "命中率的分母取决于阶段；3/14 与 3/27 是两个观测。",
        "synonyms": ["筛选阶段", "funnel stage"],
    },
    "NegativeOutcome": {
        "definition": "负结果：测到阴性、合成失败、未测、撤稿/不公开，四者语义不同。",
        "not_scope": "不是 Limitation（局限），不是 missing_state 本身。",
        "examples": ["13 条环化产量不足（synthesis_insufficient）"],
        "constraints": ["outcome_type ∈ 词表", "count 与 reason 建议填写"],
        "llm_hint": "不要把「没测」写成「阴性」；前者是 not_measured。",
        "synonyms": ["负结果", "failure"],
    },
}

# ---------------------------------------------------------------------------
# 2. 关系语义（40 类）
# ---------------------------------------------------------------------------
RELATION_SEMANTICS: Dict[str, Dict[str, Any]] = {
    "HAS_VERSION": {"definition": "论文与其版本", "inverse": "VERSION_OF",
                    "cardinality": "1..*", "transitive": False},
    "FORMULATES": {"definition": "分析者把论文目的提炼为研究问题", "inverse": "FORMULATED_BY",
                   "cardinality": "0..1", "transitive": False},
    "MOTIVATED_BY": {"definition": "问题背景", "inverse": "MOTIVATES",
                     "cardinality": "0..*", "transitive": False},
    "OPERATIONALIZED_AS": {"definition": "问题任务化", "inverse": "OPERATIONALIZES",
                           "cardinality": "0..*", "transitive": False},
    "ADDRESSED_BY": {"definition": "任务所用方法", "inverse": "ADDRESSES_TASK",
                     "cardinality": "0..*", "transitive": False},
    "IMPLEMENTS": {"definition": "流程实现/调用方法", "inverse": "IMPLEMENTED_BY",
                   "cardinality": "0..*", "transitive": False},
    "PROPOSES_WORKFLOW": {"definition": "论文报告流程", "inverse": "WORKFLOW_OF",
                          "cardinality": "0..*", "transitive": False},
    "ABOUT_METHOD": {"definition": "能力属于整体流程或单模型（二者必须选明确的端点）",
                     "inverse": "HAS_CLAIM_ABOUT", "cardinality": "1..*", "transitive": False},
    "HAS_CLAIM": {"definition": "论文抽取/综合的能力主张", "inverse": "CLAIM_OF_PAPER",
                  "cardinality": "0..*", "transitive": False},
    "EVALUATED_IN": {"definition": "主张对应的评测记录", "inverse": "EVALUATES",
                     "cardinality": "1..*", "transitive": False},
    "SUPPORTED_BY": {"definition": "由证据支持；不自动表示独立复现",
                     "inverse": "SUPPORTS", "cardinality": "1..*", "transitive": False},
    "EXTRACTED_FROM": {"definition": "证据来自特定文章版本", "inverse": "HAS_EVIDENCE",
                       "cardinality": "1..1", "transitive": False},
    "USES_METRIC": {"definition": "本次评测所用指标定义", "inverse": "USED_IN",
                    "cardinality": "1..*", "transitive": False},
    "PRODUCES_OBSERVATION": {"definition": "评测产生观测", "inverse": "OBSERVED_IN",
                             "cardinality": "1..*", "transitive": False},
    "OF_METRIC": {"definition": "观测属于某指标定义", "inverse": "HAS_OBSERVATION",
                  "cardinality": "1..1", "transitive": False},
    "HAS_CONDITION": {"definition": "评测/观测的适用条件", "inverse": "CONDITION_OF",
                      "cardinality": "1..*", "transitive": False},
    "HAS_ASSAY": {"definition": "评测所用测定方法", "inverse": "ASSAY_OF",
                  "cardinality": "0..*", "transitive": False},
    "MEASURES_ENDPOINT": {"definition": "测定方法测量的实际终点", "inverse": "ENDPOINT_OF",
                          "cardinality": "0..*", "transitive": False},
    "ABOUT_SUBJECT": {"definition": "观测对象（单分子/候选集/模型）", "inverse": "SUBJECT_OF",
                      "cardinality": "0..*", "transitive": False},
    "FOR_TARGET": {"definition": "观测所针对的靶点", "inverse": "TARGET_OF",
                   "cardinality": "0..*", "transitive": False},
    "USES_DATASET": {"definition": "流程/评测使用数据集", "inverse": "DATASET_USED_BY",
                     "cardinality": "0..*", "transitive": False},
    "HAS_SPLIT": {"definition": "数据集的划分声明", "inverse": "SPLIT_OF",
                  "cardinality": "0..*", "transitive": False},
    "QUALIFIES": {"definition": "局限限制主张范围", "inverse": "QUALIFIED_BY",
                  "cardinality": "0..*", "transitive": False},
    "BROADER": {"definition": "子问题归属问题分类（可传递）", "inverse": "NARROWER",
                "cardinality": "0..1", "transitive": True},
    "ADDRESSES": {"definition": "论文明确尝试缓解该子问题；不蕴含已解决",
                  "inverse": "ADDRESSED_BY_PAPER", "cardinality": "0..*", "transitive": False},
    "EXPOSES_LIMITATION": {"definition": "原文明确提供该问题未被解决的证据",
                           "inverse": "LIMITATION_EXPOSED_BY", "cardinality": "0..*",
                           "transitive": False},
    "ANALYST_RELEVANT_TO": {"definition": "分析者关联，不是作者声明",
                            "inverse": "HAS_ANALYST_LINK", "cardinality": "0..*",
                            "transitive": False},
    "HAS_CODE": {"definition": "论文/流程/算法对应的源码资源", "inverse": "CODE_OF",
                 "cardinality": "0..*", "transitive": False},
    "HAS_WEIGHTS": {"definition": "权重资源（许可可能与源码不同）", "inverse": "WEIGHTS_OF",
                    "cardinality": "0..*", "transitive": False},
    "HAS_DATA": {"definition": "共享数据资源", "inverse": "DATA_OF",
                 "cardinality": "0..*", "transitive": False},
    "MEMBER_OF": {"definition": "论文属于某证据依赖组", "inverse": "HAS_MEMBER",
                  "cardinality": "0..*", "transitive": False},
    "REPORTS_CAMPAIGN": {"definition": "论文报告具体设计活动", "inverse": "CAMPAIGN_IN",
                         "cardinality": "0..*", "transitive": False},
    "HAS_STAGE": {"definition": "设计活动的筛选阶段", "inverse": "STAGE_OF",
                  "cardinality": "0..*", "transitive": False},
    "HAS_NEGATIVE_OUTCOME": {"definition": "设计活动的失败/负结果", "inverse": "NEGATIVE_OF",
                             "cardinality": "0..*", "transitive": False},
    "HAS_OBJECTIVE": {"definition": "流程/活动的优化目标或约束", "inverse": "OBJECTIVE_OF",
                      "cardinality": "0..*", "transitive": False},
    "HAS_STATE": {"definition": "分子的构象/质子化/复合状态", "inverse": "STATE_OF",
                  "cardinality": "0..*", "transitive": False},
    "ON_ORGANISM": {"definition": "评测/靶点对应的物种或菌株", "inverse": "ORGANISM_OF",
                    "cardinality": "0..*", "transitive": False},
    "CORRECTED_BY": {"definition": "版本被正式更正通知修订", "inverse": "CORRECTS",
                     "cardinality": "0..1", "transitive": False},
    "EVALUATED_ON": {"definition": "论文/代码在该基准上评测", "inverse": "HAS_EVALUATOR",
                     "cardinality": "0..*", "transitive": False},
    "BENCHMARK_FOR": {"definition": "基准对应的研究问题", "inverse": "HAS_BENCHMARK",
                      "cardinality": "0..*", "transitive": False},
    "HAS_LEADERBOARD": {"definition": "基准下的成绩条目", "inverse": "LEADERBOARD_OF",
                        "cardinality": "0..*", "transitive": False},
    "REPORTED_BY": {"definition": "成绩由某论文/代码报告", "inverse": "REPORTS_RESULT",
                    "cardinality": "0..1", "transitive": False},
    "FROM_OBSERVATION": {"definition": "成绩来自某条原始观测", "inverse": "YIELDS_ENTRY",
                         "cardinality": "1..1", "transitive": False},
    "IN_DOMAIN": {"definition": "节点属于某应用领域（多标签）", "inverse": "HAS_MEMBER_NODE",
                  "cardinality": "0..*", "transitive": False},
    "USES_ALGO_FAMILY": {"definition": "节点使用某算法族（多标签）", "inverse": "USED_BY_NODE",
                         "cardinality": "0..*", "transitive": False},
}

# ---------------------------------------------------------------------------
# 3. 推理规则（确定性，供推理器与 LLM 共用）
# ---------------------------------------------------------------------------
INFERENCE_RULES: Tuple[Dict[str, Any], ...] = (
    {"id": "R1", "name": "领域继承到主张",
     "if": "Paper IN_DOMAIN D ∧ Paper HAS_CLAIM C", "then": "C IN_DOMAIN D",
     "kind": "deterministic", "used_by": ["reasoning"]},
    {"id": "R2", "name": "算法族继承到主张",
     "if": "Paper USES_ALGO_FAMILY A ∧ Paper HAS_CLAIM C", "then": "C USES_ALGO_FAMILY A",
     "kind": "deterministic", "used_by": ["reasoning"]},
    {"id": "R3", "name": "架构映射算法族",
     "if": "Algorithm.architecture ∈ ALGORITHM_FAMILY_TO_CODE", "then": "Algorithm USES_ALGO_FAMILY A",
     "kind": "deterministic", "used_by": ["reasoning"]},
    {"id": "R4", "name": "问题层级传递",
     "if": "P1 BROADER P2 ∧ P2 BROADER P3", "then": "P1 BROADER P3",
     "kind": "deterministic", "used_by": ["reasoning"]},
    {"id": "R5", "name": "可比性分组",
     "if": "O1,O2 均为 MetricObservation 且可比键 15 维全等", "then": "O1,O2 可同组排序",
     "kind": "deterministic", "used_by": ["reasoning", "gap_discovery"]},
    {"id": "R6", "name": "领域空覆盖",
     "if": "Domain D 的论文数为 0", "then": "报告 D 为覆盖空白",
     "kind": "heuristic", "used_by": ["gap_discovery"]},
    {"id": "R7", "name": "论文宣称但代码缺失",
     "if": "Paper HAS_CLAIM C ∧ C 无 REALIZES/无对应 Algorithm 实现 ∧ Paper 无 HAS_CODE",
     "then": "报告复现缺口", "kind": "heuristic", "used_by": ["gap_discovery"]},
    {"id": "R8", "name": "指标未测",
     "if": "MetricObservation.missing_state ∈ {not_measured, not_reported}",
     "then": "该指标不可进入比较与结论", "kind": "deterministic", "used_by": ["reasoning"]},
    {"id": "R9", "name": "证据层级不可合并",
     "if": "O1.modality ≠ O2.modality", "then": "不得把两者压成单一总分",
     "kind": "deterministic", "used_by": ["reasoning", "summarization"]},
    {"id": "R10", "name": "共享平台非独立复现",
     "if": "P1,P2 MEMBER_OF 同一 EvidenceFamily 且 independence_status=shared_platform",
     "then": "P1,P2 不构成两次独立验证", "kind": "deterministic", "used_by": ["reasoning"]},
)

# ---------------------------------------------------------------------------
# 4. 任务协议（给 LLM 的输入/输出契约 + 后置校验）
# ---------------------------------------------------------------------------
TASK_PROTOCOLS: Dict[str, Dict[str, Any]] = {
    "extraction": {
        "goal": "从论文/代码片段抽取 PO 五维概念，输出结构化 JSON",
        "input": ["text", "paper_id", "paper_version_id", "evidence_locator"],
        "output_schema": {
            "nodes": [{"id": "str", "type": "concept_class", "label": "str",
                       "attrs": "object", "attribution": "attribution",
                       "evidence_ids": ["str"]}],
            "assertions": [{"source": "str", "target": "str", "relation": "relation_type",
                            "attribution": "attribution", "evidence_ids": ["str"]}],
        },
        "rules": ["每个节点必须有 evidence_ids 或 attribution",
                  "数值必须带 unit；无值写 missing_state",
                  "不得编造 DOI / 页码 / registry ID",
                  "关系必须满足 domain/range"],
        "post_checks": ["validate_po_graph", "Concept.validate", "vocab.normalize"],
    },
    "reasoning": {
        "goal": "在给定子图上回答问题（可比性、归属、证据链、领域-算法关系）",
        "input": ["question", "context_pack"],
        "output_schema": {"answer": "str", "citations": ["node_id"],
                          "inferences": [{"rule_id": "R1..R10", "statement": "str"}],
                          "uncertainty": "str"},
        "rules": ["结论必须引用节点 ID", "区分 author_* 与 analyst_* 归属",
                  "不可比观测不得给出大小比较", "缺失不得当作 0/阴性"],
        "post_checks": ["citation_exists", "rule_id_valid"],
    },
    "gap_discovery": {
        "goal": "发现证据/实现/覆盖缺口并排序",
        "input": ["graph_stats", "coverage_matrix"],
        "output_schema": {"gaps": [{"type": "gap_type", "object": "str", "severity": "high|medium|low",
                                    "evidence": ["node_id"], "rationale": "str",
                                    "suggested_action": "str"}]},
        "rules": ["每个缺口必须指向具体节点", "严重度依据：无实现 > 无评测 > 无证据 > 覆盖空白",
                  "不得把「未抽取」当成「不存在」"],
        "post_checks": ["object_exists", "severity_in_vocab"],
    },
    "summarization": {
        "goal": "按领域/算法族/问题生成结构化摘要",
        "input": ["scope", "graph_stats", "selected_nodes"],
        "output_schema": {"summary": "str", "key_counts": "object",
                          "notable_claims": ["str"], "caveats": ["str"]},
        "rules": ["数字必须来自统计而不是估计", "保留 modality 分层，不压总分",
                  "标注覆盖边界（未抽取/未读到）"],
        "post_checks": ["counts_match_stats"],
    },
}


# ---------------------------------------------------------------------------
# 5. 语义包
# ---------------------------------------------------------------------------
@dataclass
class SemanticBundle:
    """完整本体语义包。"""

    version: str = ONTOLOGY_VERSION
    namespace: str = NAMESPACE
    description: str = ("问题导向多肽/药物发现本体：问题—知识—算法数据—代码—指标—分类六维，"
                        "以证据与归属为中心，缺失不是 false。")
    classes: List[Dict[str, Any]] = field(default_factory=list)
    relations: List[Dict[str, Any]] = field(default_factory=list)
    vocabularies: Dict[str, Any] = field(default_factory=dict)
    keywords: Dict[str, Any] = field(default_factory=dict)
    inference_rules: List[Dict[str, Any]] = field(default_factory=list)
    task_protocols: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_jsonld_context(self) -> Dict[str, Any]:
        ctx: Dict[str, Any] = {"@version": 1.1, "@vocab": self.namespace,
                               "label": "http://www.w3.org/2000/01/rdf-schema#label",
                               "definition": "http://www.w3.org/2004/02/skos/core#definition"}
        for c in self.classes:
            ctx[c["id"]] = {"@id": f"{self.namespace}{c['id']}", "@type": "@id"}
        for r in self.relations:
            ctx[r["id"]] = {"@id": f"{self.namespace}{r['id']}", "@type": "@id"}
        return {"@context": ctx}

    def to_owl_turtle(self) -> str:
        ns = self.namespace.rstrip("#") + "#"
        lines = [f"@prefix po: <{ns}> .",
                 "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
                 "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
                 "@prefix skos: <http://www.w3.org/2004/02/skos/core#> .",
                 "", f"<{ns.rstrip('#')}> a owl:Ontology ;",
                 f'    rdfs:label "PO Ontology {self.version}" ;',
                 f'    owl:versionInfo "{self.version}" .', ""]
        for c in self.classes:
            lines.append(f"po:{c['id']} a owl:Class ;")
            lines.append(f'    rdfs:label "{c["label"]}"@zh ;')
            lines.append(f'    skos:definition """{c["definition"]}"""@zh .')
        for r in self.relations:
            lines.append(f"po:{r['id']} a owl:ObjectProperty ;")
            lines.append(f'    rdfs:label "{r["id"]}" ;')
            lines.append(f'    skos:definition """{r["definition"]}"""@zh ;')
            if r.get("domain"):
                lines.append(f"    rdfs:domain po:{r['domain'][0]} ;")
            if r.get("range"):
                lines.append(f"    rdfs:range po:{r['range'][0]} ;")
            lines[-1] = lines[-1].rstrip(" ;") + " ."
        return "\n".join(lines) + "\n"


def build_bundle(*, include_vocab: bool = True) -> SemanticBundle:
    """组装语义包（概念定义 + 关系语义 + 词表 + 关键词 + 规则 + 协议）。"""
    classes: List[Dict[str, Any]] = []
    for name, spec in CONCEPT_SPECS.items():
        sem = CONCEPT_SEMANTICS.get(name, {})
        classes.append({
            "id": name,
            "label": sem.get("label") or name,
            "dimension": spec.dimension,
            "dimension_label": DIMENSIONS.get(spec.dimension, ""),
            "definition": sem.get("definition") or spec.definition,
            "not_scope": sem.get("not_scope", ""),
            "required": list(spec.required),
            "recommended": list(spec.recommended),
            "vocab_bindings": dict(spec.vocab),
            "constraints": sem.get("constraints", []),
            "examples": sem.get("examples", []),
            "llm_hint": sem.get("llm_hint", ""),
            "synonyms": sem.get("synonyms", []),
        })
    relations: List[Dict[str, Any]] = []
    for rid, (dom, rng) in RELATION_DOMAIN_RANGE.items():
        sem = RELATION_SEMANTICS.get(rid, {})
        relations.append({
            "id": rid, "definition": sem.get("definition", rid),
            "domain": list(dom), "range": list(rng),
            "inverse": sem.get("inverse", ""),
            "cardinality": sem.get("cardinality", "0..*"),
            "transitive": bool(sem.get("transitive", False)),
        })
    return SemanticBundle(
        classes=classes, relations=relations,
        vocabularies=default_registry.to_dict() if include_vocab else {},
        keywords=keyword_table(),
        inference_rules=[dict(r) for r in INFERENCE_RULES],
        task_protocols=dict(TASK_PROTOCOLS),
    )


def bundle_summary(bundle: SemanticBundle) -> Dict[str, Any]:
    return {
        "version": bundle.version, "namespace": bundle.namespace,
        "n_classes": len(bundle.classes), "n_relations": len(bundle.relations),
        "n_vocabularies": len(bundle.vocabularies),
        "n_inference_rules": len(bundle.inference_rules),
        "n_task_protocols": len(bundle.task_protocols),
        "keyword_stats": keyword_stats(),
        "dimensions": {k: sum(1 for c in bundle.classes if c["dimension"] == k)
                       for k in DIMENSIONS},
        "classes_without_definition": [c["id"] for c in bundle.classes
                                       if not c["definition"].strip()],
    }


# ---------------------------------------------------------------------------
# 6. LLM 上下文打包
# ---------------------------------------------------------------------------
def _node_brief(n: Any) -> Dict[str, Any]:
    return {"id": n.id, "type": n.type,
            "label": (n.label or "")[:80],
            "definition": CONCEPT_SEMANTICS.get(n.type, {}).get("definition", "")[:80],
            "attrs": {k: v for k, v in list(n.attrs.items())[:8]
                      if isinstance(v, (str, int, float, bool))},
            "attribution": n.attribution}


def context_pack(graph: Any, *, task: str = "reasoning", focus: str = "",
                 max_nodes: int = 40, max_edges: int = 80) -> Dict[str, Any]:
    """为 LLM 组装一个受预算控制的上下文（schema + 子图 + 统计 + 指令）。

    选择策略：``focus`` 名称/标签包含匹配 → 1 跳邻域扩展 → 按度数排序截断。
    """
    bundle = build_bundle(include_vocab=False)
    focus_low = (focus or "").lower()

    seeds: List[str] = []
    if graph is not None:
        for n in graph.nodes.values():
            if not focus_low:
                continue
            hay = f"{n.id} {n.label} {' '.join(str(v) for v in n.attrs.values())}".lower()
            if focus_low in hay:
                seeds.append(n.id)
    if not seeds and graph is not None:
        # 无 focus 时取度数最高的节点作为代表
        deg: Dict[str, int] = {}
        for e in graph.assertions:
            deg[e.source] = deg.get(e.source, 0) + 1
            deg[e.target] = deg.get(e.target, 0) + 1
        seeds = [k for k, _ in sorted(deg.items(), key=lambda kv: -kv[1])[:5]]

    selected: List[str] = []
    if graph is not None:
        for sid in seeds:
            if sid not in selected:
                selected.append(sid)
            for nid, _ in graph.neighbours(sid, hops=1):
                if nid not in selected:
                    selected.append(nid)
            if len(selected) >= max_nodes:
                break
        selected = selected[:max_nodes]

    nodes = [_node_brief(graph.nodes[n]) for n in selected
             if n in graph.nodes] if graph is not None else []
    sel = set(selected)
    edges = [{"source": e.source, "target": e.target, "relation": e.relation,
              "attribution": e.attribution, "evidence_ids": e.evidence_ids[:3]}
             for e in (graph.assertions if graph is not None else [])
             if e.source in sel and e.target in sel][:max_edges]

    protocol = TASK_PROTOCOLS.get(task, TASK_PROTOCOLS["reasoning"])
    return {
        "task": task,
        "focus": focus,
        "ontology": {"version": bundle.version, "namespace": bundle.namespace,
                     "n_classes": len(bundle.classes), "n_relations": len(bundle.relations)},
        "schema": {
            "classes": [{k: c[k] for k in ("id", "definition", "required",
                                           "vocab_bindings", "llm_hint")}
                        for c in bundle.classes],
            "relations": [{k: r[k] for k in ("id", "domain", "range", "definition")}
                          for r in bundle.relations],
            "rules": bundle.inference_rules,
        },
        "subgraph": {"nodes": nodes, "edges": edges,
                     "truncated": len(nodes) >= max_nodes},
        "stats": getattr(graph, "stats", lambda: {})(),
        "instructions": {
            "goal": protocol["goal"],
            "output_schema": protocol["output_schema"],
            "rules": protocol["rules"],
            "post_checks": protocol["post_checks"],
            "attribution_policy": ("作者声称用 author_*，分析者推断用 analyst_*；"
                                   "缺失用 missing_state，禁止填 0/false。"),
        },
    }
