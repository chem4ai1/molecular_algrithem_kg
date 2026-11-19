# Awesome Ontology

[![Awesome](https://awesome.re/badge.svg)](https://awesome.re)
[![License: CC0-1.0](https://img.shields.io/badge/License-CC0--1.0-lightgrey.svg)](https://creativecommons.org/publicdomain/zero/1.0/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Link Check](https://github.com/awesome-ontology/awesome-ontology/actions/workflows/link-check.yml/badge.svg)](https://github.com/awesome-ontology/awesome-ontology/actions/workflows/link-check.yml)


一份面向中文读者的**本体工程（Ontology Engineering）**资源清单：从顶层本体、领域词表、标准规范，到建模工具、推理机、质量评估，再到近年的 LLM 辅助建模与本体学习。

本体是语义网与知识图谱的骨架。但这片领域资料分散：W3C 规范、OBO 社区、生物医学本体、工业本体、描述逻辑论文、各种工具与平台各自成体系，新手往往不知道从哪读起、哪个工具还在维护。本清单试图把**现在仍然可用、值得投入时间**的资源按主题组织起来，每条附带一句话说明它解决什么问题。

内容以英文一手资料为主（这是该领域的现实），说明文字为中文；对中文社区资源（OpenKG、CCKS、术语标准等）单独设了一节。

<!-- START_TOC -->

- [入门](#入门)
  - [什么是本体](#什么是本体)
  - [在线教程](#在线教程)
  - [课程](#课程)
  - [书籍与教材](#书籍与教材)
  - [术语速查](#术语速查)
- [本体与词表资源](#本体与词表资源)
  - [顶层与基础本体](#顶层与基础本体)
  - [通用词表与元数据](#通用词表与元数据)
  - [生命科学与生物医学](#生命科学与生物医学)
  - [地理空间与环境](#地理空间与环境)
  - [工业与制造](#工业与制造)
  - [金融、法律与政务](#金融法律与政务)
  - [学术出版与科研](#学术出版与科研)
  - [农业与食品](#农业与食品)
  - [其他垂直领域](#其他垂直领域)
  - [中文与国产资源](#中文与国产资源)
- [标准与规范](#标准与规范)
  - [W3C 标准](#w3c-标准)
  - [ISO 与国家标准](#iso-与国家标准)
  - [社区规范与最佳实践](#社区规范与最佳实践)
- [本体仓库与检索平台](#本体仓库与检索平台)
- [工具链](#工具链)
  - [编辑器与建模环境](#编辑器与建模环境)
  - [命令行与开发套件](#命令行与开发套件)
  - [推理机](#推理机)
  - [编程库](#编程库)
  - [可视化](#可视化)
  - [文档生成与发布](#文档生成与发布)
  - [质量评估与诊断](#质量评估与诊断)
  - [匹配与对齐](#匹配与对齐)
  - [本体学习、抽取与 LLM 辅助建模](#本体学习抽取与-llm-辅助建模)
  - [版本、差异与模块化](#版本差异与模块化)
  - [本体数据访问与映射（OBDA）](#本体数据访问与映射obda)
  - [三元组库与查询引擎](#三元组库与查询引擎)
- [方法论](#方法论)
- [基准数据集与评测](#基准数据集与评测)
- [社区与活动](#社区与活动)
  - [会议与研讨会](#会议与研讨会)
  - [期刊](#期刊)
  - [组织与社区](#组织与社区)
  - [代表人物](#代表人物)
  - [博客与 Newsletter](#博客与-newsletter)
- [最新研究论文](#最新研究论文)
- [相关 Awesome 列表](#相关-awesome-列表)
- [贡献](#贡献)
- [许可证](#许可证)

<!-- END_TOC -->

## 入门

刚接触本体：先看「什么是本体」建立概念，再按「在线教程」动手，需要系统学习时看课程与书籍。已有基础、只想找工具或本体，直接从目录跳到对应小节。

### 什么是本体

- [Ontology（information science）- Wikipedia](https://en.wikipedia.org/wiki/Ontology_(information_science)) - 本体在信息科学中的定义、分类与历史，最快的全局概览
- [Semantic Web - Wikipedia](https://en.wikipedia.org/wiki/Semantic_web) - 语义网技术栈全景，便于定位本体所处的位置
- [Linked Data - Design Issues（Tim Berners-Lee）](https://www.w3.org/DesignIssues/LinkedData.html) - 关联数据的五星模型与设计原则，理解"为什么要发布本体"的底层文档
- [Buffalo Ontology Site（Barry Smith）](https://ontology.buffalo.edu/smith/) - 本体论与本体工程领域最具个人色彩的文献集散地，含大量可下载讲义
- [OBO Foundry Principles](https://obofoundry.org/principles/fp-000-summary.html) - 社区驱动的本体开发原则，是"什么样的本体算好本体"的实操答案
- [FAIR Principles（GO FAIR）](https://www.go-fair.org/fair-principles/) - 可发现、可访问、可互操作、可复用四原则，本体发布的评价基准

### 在线教程

- [W3C RDF 1.1 Primer](https://www.w3.org/TR/rdf11-primer/) - 三元组与图模型入门，本体的一切都建立在这层之上
- [W3C OWL 2 Primer](https://www.w3.org/TR/owl2-primer/) - OWL 2 的官方入门文档，讲清类、属性、公理与推理的关系
- [W3C SPARQL 1.1 Overview](https://www.w3.org/TR/sparql11-overview/) - 查询语言规范总览，含查询与更新两部分入口
- [W3C SKOS Primer](https://www.w3.org/TR/skos-primer/) - 叙词表与受控词表如何用 SKOS 表达，做分类体系的必读
- [JSON-LD 官网](https://json-ld.org/) - 在 JSON 中表达本体的规范与 Playground，工程落地最常用语法
- [Ontology Development 101（Noy & McGuinness）](https://protege.stanford.edu/publications/ontology_development/ontology101.pdf) - 二十多年仍在被引用的本体建模入门 PDF，两小时可读完
- [OBO Academy Book](https://oboacademy.github.io/obook/) - 生命科学本体的官方教程，实际上也覆盖了 ROBOT、语义工程等通用实践
- [Linked Data 指南与教程（linkeddata.org）](https://www.linkeddata.org/) - 关联数据发布的学习资源聚合
- [Best Practices for Publishing Linked Data（W3C）](https://www.w3.org/TR/ld-bp/) - URI 设计、内容协商、词表复用的官方建议

### 课程

- [Stanford CS520 知识图谱](https://web.stanford.edu/class/cs520/) - 斯坦福知识图谱研究生课程，课件与作业公开
- [Buffalo 本体与本体论课程资料](https://ontology.buffalo.edu/) - Barry Smith 团队课程主页，偏形式本体与生物医学应用
- [中国大学 MOOC 知识图谱课程](https://www.icourse163.org/search.htm?search=%E7%9F%A5%E8%AF%86%E5%9B%BE%E8%B0%B1) - 中文慕课检索入口，适合零基础快速入门

### 书籍与教材

- [Semantic Web for the Working Ontologist（3rd ed.）](https://www.workingontologist.org/) - Allemang、Hendler、Gandon 著，把 RDFS/OWL 讲成建模模式的最佳实践书
- [Foundations of Semantic Web Technologies](https://www.routledge.com/Foundations-of-Semantic-Web-Technologies/Hitzler-Krotzsch-Rudolph/p/book/9781420090505) - Hitzler 等著，偏理论，描述逻辑与 OWL 语义讲得最严谨
- [Handbook on Ontologies（Springer 检索入口）](https://link.springer.com/search?query=Handbook%20on%20Ontologies) - Staab、Studer 主编的领域手册，检索入口可定位最新版与分册
- [Ontology Engineering 相关专著（Springer 检索入口）](https://link.springer.com/search?query=ontology%20engineering) - 本体工程教材与专著的检索入口，含开放获取版本
- [中文知识图谱图书（豆瓣检索入口）](https://book.douban.com/subject_search?search_text=%E7%9F%A5%E8%AF%86%E5%9B%BE%E8%B0%B1) - 中文教材与译作的检索入口

### 术语速查

- [W3C OWL 2 Quick Reference Guide](https://www.w3.org/TR/owl2-quick-reference/) - OWL 2 构造子的速查表，建模时最常打开的规范页
- [RDF 1.1 Concepts and Abstract Syntax](https://www.w3.org/TR/rdf11-concepts/) - IRI、字面量、数据集等基础术语的权威定义
- [W3C 标准与草案索引](https://www.w3.org/TR/) - 所有 W3C 规范的总索引，按领域过滤查找
- [术语在线](https://www.termonline.cn/) - 全国科学技术名词审定委员会的规范术语查询平台，做中文本体时对齐概念用

## 本体与词表资源

按领域组织的**可复用**本体与词表。选型时优先看：是否有稳定 URI、是否有版本发布机制、是否被主流注册中心收录。

### 顶层与基础本体

- [Basic Formal Ontology（BFO）](https://basic-formal-ontology.org/) - 被 ISO/IEC 21838-2 采纳的顶层本体，生物医学与工业界使用最广；OWL
- [SUMO（Suggested Upper Merged Ontology）](https://www.ontologyportal.org/) - 规模最大的开源顶层本体之一，含多语言映射与推理工具链；SUO-KIF/OWL
- [UFO（Unified Foundational Ontology）](https://nemo.inf.ufes.br/en/ontologies/ufo/) - NEMO 团队维护，对概念建模与 UML 映射最友好，gUFO 是其轻量 OWL 实现；OWL
- [gUFO（lightweight implementation of UFO）](https://nemo.inf.ufes.br/en/ontologies/gufo/) - 面向工程落地的 UFO 轻量版，可直接 import；OWL
- [CIDOC CRM](http://www.cidoc-crm.org/) - 文化遗产领域的 ISO 21127 标准本体，也是跨领域事件建模的参考；OWL/RDFS
- [DOLCE 与 DOLCE+DnS Ultralite（Wikipedia 概览）](https://en.wikipedia.org/wiki/DOLCE) - 认知导向的顶层本体及其描述与情境扩展，设计模式思想的重要来源；OWL
- [General Formal Ontology（GFO，Wikipedia 概览）](https://en.wikipedia.org/wiki/General_Formal_Ontology) - 莱比锡 Onto-Med 团队的三层结构顶层本体，强调范畴与层级；OWL
- [YAMATO（Yet Another More Advanced Top-level Ontology）](https://en.wikipedia.org/wiki/YAMATO_(ontology)) - 沟口理一郎提出的顶层本体，含角色与关系质量理论；OWL
- [gist（Semantic Arts）](https://www.semanticarts.com/gist/) - 面向企业的极简上层本体，约 150 个类，商业项目常用；OWL
- [OWL-Time](https://www.w3.org/TR/owl-time/) - W3C 时间本体，时间间隔与瞬时事件的标准表达；OWL
- [PROV-O](https://www.w3.org/TR/prov-o/) - W3C 溯源本体，实体、活动、代理三要素及派生关系；OWL
- [Cyc 与 OpenCyc](https://www.cyc.com/) - 历史最长的常识知识库项目，OpenCyc 是其开源顶层本体版本；CycL/OWL

### 通用词表与元数据

- [schema.org](https://schema.org/) - 搜索引擎联合推出的最大规模通用词表，网页结构化数据事实标准；RDFS/OWL
- [FOAF Vocabulary Specification](http://xmlns.com/foaf/spec/) - 人物、组织与社交关系的经典词表；RDFS/OWL
- [SKOS Simple Knowledge Organization System](https://www.w3.org/TR/skos-reference/) - 叙词表、分类法、主题词表的标准表达模型；OWL/RDFS
- [DCMI Metadata Terms](https://www.dublincore.org/specifications/dublin-core/dcmi-terms/) - 都柏林核心元数据词表，数字资源描述的基础；RDFS
- [Organization Ontology（ORG）](https://www.w3.org/TR/vocab-org/) - 组织机构与成员关系的 W3C 词表；OWL
- [Registered Organization Vocabulary（ROV）](https://www.w3.org/TR/vocab-regorg/) - 法人机构与注册信息词表，政务数据常用；OWL
- [Data Catalog Vocabulary（DCAT 3）](https://www.w3.org/TR/vocab-dcat-3/) - 数据目录描述标准，开放数据门户的通用骨架；OWL
- [DCAT-AP（欧盟）](https://semiceu.github.io/DCAT-AP/) - DCAT 的欧洲政务扩展，包含大量可复用约束；OWL/SHACL
- [VoID Vocabulary](https://www.w3.org/TR/void/) - 描述 RDF 数据集本身的词表，用于数据集互操作；RDFS
- [SIOC Core Ontology](http://rdfs.org/sioc/spec/) - 在线社区内容与交互的词表；OWL/RDFS
- [GoodRelations](http://www.heppnetz.de/ontologies/goodrelations/v1) - 电子商务产品、价格与交易条件词表，schema.org 的重要来源；OWL
- [QUDT（Quantities, Units, Dimensions and Data Types）](https://qudt.org/) - 工程与科学计量单位本体，含完整单位换算；OWL
- [Ontology of Units of Measure（OM）](http://www.ontology-of-units-of-measure.org/) - 轻量级单位与量纲本体，建模物理量的常用选择；OWL
- [SOSA/SSN](https://www.w3.org/TR/vocab-ssn/) - W3C 传感器、观测、采样与执行本体，物联网领域标准；OWL
- [SAREF（ETSI）](https://saref.etsi.org/) - 智能设备的 ETSI 标准本体，含楼宇、能源、环境等扩展域；OWL
- [Web Annotation Data Model](https://www.w3.org/TR/annotation-model/) - 标注与评论的标准模型，数据标注系统常用；OWL
- [ELI Ontology（European Legislation Identifier）](https://data.europa.eu/eli/ontology) - 法律法规的标识与结构本体；OWL

### 生命科学与生物医学

- [OBO Foundry](https://obofoundry.org/) - 生命科学本体的协调组织，遵循统一原则、可互操作的本体集合入口
- [Gene Ontology（GO）](http://geneontology.org/) - 基因功能、生物过程与细胞组分的权威本体；OWL
- [Uberon（Multi-species Anatomy Ontology）](https://github.com/obophenotype/uberon) - 跨物种解剖结构本体，表型集成的核心枢纽；OWL
- [ChEBI](https://www.ebi.ac.uk/chebi/) - 小分子化学实体本体，生物化学与药学常用；OWL
- [OBI（Ontology for Biomedical Investigations）](http://obi-ontology.org/) - 实验设计与调查过程的本体；OWL
- [PATO（Phenotype And Trait Ontology）](https://obofoundry.org/ontology/pato.html) - 表型与性状的属性词表，与 Uberon 组合使用；OWL
- [Relation Ontology（RO）](https://github.com/oborel/obo-relations) - OBO 生态的标准关系集合，跨本体对齐的基础；OWL
- [MONDO Disease Ontology](https://mondo.monarchinitiative.org/) - 疾病本体，整合多源疾病术语并映射到 OMIM、Orphanet 等；OWL
- [Human Phenotype Ontology（HPO）](https://hpo.jax.org/) - 人类表型本体，罕见病诊断与基因优先级排序的标配；OWL
- [Cell Ontology（CL）](https://obofoundry.org/ontology/cl.html) - 细胞类型本体，单细胞分析中的注释标准；OWL
- [Environment Ontology（ENVO）](https://obofoundry.org/ontology/envo.html) - 环境系统、环境材料与过程本体；OWL
- [SNOMED CT](https://www.snomed.org/) - 全球最完整的临床医学术语体系，含官方 OWL 发行版；OWL
- [Foundational Model of Anatomy（FMA，BioPortal）](https://bioportal.bioontology.org/ontologies/FMA) - 人体解剖学参考本体；OWL
- [ICD-11](https://icd.who.int/en) - WHO 国际疾病分类第十一版，含本体形式化版本；OWL/RDFS
- [MeSH](https://www.nlm.nih.gov/mesh/) - 美国国立医学图书馆主题词表，有 RDF 发行版；RDF/SKOS
- [NCI Thesaurus（NCIt）](https://bioportal.bioontology.org/ontologies/NCIT) - 癌症研究术语体系，OBO 与 NCI 双向映射；OWL
- [RxNorm](https://www.nlm.nih.gov/research/umls/rxnorm/index.html) - 临床药物标准化命名体系；RDF
- [LOINC](https://loinc.org/) - 实验室检验与临床观测代码标准；RDF/OWL
- [Uberon、GO 之外的 OBO 全量清单](https://obofoundry.org/ontologies/) - 按领域浏览上百个 OBO 本体及其活跃度指标

### 地理空间与环境

- [GeoSPARQL（OGC）](https://www.ogc.org/standard/geosparql/) - 地理空间数据的 RDF 查询与本体标准，含拓扑关系词表；OWL
- [W3C Basic Geo Vocabulary](https://www.w3.org/2003/01/geo/) - 最简经纬度表达词表，轻量场景够用；RDFS
- [SWEET Ontologies](https://sweetontology.net/) - NASA JPL 的地球与环境科学本体集合，覆盖物理、化学、生物、地学；OWL
- [INSPIRE（欧盟空间数据基础设施）](https://inspire.ec.europa.eu/) - 欧洲空间数据主题与数据规范，含大量 UML 到本体的映射；UML/OWL
- [GEMET（General Multilingual Environmental Thesaurus）](https://www.eionet.europa.eu/gemet/en/themes/) - 多语言环境叙词表，欧盟环境署维护；SKOS

### 工业与制造

- [Industrial Ontologies Foundry（IOF）](https://www.industrialontologies.org/) - 制造业本体工厂，含核心本体、供应链、维护、产品等系列；OWL
- [SOSA/SSN 物联网本体](https://www.w3.org/TR/vocab-ssn/) - 传感与观测建模，工业物联网底座；OWL
- [Asset Administration Shell（IDTA）](https://industrialdigitaltwin.org/en/content-hub/aasspecifications) - 工业数字孪生的资产管理壳规范，含本体化子模型；OWL/RDFS
- [Process Specification Language（PSL，NIST）](https://www.nist.gov/el/mbe-pmi-ontologies) - NIST 的过程规范语言，制造过程语义的早期标准；FOL/KIF
- [EMMO（European Materials and Modelling Ontology）](https://github.com/emmo-repo/EMMO) - 材料与建模本体，欧盟材料建模委员会主推；OWL
- [BattINFO](https://github.com/BIG-MAP/BattINFO) - 电池领域本体，BIG-MAP 项目维护的材料科学本体实践示例；OWL

### 金融、法律与政务

- [FIBO（Financial Industry Business Ontology）](https://github.com/edmcouncil/fibo) - EDM Council 维护的金融业业务本体，含证券、贷款、衍生品等域；OWL
- [GLEIF 法人识别（LEI 数据）](https://www.gleif.org/en/) - 全球法人识别编码体系，可与 ROV/ORG 结合做机构主数据；RDF
- [EU Vocabularies](https://op.europa.eu/en/web/eu-vocabularies) - 欧盟官方受控词表集合，含国家、语言、货币、机构等；SKOS
- [LegalRuleML（OASIS）](https://www.oasis-open.org/committees/legalruleml/) - 法律规则的形式化表达标准，可对接 LegalDocML；XML
- [LKIF（Legal Knowledge Interchange Format）](http://www.lkif.org/) - 法律知识的本体与规则表示格式，阿姆斯特丹大学成果；OWL

### 学术出版与科研

- [SPAR Ontologies（CiTO、FaBiO、BiRO 等）](https://sparontologies.github.io/) - Silvio Peroni 维护的学术出版本体族，引用关系建模首选；OWL
- [BIBO（Bibliographic Ontology）](http://bibliontology.com/) - 文献与引文书目本体；RDFS/OWL
- [BIBFRAME（美国国会图书馆）](https://www.loc.gov/bibframe/) - 面向图书馆的编目模型，MARC 的语义化替代；OWL/RDFS
- [DataCite Metadata Schema](https://schema.datacite.org/) - 科研数据引用的元数据标准；XML/JSON
- [ORCID](https://orcid.org/) - 研究者标识体系，科研知识图谱的人员对齐基础
- [FRBRoo（IFLA 概念模型）](https://www.iflastandards.info/fr/) - 书目记录的 IFLA 概念模型，文化遗产与图书馆通用；OWL

### 农业与食品

- [AGROVOC（FAO）](https://www.fao.org/agrovoc/) - 多语言农业叙词表，联合国粮农组织维护；SKOS
- [Crop Ontology](https://cropontology.org/) - 作物性状与育种本体集合；OWL/SKOS
- [FoodOn](https://foodon.org/) - 食品本体，覆盖食材、加工与食品安全；OWL
- [GACS（Global Agricultural Concept Scheme，FAO VEST Registry）](https://aims.fao.org/vest-registry) - 农业概念全局方案，CABI、FAO、GODAN 三方共建；SKOS
- [AgroPortal](http://agroportal.lirmm.fr/) - 农业与植物本体的托管与检索平台，同时提供 AGRO 本体；OWL/SKOS

### 其他垂直领域

- [Music Ontology](http://musicontology.com/) - 音乐作品、表演、编曲与事件的关系建模；OWL
- [Ontology for Media Resources](https://www.w3.org/TR/mediaont-10/) - 多媒体资源元数据的 W3C 本体；OWL
- [Chemical Information Ontology（CHEMINF）](https://obofoundry.org/ontology/cheminf.html) - 化学信息与化学描述符本体，药物发现领域常用；OWL
- [Dublin Core 与元数据词表索引（DCMI）](https://www.dublincore.org/specifications/) - 各领域元数据词表的官方索引
- [Wikidata 属性与本体（Wikidata:WikiProject Ontology）](https://www.wikidata.org/wiki/Wikidata:WikiProject_Ontology) - 最大协作知识库的属性治理与本体议题

### 中文与国产资源

- [OpenKG 开放知识图谱社区](http://openkg.cn/) - 中文知识图谱资源联盟，含数据集、工具、本体与 SIG 活动
- [OpenKG GitHub 组织](https://github.com/OpenKG-ORG) - 社区开源项目汇总，含本体与知识图谱工具
- [术语在线](https://www.termonline.cn/) - 全国科学技术名词审定委员会规范术语平台，中文本体概念对齐依据
- [国家标准全文公开系统](https://openstd.samr.gov.cn/) - GB/T 术语与元数据相关国家标准的官方检索入口
- [中国中文信息学会](http://www.cipsc.org.cn/) - 国内语言与知识计算的主要学术组织，CCKS 等会议的主办方
- [CN-DBpedia（复旦大学知识工场）](http://kw.fudan.edu.cn/) - 较早的中文百科知识图谱，提供本体结构与 API
- [中医药学语言系统与语义网络（OpenKG 检索入口）](http://openkg.cn/group) - 中文领域本体与词表的社区聚合入口，中医药本体多在此发布

## 标准与规范

本体领域的"硬约束"集中在两处：W3C 的语义网标准族，以及各社区的原则性规范。建模前先确认目标标准，能省掉大量返工。

### W3C 标准

- [RDF 1.1 Concepts and Abstract Syntax](https://www.w3.org/TR/rdf11-concepts/) - 图数据模型的基础规范，定义 IRI、字面量与数据集
- [RDF Schema 1.1](https://www.w3.org/TR/rdf-schema/) - 最轻量的类与属性定义层
- [OWL 2 Document Overview](https://www.w3.org/TR/owl2-overview/) - OWL 2 全部文档的入口，含各语法与语义分支
- [OWL 2 Profiles](https://www.w3.org/TR/owl2-profiles/) - EL、QL、RL 三种可判定 profile 的取舍说明，选型必读
- [OWL 2 Direct Semantics](https://www.w3.org/TR/owl2-direct-semantics/) - OWL 2 DL 的模型论语义，理解推理结果的依据
- [OWL 2 Quick Reference Guide](https://www.w3.org/TR/owl2-quick-reference/) - 构造子速查表
- [SPARQL 1.1 Query Language](https://www.w3.org/TR/sparql11-query/) - 查询语法与语义规范
- [SPARQL 1.1 Update](https://www.w3.org/TR/sparql11-update/) - 图数据的增删改规范
- [SHACL](https://www.w3.org/TR/shacl/) - 基于图的约束校验语言，本体数据质量的事实标准
- [SHACL Advanced Features](https://www.w3.org/TR/shacl-af/) - SHACL 规则与函数扩展
- [Shape Expressions（ShEx）](http://shex.io/) - 与 SHACL 并行的形状校验语言，语法更紧凑
- [JSON-LD 1.1](https://www.w3.org/TR/json-ld11/) - JSON 中的 RDF 序列化与上下文机制
- [Turtle](https://www.w3.org/TR/turtle/) - 最通用的人工可读 RDF 序列化格式
- [N-Quads](https://www.w3.org/TR/n-quads/) - 带图标识的四元组序列化，数据集交换常用
- [SKOS Reference](https://www.w3.org/TR/skos-reference/) - 知识组织系统的标准表达
- [PROV-O](https://www.w3.org/TR/prov-o/) - 溯源本体标准
- [SOSA/SSN](https://www.w3.org/TR/vocab-ssn/) - 传感器与观测本体标准
- [OWL-Time](https://www.w3.org/TR/owl-time/) - 时间与时间区间本体
- [Data Catalog Vocabulary（DCAT）](https://www.w3.org/TR/vocab-dcat-3/) - 数据目录描述标准
- [Linked Data Platform（LDP）](https://www.w3.org/TR/ldp/) - 读写关联数据的 HTTP 交互规范
- [R2RML](https://www.w3.org/TR/r2rml/) - 关系数据库到 RDF 数据集的映射语言，OBDA 的基础标准
- [Organization Ontology（ORG）](https://www.w3.org/TR/vocab-org/) - 组织机构词表
- [RDF 工作组主页（RDF 1.2 / RDF-star）](https://www.w3.org/groups/wg/rdf/) - 三元组术语化与 RDF 1.2 最新进展的官方入口

### ISO 与国家标准

- [ISO/IEC 21838 顶层本体系列（IAOA 信息页）](https://www.iaoa.org/) - 顶层本体国际标准化的组织入口，21838-2 即 BFO
- [ISO 25964 叙词表与互操作（Wikipedia 概览）](https://en.wikipedia.org/wiki/ISO_25964) - 叙词表与检索语言的两部分标准
- [ISO 21127 CIDOC CRM](http://www.cidoc-crm.org/) - 文化遗产信息交换的概念参考模型
- [ETSI SAREF 标准](https://saref.etsi.org/) - 智能家电与设备的欧洲电信标准本体
- [OGC GeoSPARQL 标准](https://www.ogc.org/standard/geosparql/) - 地理空间数据的语义查询标准
- [国家标准全文公开系统](https://openstd.samr.gov.cn/) - 中国国家标准检索入口，可查术语与元数据相关 GB/T

### 社区规范与最佳实践

- [OBO 文件格式规范（INCATools/oboformat）](https://github.com/INCATools/oboformat) - OBO 语法的官方实现与格式定义
- [OBO Foundry 原则 FP-001 开放许可](https://obofoundry.org/principles/fp-001-opensource.html) - 本体复用前必须确认的许可要求
- [Data on the Web Best Practices（W3C）](https://www.w3.org/TR/dwbp/) - 数据发布与元数据描述的官方建议
- [Spatial Data on the Web Best Practices（W3C）](https://www.w3.org/TR/sdw-bp/) - 空间数据语义化的实践指南
- [Ontology Engineering with Ontology Design Patterns（IOS Press）](https://ebooks.iospress.nl/volume/ontology-engineering-with-ontology-design-patterns-foundations-and-applications) - 本体设计模式的奠基性教材，开放获取
- [OntoClean 方法文献检索（Semantic Scholar）](https://www.semanticscholar.org/search?q=OntoClean) - 本体概念元属性清洗方法的论文入口

## 本体仓库与检索平台

找现成本体时优先在这几个平台搜索：确认该本体是否已被收录、最近一次发布时间、以及被其他本体引用的情况。

- [Linked Open Vocabularies（LOV）](https://lov.linkeddata.es/) - 关联开放词表的搜索引擎，可按类与属性检索，含版本统计
- [BioPortal](https://bioportal.bioontology.org/) - 最大的生物医学本体仓库，提供映射、评论与 REST API
- [EBI Ontology Lookup Service（OLS4）](https://www.ebi.ac.uk/ols4/) - EMBL-EBI 的本体检索服务，覆盖 OBO 与大量外部本体
- [Ontobee](http://www.ontobee.org/) - 面向链接数据的本体浏览器，适合查看某个类的跨本体链接情况
- [Aber-OWL](http://aber-owl.net/) - 支持在线分类推理的本体仓库，可直接查询隐含父类
- [EcoPortal](https://ecoportal.lifewatch.eu/) - 生态环境领域的本体与词表门户
- [MatPortal](https://matportal.org/) - 材料科学本体门户，与 EMMO 生态紧密
- [FAIRsharing](https://fairsharing.org/) - 标准、数据库与数据政策的一站式登记平台，含本体与元数据标准
- [RDA Metadata Standards Catalog](https://rdamsc.bath.ac.uk/) - 跨学科元数据标准的社区维护目录
- [Wikidata](https://www.wikidata.org/) - 最大规模的协作知识库，其属性与条目本身即大型词表实践
- [Wikibase](https://wikiba.se/) - Wikidata 背后的开源知识库软件，自建本体驱动的知识库首选
- [Linked Open Data Cloud](https://lod-cloud.net/) - LOD 数据集与词表的可视化总览，含领域与链接统计
- [ESIP（Earth Science Information Partners）](https://www.esipfed.org/) - 地球科学数据的语义与词表协作社区

## 工具链

按本体生命周期排列：建模、推理、编程、可视化、文档、质量、对齐、学习、演化、存储。

### 编辑器与建模环境

- [Protégé](https://protege.stanford.edu/) - 事实标准的桌面本体编辑器，插件生态最完整
- [WebProtégé](https://webprotege.stanford.edu/) - Protégé 的浏览器版本，支持多人协作与评审
- [TopBraid Composer](https://www.topquadrant.com/products/topbraid-composer/) - 企业级建模环境，本体、SHACL 与数据治理一体（商业）
- [VocBench](https://vocbench.uniroma2.it/) - 面向 SKOS 词表与本体协作的 Web 平台，多语言术语管理强
- [PoolParty Semantic Suite](https://www.poolparty.biz/) - 词表与知识图谱的商业套件，含本体编辑器
- [metaphactory](https://www.metaphacts.com/) - 知识图谱平台，内置本体管理与可视化
- [Anzo（Cambridge Semantics）](https://www.cambridgesemantics.com/anzo/) - 企业级知识图谱与本体工程平台
- [NeOn Toolkit](http://neon-toolkit.org/) - 基于 Eclipse 的本体工程环境，生态庞大但已停止维护

### 命令行与开发套件

- [ROBOT](http://robot.obolibrary.org/) - OBO 社区的本体积木工具，推理、抽取、合并、报告、格式转换全覆盖
- [Ontology Development Kit（ODK）](https://github.com/INCATools/ontology-development-kit) - 基于 Docker 的本体工程流水线，含 CI 与发布流程模板
- [LinkML](https://linkml.io/) - 用 YAML 定义模式并生成 OWL、SHACL、JSON Schema、Python 等多产物
- [Ontology Access Kit（OAK）](https://github.com/INCATools/ontology-access-kit) - 统一的本体后端访问层，屏蔽 OWL、OBO、SQL 等差异
- [Semantic Versioning for Ontologies（OBO 原则索引）](https://obofoundry.org/principles/) - 本体版本管理与发布原则，发版策略参考

### 推理机

- [HermiT](http://www.hermit-reasoner.com/) - 基于 hypertableau 的完备 OWL 推理机，Protégé 默认之一
- [ELK](https://github.com/liveontologies/elk-reasoner) - 面向 OWL 2 EL 的高性能推理机，大规模生物医学本体的首选
- [FaCT++](https://www.cs.ox.ac.uk/isg/tools/fact/) - 经典 tableau 推理机，曼彻斯特大学维护
- [Konclude](https://github.com/konclude/Konclude) - C++ 实现的高性能推理机，支持并发推理
- [Openllet](https://github.com/Galigator/openllet) - 由 Pellet 分支而来的 OWL 2 推理机，持续维护中
- [Pellet](https://github.com/stardog-union/pellet) - 曾最流行的开源 OWL DL 推理机，已停止维护
- [RDFox](https://www.oxfordsemantic.tech/product) - 内存推理型三元组库，支持 Datalog 规则与 OWL 2 RL
- [OWL-RL](https://github.com/RDFLib/OWL-RL) - Python 的 OWL 2 RL 与 RDFS 推理实现
- [Apache Jena 推理子系统](https://jena.apache.org/documentation/inference/) - Jena 内置的 RDFS/OWL 与规则推理支持

### 编程库

按语言分组，覆盖本体读写、校验与发布。

Java

- [OWL API](https://github.com/owlcs/owlapi) - Java 生态的 OWL 标准库，几乎所有 Java 本体工具的地基
- [Apache Jena](https://jena.apache.org/) - 完整的 RDF/OWL/SPARQL 框架，含 ARQ 查询引擎与 Fuseki 服务
- [RDF4J](https://rdf4j.org/) - Eclipse 基金会维护的 RDF 框架，内存与存储实现分离
- [Apache Commons RDF](https://commons.apache.org/proper/commons-rdf/) - RDF 1.1 的通用 Java API 抽象层，便于跨实现切换

Python

- [RDFLib](https://github.com/RDFLib/rdflib) - Python 生态的基础 RDF 库，支持 SPARQL 与插件式序列化
- [Owlready2](https://owlready2.readthedocs.io/) - 以对象方式操作 OWL 本体，内置 HermiT 与 Pellet 集成
- [pySHACL](https://github.com/RDFLib/pySHACL) - Python 的 SHACL 校验器，可嵌入数据流水线
- [LinkML Runtime](https://github.com/linkml/linkml-runtime) - LinkML 生成对象的运行时与数据转换工具

JavaScript 与其他语言

- [N3.js](https://github.com/rdfjs/N3.js) - 高性能的 RDF/JS 实现，支持 Turtle、N-Triples 与推理
- [RDF/JS 规范与生态](https://rdf.js.org/) - JavaScript 端 RDF 数据模型的社区标准与实现索引
- [Oxigraph（Rust/Python）](https://github.com/oxigraph/oxigraph) - Rust 编写的 SPARQL 数据库，提供 Python 绑定
- [horned-owl（Rust）](https://github.com/phillord/horned-owl) - Rust 实现的 OWL 库，面向高性能本体处理
- [Redland librdf（C）](https://librdf.org/) - 老牌 C 语言 RDF 库，提供多语言绑定

### 可视化

- [WebVOWL](http://vowl.visualdataweb.org/) - 浏览器中的本体可视化，VOWL 规范的参考实现
- [VOWL 2 规范与资源](https://github.com/VisualDataWeb/VOWL) - 面向领域用户的本体可视化符号体系
- [OntoGraf（Protégé 插件）](https://protegewiki.stanford.edu/wiki/OntoGraf) - Protégé 内置的类关系图视图，适合快速浏览
- [OWLViz（Protégé 插件）](https://protegewiki.stanford.edu/wiki/OWLViz) - 类层次结构的可视化与导出
- [AR2DTool](https://github.com/idafensp/ar2dtool) - 生成本体图形与类层次图的命令行工具，适合文档自动化
- [Graffoo](https://github.com/essepuntato/Graffoo) - 用 Graphviz 绘制 OWL 本体的可视化框架
- [Ontodia](https://github.com/ontodia-org/ontodia) - 可嵌入的图谱与本体浏览器组件，React 实现

### 文档生成与发布

- [WIDOCO](https://github.com/dgarijo/WIDOCO) - 一键生成本体 HTML 文档，内置 LODE 风格与指标统计
- [pyLODE](https://github.com/rdflib/pyLODE) - Python 实现的本体文档生成器，支持 OWL 与 SHACL 产物
- [LODE（Live OWL Documentation Environment）](https://essepuntato.it/lode/) - 在线本体文档服务，历史悠久的自动生成方案
- [Linked Open Terms（LOT）](https://github.com/oeg-upm/lot) - 词表与本体发布流水线，含文档生成与 FOOPS! 质量评估

### 质量评估与诊断

- [OOPS!（OntOlogy Pitfall Scanner）](http://oops.linkeddata.es/) - 在线本体缺陷扫描器，输出常见建模陷阱清单
- [ROBOT Report](http://robot.obolibrary.org/report) - 命令行本体体检，检查缺失标签、重复定义与 OBO 原则
- [SHACL Playground](https://shacl.org/playground/) - 在线编写与调试 SHACL 形状
- [Apache Jena SHACL](https://jena.apache.org/documentation/shacl/) - Jena 内置的 SHACL 校验引擎
- [TopQuadrant SHACL](https://www.topquadrant.com/technology/shacl/) - SHACL 技术资料与工具入口，含教程与验证器
- [OQuaRE 本体质量评价文献（Semantic Scholar）](https://www.semanticscholar.org/search?q=OQuaRE%20ontology%20quality) - 基于 SQuaRE 的本体质量度量方法论文入口
- [Ontology Modularization 文献（Semantic Scholar）](https://www.semanticscholar.org/search?q=ontology%20modularization) - 本体模块抽取与复用方向的研究入口

### 匹配与对齐

- [Ontology Matching 门户](http://www.ontologymatching.org/) - 本体匹配领域的事实门户，含书目、工具与会议
- [AgreementMakerLight（AML）](https://github.com/AgreementMakerLight/AML) - 自动化本体匹配系统，OAEI 长期参赛者
- [LogMap](https://github.com/ernestojimenezruiz/logmap-matcher) - 具备不一致性修复能力的本体匹配系统，适合大规模生物医学本体
- [Silk Workbench](https://github.com/silk-framework/silk-workbench) - 链接发现框架，支持复杂相似度规则配置
- [LIMES](https://github.com/dice-group/LIMES) - 支持度量空间索引的链接发现工具，时间效率突出
- [OntoAligner（PyPI）](https://pypi.org/project/OntoAligner/) - 模块化本体对齐工具包，整合检索式与 LLM 匹配器，含评测流程
- [YAM++ 文献（Semantic Scholar）](https://www.semanticscholar.org/search?q=YAM%2B%2B%20ontology%20matching) - 多策略本体匹配系统的论文入口

### 本体学习、抽取与 LLM 辅助建模

这是近年变化最快的方向，工具生命周期较短，收录时以上一年的活跃度为准。

- [OntoGPT（Monarch Initiative）](https://github.com/monarch-initiative/ontogpt) - 用 LLM 从文本抽取结构化知识并链接到本体的工具集
- [Onto-learn（DICE Group）](https://github.com/dice-group/Onto-learn) - 基于描述逻辑的本体学习库，支持符号式类表达式学习
- [DL-Learner](http://dl-learner.org/) - 经典的本体学习框架，从数据中归纳类表达式
- [Text2KGBench（IBM）](https://github.com/IBM/Text2KGBench) - 文本到知识图谱生成的评测基准，含本体驱动的任务定义
- [LLMs4OL Challenge（官方仓库）](https://github.com/sciknoworg/LLMs4OL-Challenge) - LLM 本体学习的年度共享任务，含术语类型化、分类发现与非分类关系抽取三个赛道
- [LLMs4OL 任务官网](https://hamedbabaei.github.io/LLMs4OL/) - 任务定义、数据集与历年排行榜入口
- [LLM 本体生成研究（Semantic Scholar 检索）](https://www.semanticscholar.org/search?q=ontology%20generation%20large%20language%20models) - 用大模型自动生成本体与知识模型的最新研究入口
- [Semantica](https://getsemantica.ai/) - 开源语义层与知识工程框架，含本体推理、知识图谱构建与 RDF/SPARQL 导出；Python

### 版本、差异与模块化

- [ROBOT Diff](http://robot.obolibrary.org/diff) - 两个本体版本的结构化差异比对，可输出报告供评审
- [ROBOT Extract](http://robot.obolibrary.org/extract) - 模块抽取与 MIREOT 实现，从大本体中取子集
- [ROBOT Reason](http://robot.obolibrary.org/reason) - 命令行推理与不一致检测，用于发版前自检
- [OWL 2 本体文档与版本 IRI 规范](https://www.w3.org/TR/owl2-syntax/) - ontologyIRI 与 versionIRI 的语法定义，版本策略依据

### 本体数据访问与映射（OBDA）

不搬数据、靠映射把现有数据源暴露成知识图谱的路线，核心是映射语言与执行引擎。

- [R2RML](https://www.w3.org/TR/r2rml/) - W3C 关系数据库到 RDF 的映射语言标准，OBDA 与虚拟知识图谱的映射基础
- [RML 与 RMLMapper](https://rml.io/) - R2RML 的扩展映射语言与工具集，支持 CSV、JSON、XML 等异构数据源
- [RMLMapper（Java 引擎）](https://github.com/RMLio/rmlmapper-java) - RML 官方执行引擎，批量生成 RDF 与链接数据
- [Morph-KGC](https://github.com/morph-kgc/morph-kgc) - Python 映射驱动的知识图谱构建引擎，支持 R2RML 与 RML，适配大数据源
- [Mapeathor（PyPI）](https://pypi.org/project/mapeathor/) - 用电子表格编写映射并生成 R2RML、RML 与 YARRRML 规则
- [Ontop](https://ontop-vkg.org/) - 开源虚拟知识图谱系统，用 R2RML 映射把关系库直接暴露为 SPARQL 端点，支持 OWL 2 QL；Java
- [OBDA 与虚拟知识图谱研究（Semantic Scholar 检索）](https://www.semanticscholar.org/search?q=ontology-based%20data%20access%20virtual%20knowledge%20graph) - OBDA 方向论文与系统对比的检索入口

### 三元组库与查询引擎

只列与本体/RDF 语义强相关的，通用图数据库不在此列。

- [GraphDB（Ontotext）](https://www.ontotext.com/products/graphdb/) - 支持 OWL 与 RDFS 推理的企业级三元组库
- [Stardog](https://www.stardog.com/) - 企业知识图谱平台，本体推理与虚拟图能力强
- [Virtuoso（OpenLink）](https://virtuoso.openlinksw.com/) - 老牌混合型数据库，DBpedia 的底层引擎
- [Apache Jena Fuseki](https://jena.apache.org/documentation/fuseki2/) - 开源 SPARQL 服务器，部署简单，适合原型
- [QLever](https://github.com/ad-freiburg/qlever) - 高性能 SPARQL 引擎，索引与查询速度见长，支持 Wikidata 全量
- [Blazegraph](https://github.com/blazegraph/database) - 曾经的 Wikidata 查询引擎，已归档，历史项目仍在用
- [Amazon Neptune](https://aws.amazon.com/neptune/) - 云上托管图数据库，支持 RDF 与 SPARQL

## 方法论

"怎么把本体建出来"的方法体系。多数经典方法论以论文形式存在，这里给出可检索的文献入口，便于找到原始文献与后续改进版本。

- [METHONTOLOGY（Semantic Scholar 检索）](https://www.semanticscholar.org/search?q=METHONTOLOGY) - 早期最完整的本体开发流程，含规格说明、概念化、形式化与实现阶段
- [On-To-Knowledge 方法论（Semantic Scholar 检索）](https://www.semanticscholar.org/search?q=On-To-Knowledge%20methodology) - 以"可行性研究-开踢-细化-评估"四步组织的实用流程
- [NeOn Methodology（Semantic Scholar 检索）](https://www.semanticscholar.org/search?q=NeOn%20methodology%20ontology) - 面向协作与本体复用的场景化方法论，含九种本体开发情景
- [DILIGENT（Semantic Scholar 检索）](https://www.semanticscholar.org/search?q=DILIGENT%20ontology%20engineering) - 分布式、渐进式的本体工程方法，强调专家组与论证
- [UPON（Semantic Scholar 检索）](https://www.semanticscholar.org/search?q=UPON%20ontology%20unified%20process) - 借鉴统一软件开发过程的本体开发方法
- [SAMOD（Semantic Scholar 检索）](https://www.semanticscholar.org/search?q=SAMOD%20ontology%20methodology) - 以测试用例驱动的敏捷本体建模方法，适合小团队迭代
- [eXtreme Design（XD，Semantic Scholar 检索）](https://www.semanticscholar.org/search?q=eXtreme%20Design%20ontology) - 以本体设计模式为核心单元的迭代式建模方法
- [Ontology Design Patterns（Semantic Scholar 检索）](https://www.semanticscholar.org/search?q=ontology%20design%20patterns) - 可复用建模模式的理论与 catalog 研究入口

## 基准数据集与评测

需要客观比较工具或方法时从这里入手。

- [OAEI（Ontology Alignment Evaluation Initiative）](http://oaei.ontologymatching.org/) - 本体匹配领域唯一的年度权威评测，含解剖学、会议、大规模生物医学等赛道
- [LUBM（Lehigh University Benchmark）](http://swat.cse.lehigh.edu/projects/lubm/) - 最经典的本推理与查询基准，含标准本体与数据生成器
- [UOBM Generator（牛津大学）](https://www.cs.ox.ac.uk/isg/tools/UOBMGenerator/) - LUBM 的扩展版，数据规模与推理复杂度更高，含生成器
- [OWL2Bench（ISWC 2020）](https://github.com/kracr/owl2bench) - 覆盖 OWL 2 构造子支持度、ABox 规模与查询性能的推理机基准
- [Berlin SPARQL Benchmark（BSBM）](http://wifo5-03.informatik.uni-mannheim.de/bizer/berlinsparqlbenchmark/) - 面向 SPARQL 查询性能的基准，适合评测三元组库
- [LLMs4OL 系列任务与论文（Semantic Scholar 检索）](https://www.semanticscholar.org/search?q=LLMs4OL) - LLM 本体学习年度挑战的任务定义与结果论文

## 社区与活动

### 会议与研讨会

- [ISWC（International Semantic Web Conference）](https://en.wikipedia.org/wiki/International_Semantic_Web_Conference) - 语义网领域最高级别会议，历年收录本体工程主线成果
- [ESWC（Extended Semantic Web Conference，DBLP 索引）](https://dblp.org/db/conf/esws/index.html) - 欧洲语义网会议，本体与知识图谱论文密集
- [FOIS（Formal Ontology in Information Systems，DBLP 索引）](https://dblp.org/db/conf/fois/index.html) - 形式本体论旗舰会议，偏哲学与理论计算机交叉
- [JOWO（Joint Ontology Workshops）](https://www.iaoa.org/) - IAOA 主办的本体研讨会联合体，本年度信息见官网
- [WOP（Workshop on Ontology Design and Patterns，DBLP 索引）](https://dblp.org/db/conf/semweb/) - 与 ISWC 同期举办，专注本体设计模式与本体复用
- [ICBO（International Conference on Biomedical Ontology，DBLP 索引）](https://dblp.org/db/conf/icbo/index.html) - 生物医学本体年会，OBO 社区的主要交流场所
- [Ontology Summit](https://ontolog.cim3.net/cgi-bin/wiki.pl?OntologySummit) - 每年围绕一个议题产出共同宣言的开放式系列研讨会
- [SEMANTiCS](https://www.semantics.cc/) - 欧洲产业与学术结合的数据与语义技术会议
- [CCKS（全国知识图谱与语义计算大会）](http://www.cipsc.org.cn/) - 中文知识图谱领域主会，主办方中国中文信息学会

### 期刊

- [Semantic Web Journal](http://www.semantic-web-journal.net/) - 语义网领域专门期刊，本体工程论文的主要去处，开放获取
- [Journal of Web Semantics](https://www.sciencedirect.com/journal/journal-of-web-semantics) - Elsevier 旗下老牌期刊，覆盖语义技术与本体理论
- [Applied Ontology](https://content.iospress.com/journals/applied-ontology) - IOS Press 期刊，专注本体在各领域的应用与方法论
- [Journal of Biomedical Semantics](https://jbiomedsem.biomedcentral.com/) - 生物医学语义与本体期刊，开放获取
- [Data Intelligence](https://direct.mit.edu/dint) - MIT Press 期刊，知识图谱与数据智能方向，中文社区参与度高
- [CEUR Workshop Proceedings](https://ceur-ws.org/) - 研讨会论文的开放出版平台，本体工作坊论文多在此检索

### 组织与社区

- [W3C](https://www.w3.org/) - 语义网与本体相关标准的制定机构，各工作组主页可追踪标准进度
- [SHACL 社区组](https://www.w3.org/groups/cg/shacl/) - SHACL 扩展与最佳实践的社区讨论场所
- [IAOA（International Association for Ontology and its Applications）](https://www.iaoa.org/) - 本体学与应用国际协会，FOIS 与 JOWO 的主办方
- [Ontolog Forum](https://ontolog.cim3.net/) - 历史悠久的本体实践者开放论坛，含大量会议存档

### 代表人物

按其在顶层本体、推理、本体工程与知识图谱方向的公开成果排列，链接为个人主页或可检索的成果索引。

- [Ian Horrocks](https://www.cs.ox.ac.uk/people/ian.horrocks/) - OWL 与描述逻辑推理方向的核心学者，FaCT++、HermiT 相关工作的推动者
- [Nicola Guarino（DBLP）](https://dblp.org/pid/g/NicolaGuarino.html) - DOLCE 与 OntoClean 的主要作者，概念建模与本体论分析
- [Aldo Gangemi（DBLP）](https://dblp.org/pid/g/AldoGangemi.html) - 本体设计模式与语义网方法论方向
- [Valentina Presutti（DBLP）](https://dblp.org/pid/p/ValentinaPresutti.html) - 本体设计模式、eXtreme Design 与开放知识抽取方向
- [Silvio Peroni](https://www.essepuntato.it/) - SPAR Ontologies 作者，学术出版本体与本体工程教材作者
- [Chris Mungall](https://github.com/cmungall) - OBO 生态核心开发者，Uberon、RO、OBO 工具链维护者
- [Aidan Hogan](https://aidanhogan.com/) - 知识图谱与 RDF 方向研究者，RDF 教材与大规模知识图谱研究
- [清华 KEG 实验室](https://keg.cs.tsinghua.edu.cn/) - 知识工程实验室，中文知识图谱与本体研究的代表性团队

### 博客与 Newsletter

- [Semantic Arts Blog](https://www.semanticarts.com/blog/) - 企业级本体建模的长期博客，gist 本体作者团队维护
- [Ontotext Blog](https://www.ontotext.com/blog/) - 三元组库与知识图谱工程实践文章
- [PoolParty Blog](https://www.poolparty.biz/blog/) - 词表管理与企业知识图谱的实践分享
- [douroucouli（Chris Mungall 博客）](https://douroucouli.wordpress.com/) - OBO 生态与本体工程的技术随笔，更新稳定

## 最新研究论文

本体工程领域的最新研究方向与代表性论文，按领域分类整理，便于追踪学术前沿。

👉 **[最新研究论文与方向](docs/papers.md)** — 含 LLM 与本体工程、本体学习、匹配对齐、质量评估、形式化推理、知识图谱构建、领域应用、演化模块化等方向的最新论文与检索入口。

## 相关 Awesome 列表

- [awesome-semantic-web](https://github.com/semantalytics/awesome-semantic-web) - 本清单结构上的直接参考，语义网与关联数据资源全集
- [awesome-knowledge-graph（totogo）](https://github.com/totogo/awesome-knowledge-graph) - 知识图谱基础设施、数据集与学习材料清单
- [awesome-knowledge-graph（husthuke，中文为主）](https://github.com/husthuke/awesome-knowledge-graph) - 中文整理的知识图谱学习与论文资源集合
- [GitHub 检索：awesome ontology](https://github.com/search?q=awesome+ontology&type=repositories) - 本体方向其他清单的检索入口
- [GitHub 检索：awesome linked data](https://github.com/search?q=awesome+linked+data&type=repositories) - 关联数据方向清单的检索入口

## 贡献

收录标准、条目格式与提交流程见 [CONTRIBUTING.md](CONTRIBUTING.md)。

一句话概括：只收与本体直接相关、公开可访问、仍在维护的资源；每条一行，格式为 `- [名称](URL) - 一句话说明`；提交前跑一遍 `python scripts/stats.py` 与 `python scripts/generate_toc.py`。

发现失效链接、停更项目或过时描述，欢迎直接提 PR 修正。

## 许可证

清单内容与文档以 [CC0 1.0 Universal](LICENSE) 释放至公共领域，可自由使用与演绎，无需署名。

各链接指向的第三方资源适用其自身的许可协议，使用前请自行确认，尤其是本体的再分发条款。

