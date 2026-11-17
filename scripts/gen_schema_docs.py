#!/usr/bin/env python3
"""生成 docs/schema 下的节点文档（每类一份）。

自动部分：属性表（级别/说明/覆盖率）、出边/入边、图内实例数、抽取阶段（从
STAGE_CLASSES 与 extract_target/refine 反查）。
手工部分：USAGE（使用场景）、NOTE（边界）、EXAMPLE（示例）。
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from capfactory.semantic.tbox_v4 import SEMANTIC_CLASSES, SEMANTIC_RELATIONS  # noqa: E402
from capfactory.applayer.tbox import APP_CLASSES, APP_RELATIONS               # noqa: E402
from capfactory.semantic.extraction.contracts import STAGE_CLASSES           # noqa: E402

GRAPH = ROOT / "storage/sciforge/batch10_semantic_v4.json"
OUT_S = ROOT / "docs/schema/semantic"
OUT_A = ROOT / "docs/schema/application"

TASK_W = {"ResearchGap", "CitedPaper", "ReviewPoint", "SectionDraft"}
TASK_R = {"FailureCheck", "ConsultedPaper"}
TASK_LEVEL = TASK_W | TASK_R

ID_PREFIX = {
    "Paper": "paper", "Algorithm": "algorithm",
    "AlgorithmModule": "algorithmmodule", "CodeRepository": "repo",
    "CodeFunction": "func", "Benchmark": "benchmark",
    "ProblemCategory": "cat", "Contribution": "contribution",
    "ResearchGap": "gap", "Assumption": "assumption",
    "FailureMode": "failure", "EvidenceNorm": "norm",
    "ExperimentArm": "experiment", "LeaderboardEntry": "entry",
    "MetricDefinition": "metric", "Evidence": "evidence",
    "Limitation": "limitation", "CitedPaper": "cited",
    "SourcePaper": "sourcepaper", "SectionPlan": "sectionplan",
    "SectionDraft": "draft", "FigureAsset": "figure",
    "ReviewPoint": "review", "FailureCheck": "check",
    "ConsultedPaper": "consult", "DataContract": "contract",
}

ATTR_DESC = {
    "run_id": "所属写作 run", "gap_id": "全局唯一 id",
    "gap_type": "capability/scale/data/theory/efficiency",
    "statement": "一句话陈述", "evidence": "逐字引文",
    "priority": "high/medium/low", "source_papers": "提炼来源论文 id[]",
    "selected_at": "选定时间", "cite_key": "引用键",
    "title": "标题", "doi": "DOI", "authors": "作者", "year": "年份",
    "venue": "发表场所", "layers": "三层核验状态[3]",
    "existence": "存在性 unknown/yes/no", "metadata_ok": "元数据一致",
    "context_ok": "上下文是否支撑", "context_quote": "支撑句",
    "cited_in": "被哪几节引用[]", "recency_ratio": "近两年占比",
    "axis": "6 维之一", "attack": "最强反驳", "response": "回应",
    "severity": "fatal/high/medium/low", "evidence_gap": "该攻击为何成立",
    "status": "pass/fail/unknown", "note": "备注", "checked_at": "检查时间",
    "paper_id": "论文 id", "reason": "为什么查但没引", "used_in": "在哪用",
    "section": "章节名", "section_plan": "对应骨架 id",
    "claims": "该节要论证的点[]", "word_budget": "字数预算",
    "cited": "引用[]", "section_type": "章节类型",
    "kind": "类别", "name": "名称", "config": "配置描述",
    "n_seeds": "种子数", "benchmark": "基准名",
    "fig_label": "图号", "caption": "图注", "for_contribution": "支撑哪条贡献",
    "placement": "body/appendix", "archetype": "图的类型学",
    "inferential_role": "推理角色", "evidence_type": "六类证据类型",
    "accepted_metrics": "领域认可指标[]", "min_fidelity": "最低保真度",
    "sample_size_norm": "样本量惯例", "control_design_norm": "对照设计惯例",
    "effect_reporting_norm": "效应报告惯例", "negative_result_norm": "阴性结果惯例",
    "exemplar_venues": "代表性 venues[]",
    "code": "类别编码", "label": "显示名", "n_papers": "论文数",
    "novelty_basis": "新颖性依据[]", "claimed_strength": "proven/supported/suggests",
    "scope": "global/module", "applicability": "适用范围",
    "verified_status": "是否已验证", "detection": "检测方法",
    "domain_tags": "适用领域[]", "outcome_class": "primary/secondary",
    "seeds": "种子数", "fidelity": "symbolic/numerical/qualitative",
    "value": "数值", "unit": "单位", "is_sota": "是否 SOTA",
    "model": "模型名", "direction": "min/max",
    "n_benchmarks": "出现基准数", "sota_model": "SOTA 模型",
    "contribution_link": "度量哪个贡献", "quote": "逐字引文",
    "source": "出处", "char_span": "字符区间", "algorithm": "算法 id",
    "ref_paper": "引用论文 id", "relation": "关系类型", "resolved": "是否解析到库内",
    "figure_min": "该节最少图数", "evidence_norm": "适用证据规范",
    "evidence_refs": "证据 id[]", "input_form": "输入形式",
    "output_form": "输出形式", "n_samples": "样本量", "scale": "规模档",
    "modality": "数据模态",
}

USAGE = {
    # 语义层
    "Paper": "复现锁定问题锚点；生成时决定范式与证据类型",
    "Algorithm": "跨论文对比方法；编译 method SAU",
    "AlgorithmModule": "method/ordering/code_grounding 三类 SAU 的来源",
    "CodeRepository": "定位原仓库；code_grounding 的入口",
    "CodeFunction": "代码对齐的落点；与模块建 MODULE_IMPLEMENTED_BY",
    "Benchmark": "protocol 决定证据门槛；数值行决定 fidelity",
    # 应用层
    "ProblemCategory": "聚类同类问题；决定章节骨架",
    "Contribution": "生成时决定主推哪条；复现时决定验证顺序",
    "ResearchGap": "生成时写 why-hard；检索时定位空白",
    "Assumption": "Type II 泄露检查；限制章节",
    "FailureMode": "审稿预演自检清单",
    "EvidenceNorm": "指标对口校验；最低保真度",
    "ExperimentArm": "实验矩阵完备性；消融规划",
    "LeaderboardEntry": "措辞许可（fidelity）；主/次结果区分",
    "MetricDefinition": "指标去重；contribution_link 对口",
    "Evidence": "主张锚定；引用支撑",
    "Limitation": "限制章节素材",
    "CitedPaper": "引用网络；三层核验",
    "SourcePaper": "科技树出处；相关工作脉络",
    "SectionPlan": "章节骨架；字数预算",
    "SectionDraft": "本次每节写什么；引用与证据挂载",
    "FigureAsset": "图表归属（正文/附录）；图-claim 绑定",
    "ReviewPoint": "最强反驳预演",
    "FailureCheck": "本次自检结论（能不能回应审稿人）",
    "ConsultedPaper": "回答「为什么没引它」",
    "DataContract": "形状探针输入；数据契约核对",
    # 代码域
    "CodeUnit": "定位「改哪个文件」；Type II 假设与失败模式落点",
    "CodeSymbol": "模块实现定位；指标计算函数",
    "Dependency": "依赖冲突排查；环境复现",
    "EntryPoint": "实验组怎么跑；复现入口",
    "TestUnit": "改完有没有测试兜底",
    "EnvSpec": "环境复现（python/cuda/packages）",
    "RunArtifact": "回答「这个数是怎么跑出来的」",
    "RelatedPaper": "任务级检索候选：本次召回谁、排第几、最终引没引",
}

NOTE = {
    "AlgorithmModule": "与 Algorithm 的 id 策略不同：算法跨论文共享，模块按论文唯一（同名会重复 9 次）。`BELONGS_TO_MODULE` 定义了但当前 0 条。",
    "Benchmark": "`table_extract:N` 与 md 的 `Table N` 不对应，回溯需靠三元组搜索。",
    "Contribution": "是「论文声称的贡献」；`numeric` SAU 是「可验证的声明」，二者不同层。",
    "ResearchGap": "任务级：只在本次写作选定后建；`mine_all` 不产出。",
    "CitedPaper": "任务级：`cited_in[]` 记录被哪几节引用；与 `SourcePaper`（全局科技树）不同。",
    "ReviewPoint": "当前仍为每条贡献固定生成 6 条，待改为按需预演。",
    "Evidence": "`used_in[]` 记录本次被哪句话使用；`char_span` 待补。",
    "ExperimentArm": "「论文做过什么」是事实；「本次复现跑哪些」应进 `METHOD_LOCK.experiment_matrix`。",
    "FailureCheck": "只记本次结论，不改 `FailureMode` 本体。",
    "ConsultedPaper": "查过但未引；与 `CitedPaper` 的差别是「没有 CITES 边」。",
    "CodeUnit": "与语义层 `CodeRepository` 不同：这里记本地仓库的实际文件，可能论文说开源但本地没 clone。",
    "CodeSymbol": "粒度停在符号级（类/函数/方法），不做行级与字段级；见 `docs/schema/CODE_DOMAIN.md` §1。",
    "RunArtifact": "任务级：只在本次执行后产生，带 `run_id`。",
    "Dependency": "从 AST import + requirements.txt 双向收集，可能含标准库。",
    "EntryPoint": "由 `if __name__ == '__main__'` 或文件名规则判定，可能把 demo 脚本也纳入。",
    "RelatedPaper": "domain_hint 只是检索线索，不参与相似度、不推导 evidence_type；"
                    "与 CitedPaper（最终引用）/ ConsultedPaper（查过未引）/ "
                    "SourcePaper（全库科技树）四种角色互不替代。",
}


def load_stats():
    from capfactory.po import POGraph
    if not GRAPH.exists():
        return {}, {}
    g = POGraph.load(str(GRAPH))
    counts, fill = Counter(), {}
    for n in g.nodes.values():
        counts[n.type] += 1
    for typ in counts:
        nodes = [n for n in g.nodes.values() if n.type == typ]
        keys = set()
        for n in nodes:
            keys |= {k for k, v in n.attrs.items() if v not in (None, "", [])}
        fill[typ] = keys
    return counts, fill


def refine_map() -> dict:
    """类 → 二次抽取目标名"""
    import yaml
    out = {}
    for p in sorted((ROOT / "data/extract_target/refine").glob("*.yaml")):
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        c = (d.get("target") or {}).get("class")
        if c:
            out.setdefault(c, []).append(d.get("refine"))
    return out


def stage_map() -> dict:
    out = {}
    for st, classes in STAGE_CLASSES.items():
        for c in classes:
            out.setdefault(c, []).append(st)
    return out


def rels_of(cls, rels, semantic: bool):
    out_edges, in_edges = [], []
    for r, spec in rels.items():
        dom, rng = spec[0], spec[1]
        note = spec[2] if len(spec) > 2 else ""
        if cls in [x.strip() for x in dom.split("|")]:
            out_edges.append((r, rng, note))
        if cls in [x.strip() for x in rng.split("|")]:
            in_edges.append((r, dom, note))
    return out_edges, in_edges


def render(cls: str, desc: str, fields, *, semantic: bool, counts, fill,
           stages, refines) -> str:
    rels = SEMANTIC_RELATIONS if semantic else APP_RELATIONS
    out_e, in_e = rels_of(cls, rels, semantic)
    n = counts.get(cls, 0)
    got = fill.get(cls, set())
    lifecycle = ("global" if semantic else
                 "task-w（写作态）" if cls in TASK_W else
                 "task-r（读态）" if cls in TASK_R else "global")
    L = [f"# `{cls}` · {desc}", "",
         f"> 层：**{'语义层' if semantic else '应用层'}** ｜ 生命周期：**{lifecycle}** "
         f"｜ 图内实例：**{n}**", ""]
    # 1 定位
    L += ["## 1. 定位", "", desc + "。", ""]
    if cls in NOTE:
        L += [NOTE[cls], ""]
    # 2 属性
    L += ["## 2. 属性", "", "| 字段 | 级别 | 说明 | 当前填充 |", "|---|---|---|---|"]
    for f in fields:
        if semantic:
            name, lv, fd = f
        else:
            name, lv = f
            fd = ATTR_DESC.get(name, "")
        mark = "✅" if name in got else ("—" if n == 0 else "❌ 0%")
        L.append(f"| `{name}` | {lv} | {fd} | {mark} |")
    L.append("")
    # 3 关系
    L += ["## 3. 关系", ""]
    if out_e:
        L += ["**出边**", "", "| 关系 | 目标 | 说明 |", "|---|---|---|"]
        L += [f"| `{r}` | {t} | {note} |" for r, t, note in out_e]
        L.append("")
    if in_e:
        L += ["**入边**", "", "| 关系 | 来源 | 说明 |", "|---|---|---|"]
        L += [f"| `{r}` | {d} | {note} |" for r, d, note in in_e]
        L.append("")
    if not out_e and not in_e:
        L += ["（无关系）", ""]
    # 4 抽取
    L += ["## 4. 抽取来源", ""]
    st = stages.get(cls, [])
    if st:
        L.append(f"- 一次抽取：{'、'.join('`'+x+'`' for x in st)}")
    if refines.get(cls):
        L.append(f"- 二次抽取：{'、'.join('`'+x+'`' for x in refines[cls])}")
    if not st and not refines.get(cls):
        L.append("- 规则/内置映射（不经 LLM）")
    L.append("")
    # 5 使用
    L += ["## 5. 使用场景", "", f"- {USAGE.get(cls, '（待补）')}", ""]
    # 6 示例
    sample = {}
    for f in fields:
        fname = f[0]
        fname_level = f[1]
        sample[fname] = f"<{fname}>" if fname_level == "must" else "..."
    L += ["## 6. 示例", "", "```json",
          json.dumps({"id": f"{ID_PREFIX.get(cls, cls.lower())}:"
                             + ("<run_id>" if cls in TASK_LEVEL else "<aid>")
                             + ":<slug>",
                      "type": cls,
                      **{k: v for k, v in list(sample.items())[:6]}},
                     ensure_ascii=False, indent=2), "```", ""]
    return "\n".join(L)


def main() -> int:
    counts, fill = load_stats()
    stages, refines = stage_map(), refine_map()
    n = 0
    for cls, (desc, fields) in SEMANTIC_CLASSES.items():
        (OUT_S / f"{cls}.md").write_text(
            render(cls, desc, fields, semantic=True, counts=counts, fill=fill,
                   stages=stages, refines=refines), encoding="utf-8")
        n += 1
    for cls, (desc, fields) in APP_CLASSES.items():
        (OUT_A / f"{cls}.md").write_text(
            render(cls, desc, fields, semantic=False, counts=counts, fill=fill,
                   stages=stages, refines=refines), encoding="utf-8")
        n += 1
    print(f"生成 {n} 份：语义层 {len(SEMANTIC_CLASSES)}，应用层 {len(APP_CLASSES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
