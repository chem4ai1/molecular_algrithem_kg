# 贡献指南

感谢你愿意让这份清单变得更好。为了保证数百条资源长期可用，贡献时需要遵守下面几条规则。

## 三条底线

收录的内容必须与**本体（ontology）**直接相关：本体与词表本身、本体工程方法论、本体建模与校验工具、本体相关的标准规范与社区。纯粹的通用知识图谱平台、通用 NLP 工具，只有在明确服务于本体工程时才收录。

资源必须是**公开可访问**的：可以免费访问，或者至少有可用的开放版本与文档。需要付费但不提供试用、文档或开放接口的商业产品不收录。

资源应当**仍然可用**：近两年内有发布、提交或维护迹象。确有历史价值但已停止维护的项目可以收录，但描述里必须标注"已停止维护"。

## 提交方式

推荐用 Pull Request。Fork 本仓库，编辑 `README.md`，把条目放到对应小节的末尾，然后提交。

不确定该放哪里、或者只想推荐一个资源时，用 Issue 模板 New Resource 提交，维护者会帮忙归类。

## 条目格式

每个条目占一行，使用下面的格式：

```markdown
- [资源名](https://example.com) - 一句话说明它是什么、解决什么问题，结尾不加句号
```

规则说明：用 `-` 开头；链接用真实可达的 URL，优先项目官网或 GitHub 仓库主页，不要链接到安装教程或二手介绍；描述控制在 50 字以内；描述结尾不要加句号；保留资源的英文原名，不要音译或自造中文名。

如果一个项目同时属于多个类别，只需在最主要的一个类别里列出。同一小节内不允许重复链接，`scripts/stats.py` 会检查这一类错误；确实需要在多个小节出现的资源，请在描述中注明它同时属于哪个主题。

## 分类原则

`README.md` 的层级是：入门、本体与词表资源、标准与规范、本体仓库与检索平台、工具链、方法论、基准数据集与评测、社区与活动、相关 Awesome 列表。新增小节前先确认现有小节能否容纳，避免分类碎片化。

## 提交前自检

本地跑一遍校验脚本（需要 Python 3.9+）：

```bash
python scripts/stats.py              # 统计条目数、分类数、域分布
python scripts/generate_toc.py       # 重新生成目录，确认锚点无误
python scripts/check_links.py        # 检查链接可达性（需要联网，较慢）
```

CI 会在每次 PR 时执行 awesome-lint 与链接检查。`check_links.py` 若因网络波动误报，在 `scripts/ignore-links.txt` 里登记该 URL。

## 文档站点

站点用 MkDocs Material 构建，内容来自 `README.md`，由 `scripts/build_site.py` 同步到 `docs/`。因此 `docs/index.md`、`docs/contributing.md`、`docs/code-of-conduct.md`、`docs/maintenance.md` 是生成物，不要直接编辑，改动会被覆盖。

本地预览：

```bash
pip install -r requirements.txt
python scripts/build_site.py
mkdocs serve            # 打开 http://127.0.0.1:8000
```

推送到 main 后 `Documentation` 工作流会自动构建并发布。首次使用需要在仓库 Settings 的 Pages 页面把 Source 设为 GitHub Actions。修改 `mkdocs.yml` 的导航后，记得同步 `scripts/build_site.py` 中的文件映射。

## 修改现有条目

发现链接失效、项目停更、描述过时，直接提 PR 修正，并在 PR 描述里说明依据。删除条目时请说明理由，不要静默删除。

## 行为准则

参与本项目即视为同意遵守 [Contributor Covenant](CODE_OF_CONDUCT.md)。
