# awesome-ontology 工程研究报告

## 执行摘要

本报告记录了 `d:/code/awesome-ontology` 这个 awesome 清单工程的设计与构建过程。工程参考 semantalytics/awesome-semantic-web 的组织方式，围绕本体工程主题建立了 11 个一级分类、34 个二级分类、287 条资源条目的清单，并配套贡献规范、行为准则、三个维护脚本与两条 GitHub Actions 工作流。清单以英文一手资料为主、说明文字为中文，单独设置了中文与国产资源小节。受本机网络限制，链接核验采用"抽样搜索核验加工程化巡检"的组合策略，而非一次性全量人工核对。

## 背景

本体（ontology）是语义网与知识图谱的语义骨架，但相关资料高度分散：W3C 的规范族、OBO 社区的原则与工具链、生物医学与工业界的领域本体、描述逻辑与本体匹配的研究文献，各自成体系且更新节奏差异很大。新手面临两个现实问题：不知道哪些工具仍在维护，不知道该按什么顺序学。awesome-semantic-web 覆盖面广但以语义网整体为边界，本体工程只是其中一个分支。因此需要一个以本体为主轴、判断标准更明确的清单。

## 工程结构

```text
awesome-ontology/
├── README.md                         清单主体，287 条资源
├── CONTRIBUTING.md                   收录标准、条目格式、提交流程
├── CODE_OF_CONDUCT.md                Contributor Covenant 2.1
├── LICENSE                           CC0 1.0 Universal
├── .editorconfig / .gitignore
├── docs/
│   ├── research_plan_awesome_ontology.md
│   └── research_report_awesome_ontology.md
├── scripts/
│   ├── generate_toc.py               生成与校验目录
│   ├── stats.py                      清单健康度统计
│   ├── check_links.py                并发链接巡检
│   ├── ignore-links.txt              巡检放行名单
│   └── README.md                     脚本用法
└── .github/
    ├── workflows/
    │   ├── awesome-lint.yml          awesome-lint + TOC 校验 + 统计
    │   ├── link-check.yml            每周定时全量巡检
    │   └── toc.yml                   手动触发重生成目录并开 PR
    ├── ISSUE_TEMPLATE/
    │   ├── new-resource.yml
    │   ├── broken-link.yml
    │   └── config.yml
    └── PULL_REQUEST_TEMPLATE.md
```

## 分类体系

清单按本体生命周期与使用者的查找路径组织，共 11 个一级分类。

入门部分回答"本体是什么、怎么学"，包含概念性文档、W3C 官方 Primer、课程、书籍与术语速查。本体与词表资源是清单的主体，按领域拆为顶层与基础本体、通用词表与元数据、生命科学与生物医学、地理空间与环境、工业与制造、金融法律与政务、学术出版与科研、农业与食品、其他垂直领域、中文与国产资源共 10 个子类，每条标注形式化程度（OWL、RDFS、SKOS）。

标准与规范分 W3C 标准、ISO 与国家标准、社区规范与最佳实践。本体仓库与检索平台解决"去哪找现成本体"。工具链按生命周期排列：编辑器与建模环境、命令行与开发套件、推理机、编程库（按 Java、Python、JavaScript 与其他语言分组）、可视化、文档生成、质量评估、匹配对齐、本体学习与 LLM 辅助建模、版本与模块化、三元组库。方法论一节以可检索的文献入口为主，基准数据集与评测覆盖 OAEI、LUBM、UOBM、OWL2Bench、Text2KGBench、LLMs4OL。社区与活动含会议、期刊、组织、人物、博客。

## 数据来源与核验方法

内容构建以既有领域知识为主，随后用可用的搜索通道对不确定项做抽样核验。核验后有四处条目被修正：LLM4OL 更正为官方的 LLMs4OL Challenge（sciknoworg/LLMs4OL-Challenge）；OntoAligner 改用更稳定的 PyPI 地址；UOBM 改用牛津大学实际的生成器页面；OBO 版本管理原则改用原则索引页以避免具体锚点失效。同时新增了搜索过程中发现的 OWL2Bench 基准与 CHEMINF 本体，并删除若干描述与链接不符或纯占位的条目。

由于外网直连与子代理都不可用，工程把链接可达性设计成可持续执行的机制：`check_links.py` 并发探测所有链接，HEAD 被拒时回退为带 Range 的 GET，结果可输出 JSON 报告；`link-check.yml` 每周定时运行并归档报告；`ignore-links.txt` 用于放行需要登录或强反爬的站点。这样即使初始清单存在个别失效链接，也能在第一次巡检后被定位。

## 维护脚本的设计取舍

三个脚本都只依赖标准库，避免给贡献者增加环境负担。`generate_toc.py` 自己实现 GitHub 锚点规则（小写、去除非单词字符、空格转连字符），支持 `--check` 便于在 CI 中拦截过期目录。`stats.py` 区分两类重复：同一小节内重复链接判定为错误，不同小节引用同一资源只是记录为 cross-listed，因为"同一资源既是 W3C 标准又是可复用词表"这类情况在清单中不可避免。当前清单的 15 个跨小节引用都属于这一类。

## 结论

工程已可直接使用：克隆后无需安装任何依赖即可运行三个维护脚本，推送到 GitHub 后 awesome-lint、目录校验、链接巡检三条工作流即可生效。清单覆盖本体工程的主要方面，中文读者可以先按入门节建立概念，再按领域与工具节选取资源。

## 局限与后续

首要局限是链接未做全量巡检。构建环境的外网不可达意味着 287 条链接中可能有少量失效或迁移地址，第一次 `check_links.py` 全量运行后需要按报告逐条处理，反爬站点登记进 `ignore-links.txt`。

其次是中文资源偏薄。中文与国产资源一节目前以 OpenKG、术语在线、国家标准检索入口为主，领域本体的中文实例（如中医药、农业、政务数据标准）尚未充分覆盖，这是后续最值得补充的方向。

第三是经典方法论以文献检索入口代替具体论文链接。METHONTOLOGY、NeOn、DILIGENT、SAMOD 等没有稳定的官方主页，当前给出 Semantic Scholar 检索入口以保证链接长期可用，后续可由具体论文的 DOI 或开放获取版本替代。

最后，README 徽章与 Issue 模板中的仓库地址使用了 `awesome-ontology/awesome-ontology`，若实际仓库路径不同，需要全局替换该字符串。

## 参考来源

1. [awesome-semantic-web（结构参考）](https://github.com/semantalytics/awesome-semantic-web)
2. [W3C 标准与草案索引](https://www.w3.org/TR/)
3. [OBO Foundry](https://obofoundry.org/)
4. [OWL 2 Document Overview](https://www.w3.org/TR/owl2-overview/)
5. [Ontology Matching 门户](http://www.ontologymatching.org/)
6. [LLMs4OL Challenge 官方仓库](https://github.com/sciknoworg/LLMs4OL-Challenge)
7. [OntoAligner on PyPI](https://pypi.org/project/OntoAligner/)
8. [UOBM Generator（牛津大学）](https://www.cs.ox.ac.uk/isg/tools/UOBMGenerator/)
9. [Ontology Engineering with Ontology Design Patterns（IOS Press）](https://ebooks.iospress.nl/volume/ontology-engineering-with-ontology-design-patterns-foundations-and-applications)
10. [awesome-knowledge-graph（中文）](https://github.com/husthuke/awesome-knowledge-graph)
11. [Contributor Covenant 2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/)
12. [CC0 1.0 Universal 法律文本](https://creativecommons.org/publicdomain/zero/1.0/legalcode)
