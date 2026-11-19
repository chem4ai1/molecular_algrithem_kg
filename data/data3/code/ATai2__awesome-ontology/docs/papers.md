# 本体工程最新研究方向与论文

本页面按领域整理本体工程（Ontology Engineering）的最新研究方向与代表性论文，便于追踪学术前沿。

---

## 目录

- [LLM 与本体工程](#llm-与本体工程)
- [本体学习与抽取](#本体学习与抽取)
- [本体匹配与对齐](#本体匹配与对齐)
- [本体质量评估与调试](#本体质量评估与调试)
- [本体形式化与推理](#本体形式化与推理)
- [知识图谱与本体构建](#知识图谱与本体构建)
- [领域本体应用](#领域本体应用)
- [本体演化与模块化](#本体演化与模块化)

---

## LLM 与本体工程

大语言模型（LLM）正在深刻改变本体工程的各个环节，从需求分析到本体生成、评估与扩展。

### 本体生成与扩展

- [OntoExtend: A Framework for Requirement-driven and Scalable Ontology Extension with LLMs](https://arxiv.org/abs/2607.17963) - 基于需求驱动的 LLM 本体扩展框架，使用 RAG 从已有本体和能力问题中检索相关片段进行扩展（Lippolis 等，2026）
- [Extended NeOn-GPT: Advancing LLM-Powered Ontology Learning Through Ontology Reuse and Automated Verification](https://doi.org/10.1177/22104968261453138) - 扩展 NeOn-GPT 流程，结合本体复用与自动化验证的 LLM 本体学习框架，跨四个领域评估（Fathallah 等，2026）
- [Ontology Population Using LLMs: Which Factors Matter?](https://link.springer.com/book/10.1007/978-3-032-25156-5) - ESWC 2026 论文，研究 LLM 本体填充的关键影响因素（Bhattacharya 等，2026）

### LLM 规模与本体学习

- [When Does Bigger Help? A Controlled Study of LLM Scale for Ontology Learning](https://arxiv.org/abs/2608.31118) - 控制实验评估 13 个模型在本体学习任务上的表现，发现模型规模并非唯一选择标准（Giglou 等，WOP 2026）
- [pro-team at LLMs4OL 2026 Tasks: RAG and Vocabulary-Constrained Filtering for Ontology Learning](https://arxiv.org/abs/2608.27101) - LLMs4OL 2026 挑战赛方案，使用 RAG 与词汇约束过滤进行本体学习（Mishra 等，2026）

### LLM 辅助本体匹配

- [Surprising Effectiveness of Self-Demonstrations in Enhancing Schema-Ontology Mapping with LLMs](https://arxiv.org/abs/2609.13776) - 自演示驱动的神经符号方法，用于 Schema 到本体的映射，F1 提升 25 个百分点（Thombre 等，2026）

---

## 本体学习与抽取

从文本、数据或已有知识中自动或半自动构建本体的技术。

### 文本到本体

- [LLMs4OL Challenge（官方仓库）](https://github.com/sciknoworg/LLMs4OL-Challenge) - LLM 本体学习年度共享任务，含术语类型化、分类发现与非分类关系抽取三个赛道
- [LLMs4OL 任务官网](https://hamedbabaei.github.io/LLMs4OL/) - 任务定义、数据集与历年排行榜入口
- [Text2KGBench（IBM）](https://github.com/IBM/Text2KGBench) - 文本到知识图谱生成的评测基准，含本体驱动的任务定义

### 本体学习工具

- [OntoGPT（Monarch Initiative）](https://github.com/monarch-initiative/ontogpt) - 用 LLM 从文本抽取结构化知识并链接到本体的工具集
- [Onto-learn（DICE Group）](https://github.com/dice-group/Onto-learn) - 基于描述逻辑的本体学习库，支持符号式类表达式学习
- [DL-Learner](http://dl-learner.org/) - 经典的本体学习框架，从数据中归纳类表达式

---

## 本体匹配与对齐

解决异构本体之间的语义映射问题。

### 评测与基准

- [OAEI（Ontology Alignment Evaluation Initiative）](http://oaei.ontologymatching.org/) - 本体匹配领域唯一的年度权威评测，含解剖学、会议、大规模生物医学等赛道

### 匹配系统

- [AgreementMakerLight（AML）](https://github.com/AgreementMakerLight/AML) - 自动化本体匹配系统，OAEI 长期参赛者
- [LogMap](https://github.com/ernestojimenezruiz/logmap-matcher) - 具备不一致性修复能力的本体匹配系统
- [OntoAligner（PyPI）](https://pypi.org/project/OntoAligner/) - 模块化本体对齐工具包，整合检索式与 LLM 匹配器

---

## 本体质量评估与调试

确保本体建模正确性、发现并修复缺陷。

### 质量评估框架

- [Ontology Quality Improvement in the Semantic Web: Evidence from Educational Knowledge Graphs](https://doi.org/10.3390/systems14020154) - 基于 ML 的本体质量评估与改进框架，结构精度 93.5%，语义精度 90.2%（Jaziri & Sassi，2026）
- [OOPS!（OntOlogy Pitfall Scanner）](http://oops.linkeddata.es/) - 在线本体缺陷扫描器，输出常见建模陷阱清单
- [ROBOT Report](http://robot.obolibrary.org/report) - 命令行本体体检，检查缺失标签、重复定义与 OBO 原则

### 评测基准

- [OQuaRE 本体质量评价文献（Semantic Scholar）](https://www.semanticscholar.org/search?q=OQuaRE%20ontology%20quality) - 基于 SQuaRE 的本体质量度量方法论文入口

---

## 本体形式化与推理

本体的形式语义、描述逻辑推理与规则系统。

### 规则与推理

- [Recovering Explanations from Transformed Rule-Based Ontologies](https://arxiv.org/abs/2608.06399) - 研究规则本体变换后的证明树恢复问题，建立计算复杂性（Ivliev 等，ISWC 2026）

### 推理机

- [HermiT](http://www.hermit-reasoner.com/) - 基于 hypertableau 的完备 OWL 推理机
- [ELK](https://github.com/liveontologies/elk-reasoner) - 面向 OWL 2 EL 的高性能推理机
- [Konclude](https://github.com/konclude/Konclude) - C++ 实现的高性能推理机，支持并发推理
- [RDFox](https://www.oxfordsemantic.tech/product) - 内存推理型三元组库，支持 Datalog 规则与 OWL 2 RL

---

## 知识图谱与本体构建

利用本体作为知识图谱的语义骨架，构建与维护大规模知识库。

### 知识图谱构建

- [Evaluating Knowledge Graph Construction from Text Without Supervision](https://link.springer.com/book/10.1007/978-3-032-25156-5) - ESWC 2026 论文，无监督文本到知识图谱构建评估（Lermanda 等，2026）
- [Structure is the Signal: Graph Encodings and GNNs for Constraint Repair in Collaborative KGs](https://link.springer.com/book/10.1007/978-3-032-25156-5) - 使用图神经网络修复协作知识图谱中的约束（Vázquez 等，ESWC 2026）

### 知识图谱嵌入

- [Link Prediction or Perdition: The Seeds of Instability in Knowledge Graph Embeddings](https://link.springer.com/book/10.1007/978-3-032-25156-5) - 知识图谱嵌入不稳定性的研究（Méroué 等，ESWC 2026）
- [Integrating Meta-features with Knowledge Graph Embeddings for Meta-learning](https://link.springer.com/book/10.1007/978-3-032-25156-5) - 结合元特征与知识图谱嵌入的元学习方法（Klironomos 等，ESWC 2026）

---

## 领域本体应用

本体在特定领域的应用实践。

### 生物医学

- [OBO Foundry](https://obofoundry.org/) - 生命科学本体的协调组织，遵循统一原则的可互操作本体集合
- [Gene Ontology（GO）](http://geneontology.org/) - 基因功能、生物过程与细胞组分的权威本体
- [MONDO Disease Ontology](https://mondo.monarchinitiative.org/) - 整合多源疾病术语的疾病本体

### 教育

- [Ontology Quality Improvement in the Semantic Web: Evidence from Educational Knowledge Graphs](https://doi.org/10.3390/systems14020154) - 教育知识图谱的本体质量改进框架（Jaziri & Sassi，2026）

### 工业

- [Industrial Ontologies Foundry（IOF）](https://www.industrialontologies.org/) - 制造业本体工厂，含核心本体、供应链、维护等系列
- [EMMO（European Materials and Modelling Ontology）](https://github.com/emmo-repo/EMMO) - 材料与建模本体

---

## 本体演化与模块化

本体随时间变化的管理与模块化抽取。

### 模块化

- [Ontology Modularization 文献（Semantic Scholar）](https://www.semanticscholar.org/search?q=ontology%20modularization) - 本体模块抽取与复用方向的研究入口
- [ROBOT Extract](http://robot.obolibrary.org/extract) - 模块抽取与 MIREOT 实现，从大本体中取子集

### 版本管理

- [ROBOT Diff](http://robot.obolibrary.org/diff) - 两个本体版本的结构化差异比对
- [Semantic Versioning for Ontologies（OBO 原则索引）](https://obofoundry.org/principles/) - 本体版本管理与发布原则

---

## 主要会议与期刊

追踪最新论文的推荐来源：

### 会议

- [ISWC（International Semantic Web Conference）](https://en.wikipedia.org/wiki/International_Semantic_Web_Conference) - 语义网领域最高级别会议
- [ESWC（Extended Semantic Web Conference）](https://dblp.org/db/conf/esws/index.html) - 欧洲语义网会议
- [FOIS（Formal Ontology in Information Systems）](https://dblp.org/db/conf/fois/index.html) - 形式本体论旗舰会议
- [ICBO（International Conference on Biomedical Ontology）](https://dblp.org/db/conf/icbo/index.html) - 生物医学本体年会
- [WOP（Workshop on Ontology Design and Patterns）](https://dblp.org/db/conf/semweb/) - 本体设计模式研讨会
- [CCKS（全国知识图谱与语义计算大会）](http://www.cipsc.org.cn/) - 中文知识图谱领域主会

### 期刊

- [Semantic Web Journal](http://www.semantic-web-journal.net/) - 语义网领域专门期刊，开放获取
- [Journal of Web Semantics](https://www.sciencedirect.com/journal/journal-of-web-semantics) - Elsevier 旗下老牌期刊
- [Applied Ontology](https://content.iospress.com/journals/applied-ontology) - IOS Press 期刊，专注本体应用
- [Journal of Biomedical Semantics](https://jbiomedsem.biomedcentral.com/) - 生物医学语义与本体期刊
- [Data Intelligence](https://direct.mit.edu/dint) - MIT Press 期刊，知识图谱与数据智能方向

### 论文检索

- [Semantic Scholar - 本体工程](https://www.semanticscholar.org/search?q=ontology%20engineering) - 本体工程论文检索入口
- [Semantic Scholar - LLM 本体生成](https://www.semanticscholar.org/search?q=ontology%20generation%20large%20language%20models) - LLM 本体生成研究入口
- [DBLP - 语义网](https://dblp.org/db/conf/semweb/) - 语义网会议论文索引
- [CEUR Workshop Proceedings](https://ceur-ws.org/) - 研讨会论文的开放出版平台

---

*最后更新：2026-09-17*
