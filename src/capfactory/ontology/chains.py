"""V3 组合链 T-Box：三类根族（Paper / Algorithm / Benchmark）。

替换了旧版 8 条链。依据 docs/MANUAL_ALIGNMENT_MOLMINER.md：
* C3 → P3_hypothesis：论文声明的假设/观点
* C8 → P8_solution：算法怎么被用于解决问题
* Algorithm 根：拆步骤 + 模块/公式/工具 + 代码对应
* Benchmark 根：评测值 + 数据契约（输入输出形式/对象/切分/预算/指标族/基线）
* 触手 = 换根后的延伸，按根族组织
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from .schema_v3 import ROOT_FAMILIES

GROUPS: Dict[str, Dict[str, Any]] = {
    "G1_anchor": {"label": "文献与锚点",
        "classes": ["Paper", "Section", "Evidence", "CodeRepository", "Domain"],
        "extractable": True, "question": "有哪些小节、证据锚、仓库？"},
    "G2_hypothesis": {"label": "问题与假设",
        "classes": ["ResearchQuestion", "ProblemCategory", "Hypothesis", "Limitation"],
        "extractable": True, "question": "论文声明了哪些假设/观点/局限？"},
    "G3_algorithm": {"label": "算法拆解",
        "classes": ["Algorithm", "AlgorithmFamily", "AlgorithmComposition",
                    "AlgorithmStep", "Formula", "Tool", "MethodApplication", "DataForm"],
        "extractable": True, "question": "算法拆成哪些步骤、各用什么模块/公式/工具？"},
    "G4_benchmark": {"label": "基准与数据契约",
        "classes": ["Benchmark", "DataContract", "ResearchObject", "MetricDefinition"],
        "extractable": True, "question": "基准的输入输出形式/对象、切分、预算、指标族、基线？"},
    "G5_values": {"label": "评测与数值",
        "classes": ["Observation", "LeaderboardEntry", "EvaluationRun"],
        "extractable": True, "question": "各方法报了哪些评测值？"},
    "G6_code": {"label": "代码与工具实现",
        "classes": ["CodeModule", "CodeFunction", "EvaluationTool",
                    "GroundingAlignment", "CausalGraph", "CausalNode"],
        "extractable": True, "question": "哪段代码实现了哪一步、哪个脚本算的指标？"},
    "G7_process": {"label": "生成过程（不参与抽取）",
        "classes": ["Proposal", "MethodLock", "RunPhase", "CodeGenerationTask",
                    "StaticCheck", "ExperimentNode", "ReproductionResult",
                    "ClaimAnchor", "ManuscriptSection", "Figure", "ReviewVerdict",
                    "CompileReport", "CapabilityClaim", "NarrativeConstraint"],
        "extractable": False, "question": "（不暴露）"},
}


@dataclass(frozen=True)
class ChainStep:
    node_type: str
    relation: str
    required: bool = True
    hint: str = ""
    tentacle: str = ""
    origin: str = ""      # root=从链根出发, prev=从上一环出发


@dataclass(frozen=True)
class Chain:
    chain_id: str
    group: str
    root: str
    steps: Tuple[ChainStep, ...]
    purpose: str = ""
    branch: bool = False

    def types(self) -> List[str]:
        return [self.root] + [s.node_type for s in self.steps]


CHAINS: Dict[str, Chain] = {
    # ---------- Paper 根 ----------
    "P1_structure": Chain("P1_structure", "G1_anchor", "Paper", (
        ChainStep("Section", "HAS_SECTION", hint="Markdown 章节标题",
                  tentacle="Evidence.locator"),),
        "结构锚"),
    "P2_problem": Chain("P2_problem", "G2_hypothesis", "Paper", (
        ChainStep("ResearchQuestion", "ADDRESSES",
                  hint="Introduction 的 gap / challenge 句", tentacle="假设句"),
        ChainStep("ProblemCategory", "BROADER", hint="P01–P11 词表"),),
        "问题→上位类"),
    "P3_hypothesis": Chain("P3_hypothesis", "G2_hypothesis", "Paper", (
        ChainStep("Hypothesis", "DECLARES_HYPOTHESIS",
                  hint="Introduction 的 we hypothesize / we argue / our view",
                  tentacle="Conclusion 回证"),
        ChainStep("Benchmark", "TESTS_HYPOTHESIS", required=False,
                  hint="哪个实验检验它", origin="prev"),),
        "★ C3 重定义：论文声明的假设/观点，不是能力宣称"),
    "P8_solution": Chain("P8_solution", "G3_algorithm", "ResearchQuestion", (
        ChainStep("Algorithm", "ADDRESSED_BY", hint="方法解决哪个问题"),
        ChainStep("MethodApplication", "PARTICIPATES_IN", hint="具体怎么用"),
        ChainStep("ResearchQuestion", "APPLIES_TO", hint="用回到哪个问题",
                  origin="prev"),
        ChainStep("Observation", "LEADS_TO", required=False,
                  hint="产出什么结果", origin="prev"),),
        "★ C8 重定义：算法如何被用于解决问题"),
    # ---------- Algorithm 根 ----------
    "A1_decompose": Chain("A1_decompose", "G3_algorithm", "Algorithm", (
        ChainStep("AlgorithmStep", "HAS_STEP", hint="Method 节编号步骤",
                  tentacle="步骤→模块/公式/工具"),
        ChainStep("Formula", "HAS_FORMULA", required=False,
                  hint="公式(2)(3)…", origin="prev"),
        ChainStep("Tool", "USES_TOOL", required=False,
                  hint="RDKit / force field / GMM", origin="prev"),
        ChainStep("CodeModule", "HAS_MODULE_IMPL", required=False,
                  hint="AST 文件", origin="root"),),
        "算法拆成步骤 + 各步模块/公式/工具"),
    "A2_code_grounding": Chain("A2_code_grounding", "G6_code", "Algorithm", (
        ChainStep("AlgorithmStep", "HAS_STEP", hint="mechanism+IO 对齐",
                  tentacle="代码函数"),
        ChainStep("CodeFunction", "REALIZED_BY", hint="AST 函数签名",
                  origin="prev"),
        ChainStep("GroundingAlignment", "GROUNDS_TO", required=False,
                  hint="CAD 双图", origin="prev"),),
        "代码 grounding 降级为算法链的一环"),
    # ---------- Benchmark 根 ----------
    "B1_values": Chain("B1_values", "G5_values", "Benchmark", (
        ChainStep("Algorithm", "EVALUATES_METHOD", hint="Table 里的方法列",
                  tentacle="各方法评测值"),
        ChainStep("Observation", "REPORTS_VALUE", hint="表格数值单元格",
                  origin="root"),
        ChainStep("MetricDefinition", "OF_METRIC", hint="表头指标名",
                  origin="prev"),),
        "基准上各方法的评测值", branch=True),
    "B2_data_profile": Chain("B2_data_profile", "G4_benchmark", "Benchmark", (
        ChainStep("DataContract", "HAS_DATA_CONTRACT",
                  hint="数据/实验设置节", tentacle="输入输出形式与对象"),
        ChainStep("DataForm", "HAS_INPUT_FORM", hint="输入形式：条件向量/SMILES/3D",
                  origin="root"),
        ChainStep("DataForm", "HAS_OUTPUT_FORM", hint="输出形式：SMILES/分布/坐标",
                  origin="root"),
        ChainStep("ResearchObject", "HAS_INPUT_OBJECT",
                  hint="输入对象：分子/口袋/性质向量", origin="root"),
        ChainStep("ResearchObject", "HAS_OUTPUT_OBJECT",
                  hint="输出对象：生成分子/性质分布", origin="root"),
        ChainStep("EvaluationTool", "BINDS_EVAL_TOOL", required=False,
                  hint="评测脚本", origin="root"),),
        "★ Benchmark 数据特征：形式/对象/切分/预算/指标族/基线", branch=True),
    # ---------- 引用层：根对象沿引用论文继续深挖 ----------
    "A3_source_paper": Chain("A3_source_paper", "G1_anchor", "Algorithm", (
        ChainStep("SourcePaper", "SOURCED_FROM", required=False,
                  hint="正文中「算法名 [n]」共现",
                  tentacle="沿出处论文继续挖算法"),
        ChainStep("Paper", "RESOLVED_TO", required=False,
                  hint="库内命中才连", origin="root"),),
        "Stage2：算法的出处论文，可继续深挖"),
    "B3_source_paper": Chain("B3_source_paper", "G1_anchor", "Benchmark", (
        ChainStep("SourcePaper", "SOURCED_FROM", required=False,
                  hint="正文中「基准名 [n]」共现",
                  tentacle="沿出处论文继续挖数据契约"),
        ChainStep("Paper", "RESOLVED_TO", required=False,
                  hint="库内命中才连"),),
        "Stage3：基准的出处论文，可继续深挖"),
}

# 三阶段抽取契约：被抽取对象就是根节点，其余全是它的延伸
STAGES: Dict[str, Dict[str, Any]] = {
    "stage1_paper": {"order": 1, "root": "Paper",
        "extensions": ["Section", "ResearchQuestion", "ProblemCategory",
                       "Hypothesis"],
        "purpose": "盘点论文自身与参考文献索引",
        "chains": ["P1_structure", "P2_problem", "P3_hypothesis",
                   "P8_solution"]},
    "stage2_algorithm_code": {"order": 2, "root": "Algorithm",
        "extensions": ["AlgorithmStep", "Formula", "Tool", "CodeModule",
                       "CodeFunction", "SourcePaper"],
        "purpose": "分解算法并挖掘代码内容，与代码节点结合；沿出处论文深挖",
        "chains": ["A1_decompose", "A2_code_grounding", "A3_source_paper"]},
    "stage3_benchmark": {"order": 3, "root": "Benchmark",
        "extensions": ["Observation", "MetricDefinition", "DataContract",
                       "DataForm", "ResearchObject", "SourcePaper"],
        "purpose": "基准信息量大：问题/表/方法/数据特征 + 出处论文深挖",
        "chains": ["B1_values", "B2_data_profile", "B3_source_paper"]},
}

# ---- 步骤2 触手：按根族组织 ----
TENTACLE_SPECS: Dict[str, Dict[str, Any]] = {
    "paper.hypothesis": {"root_family": "Paper", "from_chain": "P3_hypothesis",
        "source": "Introduction/Conclusion 的假设与立场句",
        "produces": ["Hypothesis", "DECLARES_HYPOTHESIS", "TESTS_HYPOTHESIS"]},
    "paper.solution_use": {"root_family": "Paper", "from_chain": "P8_solution",
        "source": "问题→方法→应用→结果链",
        "produces": ["ADDRESSED_BY", "APPLIES_TO", "LEADS_TO"]},
    "algorithm.step_decomposition": {"root_family": "Algorithm",
        "from_chain": "A1_decompose",
        "source": "Method 各节：步骤句 + 公式 + 工具名",
        "produces": ["AlgorithmStep", "Formula", "Tool", "HAS_STEP",
                     "HAS_FORMULA", "USES_TOOL"]},
    "algorithm.code_grounding": {"root_family": "Algorithm",
        "from_chain": "A2_code_grounding",
        "source": "仓库 AST + 论文机制/IO 对齐",
        "produces": ["CodeFunction", "REALIZED_BY", "HAS_MODULE_IMPL"]},
    "benchmark.evaluation_values": {"root_family": "Benchmark",
        "from_chain": "B1_values", "source": "Tables / 正文指标数值句",
        "produces": ["Observation", "REPORTS_VALUE", "EVALUATES_METHOD"]},
    "benchmark.data_profile": {"root_family": "Benchmark",
        "from_chain": "B2_data_profile",
        "source": "Experiments/Setup 节 + 评测脚本",
        "produces": ["DataContract", "HAS_INPUT_FORM", "HAS_OUTPUT_FORM",
                     "HAS_INPUT_OBJECT", "HAS_OUTPUT_OBJECT"]},
    "algorithm.source_paper": {"root_family": "Algorithm",
        "from_chain": "A3_source_paper",
        "source": "正文「算法名 [n]」共现 + 引用索引",
        "produces": ["SourcePaper", "SOURCED_FROM", "REFERS_TO", "RESOLVED_TO"]},
    "benchmark.source_paper": {"root_family": "Benchmark",
        "from_chain": "B3_source_paper",
        "source": "正文「基准名 [n]」共现 + 引用索引",
        "produces": ["SourcePaper", "SOURCED_FROM", "RESOLVED_TO"]},
}

TYPE_ALIASES = {"MetricObservation": "Observation",
                "ResearchProblem": "ResearchQuestion",
                "PaperVersion": "Paper", "ExperimentalCondition": "EvaluationRun",
                "Assay": "EvaluationRun", "Task": "ResearchQuestion",
                "CodeArtifact": "CodeRepository"}


def _type_match(actual: str, expected: str) -> bool:
    return actual == expected or TYPE_ALIASES.get(actual) == expected


def extractable_classes() -> List[str]:
    return sorted({c for g in GROUPS.values() if g["extractable"]
                   for c in g["classes"]})


def chains_summary() -> Dict[str, Any]:
    return {"groups": len(GROUPS), "chains": len(CHAINS),
            "stages": list(STAGES),
            "root_families": list(ROOT_FAMILIES),
            "tentacles": len(TENTACLE_SPECS),
            "extractable_classes": len(extractable_classes()),
            "per_root": {r: len(v["chains"]) for r, v in ROOT_FAMILIES.items()},
            "per_group": {k: len(v["classes"]) for k, v in GROUPS.items()}}


def project_chains(graph: Any, paper_id: str) -> Dict[str, Any]:
    """按论文投影三类根族的链；不给全类表。"""
    nodes = graph.nodes
    out_edges: Dict[str, List[Any]] = {}
    for a in graph.assertions:
        out_edges.setdefault(a.source, []).append(a)

    def paper_out(rel: str, typ: str) -> List[str]:
        return sorted({e.target for e in out_edges.get(paper_id, [])
                       if e.relation == rel and e.target in nodes
                       and _type_match(nodes[e.target].type, typ)})[:3]

    def roots(c: Chain) -> List[str]:
        if c.root == "Paper":
            return [paper_id] if paper_id in nodes else []
        if c.root == "Algorithm":
            return paper_out("PROPOSES_METHOD", "Algorithm") or \
                   paper_out("ADDRESSED_BY", "Algorithm")
        if c.root == "Benchmark":
            return paper_out("EVALUATED_ON", "Benchmark")
        if c.root == "ResearchQuestion":
            return paper_out("ADDRESSES", "ResearchQuestion")
        return []

    out, types_used, hints = [], set(), []
    for cid, c in CHAINS.items():
        base, cur, steps_out = roots(c), roots(c), []
        for s in c.steps:
            use_root = (s.origin == "root" or (c.branch and s.origin != "prev"))
            frontier = base if use_root else cur
            nxt: List[str] = []
            for src in frontier:
                for e in out_edges.get(src, []):
                    if e.relation == s.relation and e.target in nodes and \
                            _type_match(nodes[e.target].type, s.node_type):
                        nxt.append(e.target)
            nxt = sorted(set(nxt))
            steps_out.append({"node_type": s.node_type, "relation": s.relation,
                              "required": s.required,
                              "state": "present" if nxt else "absent",
                              "instances": nxt[:6], "hint": s.hint,
                              "tentacle": s.tentacle})
            if nxt:
                types_used.add(s.node_type)
                if s.hint:
                    hints.append(f"{cid}:{s.node_type} ← {s.hint}")
            cur = base if (c.branch and s.origin != "prev") else nxt
        req = [x for x in steps_out if x["required"]]
        state = ("PRESENT" if req and all(x["state"] == "present" for x in req)
                 else "PARTIAL" if any(x["state"] == "present" for x in steps_out)
                 else "ABSENT")
        out.append({"chain_id": cid, "group": c.group, "root": c.root,
                    "root_family": next((r for r, v in ROOT_FAMILIES.items()
                                         if cid in v["chains"]), "Paper"),
                    "purpose": c.purpose, "roots": base,
                    "steps": steps_out, "state": state, "branch": c.branch})
    if paper_id in nodes:
        types_used.add(nodes[paper_id].type)
    return {"paper_id": paper_id, "chains": out,
            "root_families": ROOT_FAMILIES, "types_used": sorted(types_used),
            "n_types": len(types_used), "extraction_hints": hints,
            "missing_required": [f"{c['chain_id']}:{s['node_type']}"
                                 for c in out for s in c["steps"]
                                 if s["required"] and s["state"] == "absent"],
            "tentacles": TENTACLE_SPECS}


def render_chain_bundle(bundle: Dict[str, Any]) -> str:
    lines = [f"# 论文链束（三类根族）— {bundle['paper_id']}", "",
             f"只涉及 {bundle['n_types']} 个类：{', '.join(bundle['types_used'])}", ""]
    for fam, spec in ROOT_FAMILIES.items():
        cs = [c for c in bundle["chains"] if c["root_family"] == fam]
        if not cs:
            continue
        lines += [f"## 根族 {fam} — {spec['label']}", ""]
        for c in cs:
            lines.append(f"### {c['chain_id']} [{c['state']}] — {c['purpose']}")
            lines.append(f"根 `{c['root']}`: {', '.join(c['roots']) or '(无)'}")
            for s in c["steps"]:
                mark = "✓" if s["state"] == "present" else "✗"
                req = "" if s["required"] else "（可选）"
                lines.append(f"  {mark} -{s['relation']}-> {s['node_type']}{req} "
                             f"{s['instances'][:3]}")
                if s["hint"]:
                    lines.append(f"      抽取线索：{s['hint']}")
            lines.append("")
    if bundle["missing_required"]:
        lines += ["## 待补的必需环", ""] + \
                 [f"- {x}" for x in bundle["missing_required"]] + [""]
    lines += ["## 步骤2 触手（换根后的延伸）", ""]
    for name, spec in bundle["tentacles"].items():
        lines.append(f"- **{name}** [{spec['root_family']}根] "
                     f"从 `{spec['from_chain']}` 出发；来源 {spec['source']}；"
                     f"产出 {', '.join(spec['produces'])}")
    return "\n".join(lines) + "\n"


# 命名统一（蓝图 P0-1）：根族阶段不再叫 Stage，保留 STAGES 别名避免打断测试
ROOT_STAGES = STAGES
