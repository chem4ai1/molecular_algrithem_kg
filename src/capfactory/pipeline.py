"""CapFactory 主流水线：能力抽取 → 复刻 → 验证 → 沉淀 → 研究方向.

对外只暴露 :class:`CapFactory`，CLI 与 Web 都调用它，保证行为一致。
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .config import Settings, get_settings
from .ingest.arxiv import ArxivClient
from .ingest.github import clone_repo, code_context, group_sequence_datasets, index_repo, search_repos
from .ingest.pdf import find_code_urls, parse_pdf
from .kg import KnowledgeGraph, RunStore
from .kg.export import export_all, to_web_payload
from .llm import CriticAgent, LLMClient, ReaderAgent, get_client
from .research import CoverageAnalyzer, ResearchAdvisor
from .replicate.dataset import (
    load_csv,
    load_fasta,
    load_sequence_list,
    materialise,
    materialise_with_split,
)
from .replicate.replicator import Replicator
from .schema import Capability, Evidence, IOField, MetricSpec, PaperRecord
from .utils import ensure_dir, now_iso, read_json, short_hash, slugify, truncate, write_json

logger = logging.getLogger(__name__)

ProgressFn = Optional[Callable[[str, str], None]]


class CapFactory:
    """算法能力工厂（门面类）。"""

    def __init__(self, settings: Optional[Settings] = None, client: Optional[LLMClient] = None):
        self.settings = settings or get_settings()
        self.client = client or get_client(self.settings)
        self.graph = KnowledgeGraph(self.settings).load()
        self.store = RunStore(self.settings)
        self.arxiv = ArxivClient(self.settings)
        self.reader = ReaderAgent(self.client)
        self.critic = CriticAgent(self.client)
        self.datasets_dir = ensure_dir(self.settings.path("storage") / "datasets")
        self.registry_path = self.datasets_dir / "registry.json"

    # ==================================================================
    # 阶段一：能力抽取与图谱构建
    # ==================================================================
    def build_kg(
        self,
        queries: List[str],
        max_papers: int = 5,
        repos: Optional[List[Dict[str, str]]] = None,
        pdf_paths: Optional[List[str]] = None,
        fetch_code: bool = True,
        progress: ProgressFn = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """检索论文 → 解析 → 抽取能力 → 构建图谱。"""
        run_id = run_id or f"kg_{short_hash(now_iso(), length=8)}"
        self.store.start_run(run_id, "build_kg", "；".join(queries)[:200])

        def emit(level: str, msg: str) -> None:
            logger.info("[%s] %s", level, msg)
            self.store.log_event(run_id, msg, agent=level)
            if progress:
                progress(level, msg)

        started = time.time()
        papers: List[PaperRecord] = []
        seen_ids: set = set()
        repo_specs = list(repos or [])

        # ---- 1. arXiv 检索与下载 ----
        candidates: List[Dict[str, Any]] = []
        for q in queries:
            emit("ingest", f"检索 arXiv：{q}")
            candidates.extend(self.arxiv.search(q, max_results=max_papers))
        # 去重
        uniq: Dict[str, Dict[str, Any]] = {}
        for c in candidates:
            uniq.setdefault(c.get("arxiv_id") or c.get("title", ""), c)
        emit("ingest", f"去重后候选论文 {len(uniq)} 篇")

        paper_dir = ensure_dir(self.settings.path("raw_dir") / "papers")
        md_dir = ensure_dir(self.settings.path("raw_dir") / "parsed")

        for item in list(uniq.values()):
            arxiv_id = item.get("arxiv_id", "")
            if not arxiv_id or arxiv_id in seen_ids:
                continue
            seen_ids.add(arxiv_id)
            pdf = self.arxiv.download_pdf(arxiv_id, paper_dir)
            if not pdf:
                emit("ingest", f"PDF 下载失败，跳过：{item.get('title', '')[:60]}")
                continue
            try:
                parsed = parse_pdf(pdf, md_dir)
            except Exception as exc:  # 单篇解析失败不应中断整批
                emit("parse", f"PDF 解析失败，跳过 {item.get('title', '')[:50]}：{exc}")
                logger.exception("PDF 解析异常")
                continue
            sections: Dict[str, str] = parsed["sections"]  # type: ignore[assignment]
            abstract = item.get("abstract") or parsed["abstract"]
            full_text = "\n".join(sections.values())
            emit("parse", f"解析完成：{item.get('title', '')[:60]}（{len(sections)} 章节）")

            # 代码仓库定位
            repo_url, repo_path, repo_info = "", "", None
            if fetch_code:
                repo_url = self._match_repo(item, full_text, repo_specs)
                if repo_url:
                    dest = ensure_dir(self.settings.path("raw_dir") / "code")
                    cloned = clone_repo(repo_url, dest)
                    if cloned:
                        repo_path = str(cloned)
                        repo_info = index_repo(cloned, self.settings)
                        emit("code", f"仓库就绪：{repo_url}（{len(repo_info.files)} 文件，"
                                     f"{len(repo_info.datasets)} 数据集）")

            code_hint = ""
            if repo_info:
                code_hint = (
                    "## Code repository signals\n"
                    f"Repo: {repo_url}\nRequirements: {', '.join(repo_info.requirements[:12])}\n"
                    f"Entry points: {', '.join(repo_info.entry_points[:6])}\n"
                    f"Datasets: {[d['path'] + ' (' + str(d['n_rows']) + ' rows)' for d in repo_info.datasets[:4]]}"
                )

            extraction = self.reader.extract(
                title=item.get("title", ""), abstract=abstract,
                year=item.get("year"), sections=sections, code_hint=code_hint,
            )
            capabilities = self._make_capabilities(extraction, item)
            review = self.critic.review(full_text or abstract, capabilities)
            capabilities = self.critic.apply(capabilities, review)
            emit("extract", f"抽取能力 {len(capabilities)} 条（批评者裁决：{review.get('verdict')}）")

            paper = PaperRecord(
                id=PaperRecord.make_id(item.get("title", arxiv_id)),
                title=item.get("title", arxiv_id),
                abstract=abstract, authors=item.get("authors", []),
                year=item.get("year"), url=item.get("url", ""),
                arxiv_id=arxiv_id, pdf_path=str(pdf or ""),
                repo_url=repo_url, repo_path=repo_path,
                research_object=str(extraction.get("research_object", ""))[:200],
                background=str(extraction.get("background", ""))[:1000],
                progress=str(extraction.get("progress", ""))[:1000],
                contributions=[str(c) for c in extraction.get("contributions") or []][:8],
                limitations=[str(c) for c in extraction.get("limitations") or []][:8],
                datasets=[(d.get("name") if isinstance(d, dict) else str(d))
                          for d in extraction.get("datasets") or []][:8],
                metrics=[str(m) for m in extraction.get("metrics") or []][:8],
                sections={k: truncate(v, 1500) for k, v in list(sections.items())[:10]},
                full_text_path=str(parsed.get("markdown_path", "")),
            )
            self.graph.add_paper(paper)
            for cap in capabilities:
                cap_id, merged = self.graph.add_capability(cap, paper_id=paper.id)
                emit("graph", f"图谱写入能力：{cap.name}" + ("（合并）" if merged else ""))
            papers.append(paper)

            # 数据集落盘
            if repo_info and repo_path:
                self._materialise_repo_datasets(repo_info, Path(repo_path), emit)

        # ---- 1.5 纯仓库来源（无对应论文时，直接从 README + 代码抽取能力）----
        for spec in repo_specs:
            if (spec.get("match") or "").strip().lower() not in {"__repo__", "__standalone__", "*"}:
                continue
            paper = self._ingest_repo_source(spec.get("url", ""), emit)
            if paper:
                papers.append(paper)

        # ---- 2. 保存与导出 ----
        self.graph.save()
        export_files = export_all(self.graph, self.settings.path("kg_dir") / "exports")
        stats = self.graph.stats()
        summary = (f"论文 {len(papers)} 篇，能力节点 {stats['n_capabilities']} 个，"
                   f"边 {stats['n_edges']} 条")
        self.store.finish_run(run_id, "success", summary, {"stats": stats, "papers": [p.to_dict() for p in papers]})
        emit("done", summary)
        return {
            "run_id": run_id,
            "papers": [p.to_dict() for p in papers],
            "stats": stats,
            "exports": export_files,
            "elapsed_s": round(time.time() - started, 1),
        }

    # ------------------------------------------------------------------
    def _ingest_repo_source(self, repo_url: str, emit: Callable[[str, str], None]) -> Optional[PaperRecord]:
        """把开源仓库当作一种知识来源：README + 入口代码 → 能力抽取.

        对应需求加分项「支持从真实代码仓库中抽取函数、依赖和能力描述」。
        """
        if not repo_url:
            return None
        emit("repo", f"从代码仓库抽取能力：{repo_url}")
        dest = ensure_dir(self.settings.path("raw_dir") / "code")
        cloned = clone_repo(repo_url, dest)
        if not cloned:
            emit("repo", f"仓库获取失败，跳过：{repo_url}")
            return None
        info = index_repo(cloned, self.settings)
        snippets = code_context(cloned, cloned, ["predict", "feature", "model", "classif", "train"], 9000)
        sections = {
            "README": info.readme or "(no readme)",
            "Entry points": ", ".join(info.entry_points[:10]) or "(none)",
            "Code snippets": snippets or "(none)",
            "Datasets": str([f"{d['path']} ({d['n_rows']} rows)" for d in info.datasets[:5]]),
        }
        extraction = self.reader.extract(
            title=f"Open-source implementation: {cloned.name}",
            abstract=(info.readme or "")[:1500],
            year=None, sections=sections,
            code_hint=f"## Repository signals\nRequirements: {', '.join(info.requirements[:12])}",
        )
        capabilities = self._make_capabilities(extraction, {"arxiv_id": "", "title": cloned.name,
                                                            "year": None})
        review = self.critic.review((info.readme or "") + snippets[:4000], capabilities)
        capabilities = self.critic.apply(capabilities, review)
        emit("extract", f"仓库抽取能力 {len(capabilities)} 条（critic: {review.get('verdict')}）")

        paper = PaperRecord(
            id=PaperRecord.make_id(f"repo::{repo_url}"),
            title=f"[代码仓库] {cloned.name}",
            abstract=(info.readme or "")[:2000],
            url=repo_url, repo_url=repo_url, repo_path=str(cloned),
            research_object=str(extraction.get("research_object", ""))[:200],
            background=str(extraction.get("background", ""))[:1000],
            progress=str(extraction.get("progress", ""))[:1000],
            contributions=[str(c) for c in extraction.get("contributions") or []][:8],
            limitations=[str(c) for c in extraction.get("limitations") or []][:8],
            datasets=[d["path"] for d in info.datasets[:6]],
            sections={k: truncate(v, 2000) for k, v in sections.items()},
            source="github",
        )
        self.graph.add_paper(paper)
        for cap in capabilities:
            cap_id, merged = self.graph.add_capability(cap, paper_id=paper.id)
            self.graph.add_edge(paper.id, cap_id, "IMPLEMENTS", 0.9)
            emit("graph", f"图谱写入能力：{cap.name}" + ("（合并）" if merged else ""))
        self._materialise_repo_datasets(info, cloned, emit)
        return paper

    # ------------------------------------------------------------------
    def _match_repo(self, item: Dict[str, Any], full_text: str,
                    repo_specs: List[Dict[str, str]]) -> str:
        """确定论文对应的代码仓库：显式映射 > 论文中链接 > GitHub 搜索。"""
        title_abs = f"{item.get('title', '')} {item.get('abstract', '')}".lower()
        for spec in repo_specs:
            match = (spec.get("match") or "").lower()
            if match.startswith("__"):
                continue  # 纯仓库来源，单独处理
            if match and match in title_abs:
                return spec.get("url", "")
        urls = find_code_urls(full_text) or find_code_urls(item.get("comment", ""))
        if urls:
            return urls[0]
        if repo_specs:
            first = repo_specs[0]
            if not (first.get("match") or "").startswith("__"):
                return first.get("url", "")
        return ""

    # ------------------------------------------------------------------
    def _make_capabilities(self, extraction: Dict[str, Any], item: Dict[str, Any]) -> List[Capability]:
        """把 LLM 输出规范化为 ``Capability`` 列表。"""
        caps: List[Capability] = []
        for raw in extraction.get("capabilities") or []:
            if not isinstance(raw, dict) or not raw.get("name"):
                continue
            name = str(raw["name"]).strip()
            task = str(raw.get("task") or slugify(name, 40).lower().replace("-", "_"))
            cap = Capability(
                id=Capability.make_id(name, task, item.get("title", "")),
                name=name,
                summary=str(raw.get("summary") or "")[:600],
                category=str(raw.get("category") or "model"),
                task=task,
                inputs=[IOField.from_dict(x) for x in raw.get("inputs") or [] if isinstance(x, dict)],
                outputs=[IOField.from_dict(x) for x in raw.get("outputs") or [] if isinstance(x, dict)],
                method=str(raw.get("method") or "")[:4000],
                metrics=[MetricSpec.from_dict(x) for x in raw.get("metrics") or [] if isinstance(x, dict)],
                conditions=[str(x) for x in raw.get("conditions") or []][:8],
                constraints=[str(x) for x in raw.get("constraints") or []][:8],
                dependencies=[str(x) for x in raw.get("dependencies") or []][:10],
                evidence=[Evidence(source_id=item.get("arxiv_id", ""),
                                   quote=str(x.get("quote") or "")[:600],
                                   locator=str(x.get("locator") or ""))
                          for x in raw.get("evidence") or [] if isinstance(x, dict)],
                tags=[str(x) for x in raw.get("tags") or []][:8],
                confidence=float(raw.get("confidence") or 0.5),
                provenance={
                    "paper_title": item.get("title", ""),
                    "arxiv_id": item.get("arxiv_id", ""),
                    "year": item.get("year"),
                    "extractor": extraction.get("_extractor", "llm"),
                    "extracted_at": now_iso(),
                },
            )
            caps.append(cap)
        return caps

    # ------------------------------------------------------------------
    def _materialise_repo_datasets(self, repo_info: Any, repo_path: Path,
                                   emit: Callable[[str, str], None]) -> None:
        """把仓库中嗅探到的数据集转成标准格式并登记（支持 pos/neg 分文件形态）。"""
        if not repo_info.datasets:
            return
        groups = group_sequence_datasets(repo_info.datasets)
        for g in groups[:2]:
            try:
                train_rows: List[tuple] = []
                test_rows: List[tuple] = []
                for p in g["train_pos"]:
                    train_rows += load_sequence_list(repo_path / p, 1)
                for p in g["train_neg"]:
                    train_rows += load_sequence_list(repo_path / p, 0)
                for p in g["test_pos"]:
                    test_rows += load_sequence_list(repo_path / p, 1)
                for p in g["test_neg"]:
                    test_rows += load_sequence_list(repo_path / p, 0)
                pool_rows: List[tuple] = []
                for p in g["pool"]:
                    hint = 1 if re.search(r"pos|toxin", Path(p).stem.lower()) and "non" not in Path(p).stem.lower() else 0
                    pool_rows += load_sequence_list(repo_path / p, hint)

                name = f"{repo_path.name}__{slugify(g['name'], 24)}"
                meta = None
                if train_rows and test_rows:
                    meta = materialise_with_split(train_rows, test_rows, self.datasets_dir / name, name,
                                                 source=f"{repo_info.url or repo_path.name}:{g['dir']}")
                elif train_rows or pool_rows:
                    meta = materialise(train_rows + pool_rows, self.datasets_dir / name, name,
                                       source=f"{repo_info.url or repo_path.name}:{g['dir']}")
                if meta:
                    self._register_dataset(meta)
                    emit("data", f"数据集登记：{name}（{meta['n_total']} 条，"
                                 f"正例率 {meta['positive_rate']:.1%}，"
                                 f"{meta.get('split', 'stratified')}）")
            except Exception as exc:  # 数据集异常不应阻断主流程
                logger.warning("数据集处理失败 %s：%s", g.get("dir"), exc)

        # 通用「带标签表格」数据集
        for ds in repo_info.datasets[:2]:
            if ds.get("label_from_name") or ds["format"] == "fasta" or not ds.get("label_col"):
                continue
            path = repo_path / ds["path"]
            if not path.exists():
                continue
            try:
                rows = load_csv(path, ds["seq_col"], ds["label_col"])
                if not rows:
                    continue
                name = f"{repo_path.name}__{slugify(Path(ds['path']).stem, 30)}"
                meta = materialise(rows, self.datasets_dir / name, name,
                                   source=f"{repo_info.url or repo_path.name}:{ds['path']}",
                                   seq_col=ds["seq_col"], label_col=ds["label_col"])
                if meta:
                    self._register_dataset(meta)
                    emit("data", f"数据集登记：{name}（{meta['n_total']} 条）")
            except Exception as exc:
                logger.warning("数据集处理失败 %s：%s", ds.get("path"), exc)

    def _register_dataset(self, meta: Dict[str, Any]) -> None:
        registry = read_json(self.registry_path, default=[]) or []
        meta = dict(meta)
        meta["dataset_json"] = str(Path(meta["train_path"]).parent / "dataset.json")
        registry = [r for r in registry if r.get("name") != meta.get("name")]
        registry.append(meta)
        write_json(self.registry_path, registry)

    def list_datasets(self) -> List[Dict[str, Any]]:
        return read_json(self.registry_path, default=[]) or []

    def _select_dataset(self, capability: Capability, explicit: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """为能力挑选验证数据集：显式指定 > 关键词匹配 > 最大数据集。"""
        if explicit:
            p = Path(explicit)
            if p.is_dir():
                p = p / "dataset.json"
            if p.suffix == ".csv":
                rows = load_csv(p, "sequence", "label")
                meta = materialise(rows, self.datasets_dir / slugify(p.stem, 40), slugify(p.stem, 40),
                                   source=str(p))
                if meta:
                    self._register_dataset(meta)
                    return self._registry_entry(meta["name"])
            elif p.exists():
                return read_json(p)
        registry = self.list_datasets()
        if not registry:
            return None
        text = f"{capability.task} {capability.name} {capability.summary}".lower()
        best, best_score = None, -1.0
        for entry in registry:
            label = f"{entry.get('name', '')} {entry.get('source', '')}".lower()
            score = sum(1 for tok in set(text.split()) if len(tok) > 3 and tok in label)
            score += 0.5 if "toxin" in label and "toxin" in text else 0.0
            score += 0.01 * entry.get("n_total", 0) / 1000
            if score > best_score:
                best, best_score = entry, score
        return best or registry[0]

    def _registry_entry(self, name: str) -> Optional[Dict[str, Any]]:
        for entry in self.list_datasets():
            if entry.get("name") == name:
                return entry
        return None

    # ==================================================================
    # 阶段二：能力复刻与验证
    # ==================================================================
    def replicate(self, capability: str, dataset: Optional[str] = None,
                  progress: ProgressFn = None, run_id: Optional[str] = None) -> Dict[str, Any]:
        """对指定能力（id 或检索词）执行复刻闭环。"""
        run_id = run_id or f"rep_{short_hash(capability, now_iso(), length=8)}"
        self.store.start_run(run_id, "replicate", capability[:200])

        def emit(level: str, msg: str) -> None:
            logger.info("[%s] %s", level, msg)
            self.store.log_event(run_id, msg, agent=level)
            if progress:
                progress(level, msg)

        cap_id = self._resolve_capability(capability)
        node = self.graph.get(cap_id)
        if node is None:
            raise KeyError(f"未找到能力：{capability}")
        cap = self._capability_from_node(node)
        emit("select", f"目标能力：{cap.name}（{cap.task}，置信度 {cap.confidence}）")

        dataset_meta = self._select_dataset(cap, dataset)
        if not dataset_meta:
            raise RuntimeError("没有可用验证数据集，请先执行 build_kg 或显式指定 --dataset")
        emit("data", f"验证数据集：{dataset_meta.get('name')} "
                     f"(train={dataset_meta.get('n_train')}, test={dataset_meta.get('n_test')})")

        code_refs = ""
        repo_path = ""
        paper_title = node["attrs"].get("provenance", {}).get("paper_title", "")
        for paper in self.graph.papers():
            if paper.get("label") == paper_title:
                repo_path = paper.get("attrs", {}).get("repo_path", "") or ""
                break
        if repo_path and Path(repo_path).exists():
            keywords = [w for w in re.split(r"\W+", cap.name.lower()) if len(w) > 3][:4] or ["predict"]
            code_refs = code_context(Path(repo_path), Path(repo_path), keywords, 5000)

        replicator = Replicator(self.graph, self.settings, progress=emit)
        result = replicator.run(cap_id, dataset_meta, code_refs)
        self.store.finish_run(
            run_id, "success" if result["best"]["passed"] else "partial",
            f"{cap.name}: {'通过' if result['best']['passed'] else '未通过'} "
            f"（{result['best']['plan']}，score={result['best']['score']:.3f}）",
            {"result": result, "dataset": dataset_meta.get("name")},
        )
        result["run_id"] = run_id
        return result

    def _resolve_capability(self, key: str) -> str:
        """支持「能力 id」或自然语言检索词。"""
        if self.graph.get(key) and self.graph.get(key)["type"] == "capability":
            return key
        hits = self.graph.search_capabilities(key, top_k=1)
        if hits:
            return hits[0].node_id
        caps = self.graph.capabilities()
        if not caps:
            raise KeyError("知识图谱中没有任何能力，请先执行 build_kg")
        return caps[0]["id"]

    def _capability_from_node(self, node: Dict[str, Any]) -> Capability:
        attrs = dict(node.get("attrs", {}))
        attrs.pop("label", None)
        attrs["id"] = node["id"]
        attrs["name"] = node.get("label", "")
        for k in ("inputs", "outputs", "metrics", "evidence"):
            attrs.setdefault(k, [])
        return Capability.from_dict(attrs)

    # ==================================================================
    # 阶段三：研究方向分析
    # ==================================================================
    def research(self, needs: Optional[List[str]] = None, progress: ProgressFn = None,
                 run_id: Optional[str] = None) -> Dict[str, Any]:
        """能力覆盖度分析 + 研究方向建议。"""
        run_id = run_id or f"res_{short_hash(now_iso(), length=8)}"
        self.store.start_run(run_id, "research", "研究方向分析")

        def emit(level: str, msg: str) -> None:
            logger.info("[%s] %s", level, msg)
            self.store.log_event(run_id, msg, agent=level)
            if progress:
                progress(level, msg)

        emit("coverage", "计算需求—能力覆盖矩阵")
        result = ResearchAdvisor(self.graph, settings=self.settings).run(needs)
        emit("advise", f"生成 {len(result['directions'])} 个研究方向")
        report_path = self._write_research_report(result)
        self.store.finish_run(run_id, "success",
                              f"覆盖缺口 {result['coverage']['summary']['gap']} 个，"
                              f"方向 {len(result['directions'])} 条",
                              {"coverage": result["coverage"], "report": str(report_path)})
        result["run_id"] = run_id
        result["report_path"] = str(report_path)
        return result

    def _write_research_report(self, result: Dict[str, Any]) -> Path:
        """生成 Markdown 研究报告。"""
        reports = ensure_dir(self.settings.path("reports"))
        path = reports / f"research_{short_hash(now_iso(), length=6)}.md"
        cov = result["coverage"]
        lines = [
            f"# 算法能力与研究缺口报告",
            "",
            f"生成时间：{now_iso()}",
            "",
            "## 1. 需求覆盖度",
            "",
            f"覆盖 {cov['summary']['covered']} / 部分 {cov['summary']['partial']} / "
            f"缺口 {cov['summary']['gap']}（覆盖率 {cov['summary']['coverage_rate']:.1%}）",
            "",
            "| 需求 | 状态 | 相关度 | 成熟度 | 命中能力 |",
            "|---|---|---|---|---|",
        ]
        for n in cov["needs"]:
            top = n["matched"][0]["name"] if n["matched"] else "-"
            lines.append(f"| {n['need']} | {n['status']} | {n['relevance']:.2f} | "
                         f"{n['maturity']:.2f} | {top} |")
        lines += ["", "## 2. 能力分布", "", "| 任务 | 能力数 | 已验证 | 平均成熟度 |", "|---|---|---|---|"]
        for t in result.get("task_distribution", []):
            lines.append(f"| {t['task']} | {t['count']} | {t['verified']} | {t['avg_maturity']:.2f} |")
        lines += ["", "## 3. 研究方向建议", ""]
        for i, d in enumerate(result["directions"], 1):
            lines += [
                f"### 方向 {i}：{d['title']}（优先级 {d['priority']:.2f}，难度 {d['difficulty']}）",
                "",
                f"- **缺口**：{d['gap']}",
                f"- **依据**：{d['rationale']}",
                f"- **需要的能力**：{', '.join(d['required_capabilities']) or '-'}",
                f"- **预期影响**：{d['expected_impact']}",
                "- **验证实验**：",
            ] + [f"  - {e}" for e in d["experiments"]] + [""]
        path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("研究报告已生成：%s", path)
        return path

    # ==================================================================
    # 辅助
    # ==================================================================
    def status(self) -> Dict[str, Any]:
        """总体状态（Web 首页）。"""
        stats = self.graph.stats()
        datasets = self.list_datasets()
        runs = self.store.list_runs(limit=10)
        return {
            "stats": stats,
            "datasets": [{"name": d.get("name"), "n_total": d.get("n_total"),
                          "positive_rate": d.get("positive_rate")} for d in datasets],
            "runs": runs,
            "llm": {
                "available": self.client.available(),
                "model": self.settings.llm.get("model"),
                "offline": bool(self.settings.llm.get("offline")),
                "usage": type(self.client).stats(),
            },
            "domain": self.settings.domain.get("name"),
            "generated_at": now_iso(),
        }

    def web_payload(self) -> Dict[str, Any]:
        payload = to_web_payload(self.graph)
        payload["coverage"] = CoverageAnalyzer(self.graph, self.settings).analyze()
        return payload

    def reload(self) -> None:
        self.graph = KnowledgeGraph(self.settings).load()
