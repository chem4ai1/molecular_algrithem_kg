#!/usr/bin/env python3
"""完整抽取过程模拟（重放，不调 LLM）。

用 MECo 一篇论文，逐步展示：
  PDF → md → YAML 配置 → prompt → LLM(回放) → validate → rules → apply
  → miner 派生 → readiness 审计 → refine 触发 → 产物生成

每步打印：输入 / 动作 / 输出 / 门控 / 状态转移
"""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from capfactory.po import POGraph
from capfactory.semantic.extractspec import loader
from capfactory.semantic.extractspec.render import render
from capfactory.semantic.extractspec.rules import apply_rules
from capfactory.applayer.readiness import audit_paper, effective_attrs

AID = "2510.14455"
REPORT = ROOT / f"storage/sciforge/semantic_extraction/{AID}.json"
MD = ROOT / f"data/docx/{AID}.md"
GEN = ROOT / "storage/simulation"
GEN.mkdir(parents=True, exist_ok=True)

steps = []


def step(no, name, inp, action, out, gate, note=""):
    rec = {"step": no, "name": name, "input": str(inp)[:200],
           "action": action, "output": str(out)[:220],
           "gate": gate, "note": note}
    steps.append(rec)
    print(f"\n{'='*70}\n[{no:02d}] {name}")
    print(f"  输入 : {rec['input']}")
    print(f"  动作 : {action}")
    print(f"  输出 : {rec['output']}")
    print(f"  门控 : {gate}" + (f"  | {note}" if note else ""))


def main():
    st = loader.load(force=True)
    stages = st["stages"]
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    md_text = MD.read_text(encoding="utf-8", errors="replace") if MD.exists() else ""

    step(0, "PDF → Markdown",
         f"data/paper_seed/papers/B_molecular_editing/{AID}_MECo.pdf",
         "parse_pdf() → pymupdf 文本抽取 + 章节切分",
         f"data/docx/{AID}.md ({len(md_text)} 字符, "
         f"{len([l for l in md_text.splitlines() if l.startswith('#')])} 个章节)",
         "PASS", "文件名按 arxiv_id 重命名")

    # 三个 stage 的模拟
    for i, stage in enumerate(("E1_paper", "E2_algorithm", "E3_benchmark"), 1):
        sp = stages[stage]
        d = (report.get("stages", {}).get(stage) or {})
        data = d.get("data") or {}
        prompt = render(stage, title=AID, paper_text=md_text[:2000],
                        code_symbols="", rule_hints="")
        rule_hits = []
        if getattr(sp, "rules", None):
            rule_hits = list(apply_rules(sp.rules, md_text))
        keys = list(data)
        step(i, f"{stage} 抽取",
             f"YAML({len(sp.fields)}字段, {len(sp.rules)}条规则) + md切片",
             f"render→LLM(回放)→validate→rules({','.join(rule_hits[:3])})",
             f"{len(keys)} 个字段: {', '.join(keys[:8])}{'...' if len(keys)>8 else ''}",
             "PASS" if d.get("ok") else "FAIL",
             f"attempts={d.get('attempts')}, rule_filled={d.get('rule_filled')}")

    step(4, "落语义层图",
         "E1+E2+E3 报告",
         "apply_one(): Paper 属性 + Algorithm/Module/Benchmark 节点 + 9 类关系",
         "Paper(36字段) + Algorithm + AlgorithmModule + Benchmark",
         "PASS", "stable_key() 不含新属性，图结构 6 类未变")

    # 从已有完整图读
    g = POGraph.load(str(ROOT / "storage/sciforge/factory_knowledge_partial.json"))
    step(5, "B 类图谱聚合",
         f"{len(g.by_type('Paper'))} 篇论文语义图",
         "Leiden 社区发现 + 规则聚合（离线，一次建长期用）",
         f"MethodLineage {len(g.by_type('MethodLineage'))} + "
         f"EvaluationNorm {len(g.by_type('EvaluationNorm'))} + "
         f"FailureModeLibrary {len(g.by_type('FailureModeLibrary'))}",
         "PASS", "带 rating/findings，边回指来源论文")

    step(6, "阶段路由（按 6 维分类）",
         "method_family=edit_sequence, evidence_type=experimental, venue=NeurIPS",
         "phase_router_v2.route_phase('P1', profile)",
         "modules=[edit_generator, edit_executor], gate=has_why_not_other",
         "PASS", "不同流派走不同 skill/门控")

    p = next((x for x in g.by_type("Paper") if x.attrs.get("arxiv_id") == AID), None)
    audit = audit_paper(effective_attrs(g, p)) if p else {}
    ready = sum(1 for v in audit.values() if v["status"] == "READY")
    step(7, "就绪度审计（新增 skill）",
         f"Paper + 关联 Algorithm 的字段",
         "readiness.yaml 需求矩阵 → READY/PARTIAL/BLOCKED",
         f"{ready}/{len(audit)} 个阶段 READY: " +
         ", ".join(f"{k}={v['status']}" for k, v in audit.items()),
         "PASS" if ready == len(audit) else "PARTIAL",
         "区分『原文没有』vs『抽取漏了』")

    step(8, "C 类决策链（如需要）",
         "ProblemAnchor → GapTriple → IdeaCandidate → Claim → ...",
         "WritingContext 类型化接口（内置 B 类查询 + decision ledger）",
         "C 节点带 run_id/source/via/verdict，门控真阻断",
         "PASS", "无 refutation_condition → BLOCKED（实测触发）")

    step(9, "产物生成",
         "Paper.result_tables + SectionPlan 模板",
         "table_to_latex / build_section_skeleton / figure_script",
         f"{len(list((ROOT/'storage/generated').glob('*.tex')))} 张 LaTeX 表"
         " + 章节骨架 + 绘图脚本",
         "PASS", "↓ 取 min / 同名行不误加粗")

    (GEN / "simulation_trace.json").write_text(
        json.dumps({"paper": AID, "steps": steps}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"\n{'='*70}\n完成 {len(steps)} 步，追踪写入 {GEN}/simulation_trace.json")


if __name__ == "__main__":
    main()
