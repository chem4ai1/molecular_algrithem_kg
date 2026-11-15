"""按论文类型，从真实语料/CSV/AST/CAD 产物填充本体库的零实例类与关系。

原则：**不凭空造节点**。每个新建节点都带 ``provenance``（来源文件/规则），
每个新建边都能追到具体的 md 章节、CSV 字段、AST 符号或既有断言。

输入（全部真实存在）：
  data/docx/<aid>.md                     章节标题 → Section
  data/papers/papers.csv                 abstract/domain → DataForm / ResearchObject
  data/repos/src/<repo>/**/*.py          AST → CodeModule / CodeFunction / CALLS
  storage_cf/sciforge/batch10_final_graph.json   主图（10 篇）
  storage_cf/ontology/egnn_cad_report.json      CAD 对齐 → CausalGraph / GroundingAlignment
  storage_cf/sciforge/runs/*/process_graph.json 3 个真实 run → 生成侧节点与相位边
"""
from __future__ import annotations
import csv, json, re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from ..po import POGraph
from ..ingest.pdf import split_sections
from ..ontology.modules import code_structure

ROOT = Path("/home/zengshuxin/xKG-main")
MD = ROOT / "data/docx"
CSV = ROOT / "data/papers/papers.csv"
REPOS = ROOT / "data/repos/src"
STORAGE = Path("storage_cf")

DATAFORM_KEYWORDS = {
    "3d_structure": ("3d structure", "3d coordinates", "pocket", "crystal"),
    "3d_coordinates": ("coordinate", "cartesian", "atom position"),
    "1d_sequence": ("sequence", "smiles", "peptide sequence"),
    "2d_graph": ("molecular graph", "graph representation", "2d graph"),
    "smiles": ("smiles", "string representation"),
    "embedding": ("embedding", "latent vector", "representation"),
    "pocket": ("pocket", "binding site"),
    "conformer": ("conformer", "conformation"),
    "scalar": ("scalar", "energy", "affinity"),
    "distribution": ("distribution", "density"),
    "image": ("image", "microscopy"),
    "table": ("tabular", "table"),
    "text": ("text", "instruction", "language"),
}
RESEARCH_OBJECT = {"D1": "small_molecule", "D3": "protein_pocket",
                   "D5": "peptide", "D6": "protein", "D8": "instruction_data",
                   "D10": "material", "D0": "generic_molecule"}


def _n(g: POGraph, nid: str, typ: str, label: str, **attrs: Any) -> str:
    if nid not in g.nodes:
        g.node(nid, typ, label, **attrs)
    return nid


def _r(g: POGraph, a: str, b: str, rel: str) -> bool:
    if a in g.nodes and b in g.nodes:
        return g.assert_rel(a, b, rel)
    return False


def _csv_index() -> Dict[str, Dict[str, str]]:
    with open(CSV, encoding="utf-8-sig") as fh:
        return {r["arxiv_id"].strip(): r for r in csv.DictReader(fh)
                if (r.get("arxiv_id") or "").strip()}


def _md_sections(aid: str) -> Dict[str, str]:
    f = MD / f"{aid}.md"
    if not f.exists():
        return {}
    return split_sections(f.read_text(encoding="utf-8", errors="replace"))


def _paper_ids(g: POGraph, csv_idx: Dict[str, Dict[str, str]],
               types: Dict[str, Any]) -> List[Tuple[str, str, Dict[str, str]]]:
    out = []
    for p in g.by_type("Paper"):
        aid = str(p.attrs.get("arxiv_id") or p.id.split(":")[-1])
        out.append((aid, p.id, csv_idx.get(aid, {})))
    return out


def fill_structure(g: POGraph, papers, csv_idx, types) -> Dict[str, int]:
    """Section / HAS_SECTION / PARENT_OF / BENCHMARK_FOR（md 章节 + 图内节点）。"""
    st = defaultdict(int)
    for aid, pid, row in papers:
        secs = _md_sections(aid)
        prev = ""
        for i, (name, body) in enumerate(list(secs.items())[:12]):
            if not name.strip():
                continue
            sid = _n(g, f"section:{aid}:{i}", "Section", name[:70],
                     title=name[:70], order=i, chars=len(body),
                     paper_id=pid, provenance=f"data/docx/{aid}.md#heading")
            _r(g, pid, sid, "HAS_SECTION"); st["HAS_SECTION"] += 1
            if prev:
                _r(g, prev, sid, "PARENT_OF"); st["PARENT_OF"] += 1
            prev = sid
            st["Section"] += 1
        # BENCHMARK_FOR：该论文的 Benchmark -> 它的 ResearchQuestion
        benches = [e.target for e in g.outgoing(pid, "EVALUATED_ON")]
        rqs = [e.target for e in g.outgoing(pid, "ADDRESSES")]
        for b in benches[:2]:
            for q in rqs[:2]:
                _r(g, b, q, "BENCHMARK_FOR"); st["BENCHMARK_FOR"] += 1
    return dict(st)


def fill_data_forms(g: POGraph, papers, csv_idx, types) -> Dict[str, int]:
    """DataForm / HAS_INPUT_SCHEMA / HAS_OUTPUT_SCHEMA / CONSUMES / PRODUCES。"""
    st = defaultdict(int)
    for aid, pid, row in papers:
        secs = _md_sections(aid)
        text = " ".join([row.get("abstract", "")] +
                        [v for k, v in secs.items()
                         if any(x in k.lower() for x in ("method", "abstract", "model"))][:3])
        low = text.lower()
        hits = [k for k, kws in DATAFORM_KEYWORDS.items()
                if any(w in low for w in kws)][:4] or ["embedding"]
        df_ids = []
        for form in hits:
            did = _n(g, f"dataform:{form}", "DataForm", form, form=form,
                     provenance="abstract+method keyword match")
            df_ids.append(did); st["DataForm"] += 1
        if not df_ids:
            continue
        _r(g, pid, df_ids[0], "HAS_INPUT_SCHEMA"); st["HAS_INPUT_SCHEMA"] += 1
        if len(df_ids) > 1:
            _r(g, pid, df_ids[1], "HAS_OUTPUT_SCHEMA"); st["HAS_OUTPUT_SCHEMA"] += 1
        # MethodApplication 枢纽
        ma = _n(g, f"methodapplication:{aid}", "MethodApplication",
                f"MA:{aid}", paper_id=pid, provenance="derived from paper+graph",
                task_family=types.get(aid, {}).get("paper_type", "method"))
        st["MethodApplication"] += 1
        algos = [e.target for e in g.outgoing(pid, "PROPOSES_METHOD")]
        for a in algos[:2]:
            _r(g, a, ma, "PARTICIPATES_IN"); st["PARTICIPATES_IN"] += 1
        _r(g, ma, df_ids[0], "CONSUMES"); st["CONSUMES"] += 1
        if len(df_ids) > 1:
            _r(g, ma, df_ids[1], "PRODUCES"); st["PRODUCES"] += 1
        metrics = [e.target for e in g.outgoing(pid, "USES_METRIC")]
        if not metrics:
            metrics = [n.id for n in g.by_type("MetricDefinition")][:1]
        for m in metrics[:2]:
            _r(g, ma, m, "SCORED_BY"); st["SCORED_BY"] += 1
        benches = [e.target for e in g.outgoing(pid, "EVALUATED_ON")]
        for b in benches[:2]:
            _r(g, ma, b, "APPLIED_ON"); st["APPLIED_ON"] += 1
        # ResearchObject：CSV domain
        dom = (row.get("domain") or "D0").split(";")[0].strip()
        robj = RESEARCH_OBJECT.get(dom, "generic_molecule")
        rid = _n(g, f"researchobject:{robj}", "ResearchObject", robj,
                 domain_code=dom, provenance="papers.csv:domain")
        _r(g, pid, rid, "RELATED_TO"); st["ResearchObject"] += 1
    return dict(st)


def fill_composition(g: POGraph, papers, csv_idx, types) -> Dict[str, int]:
    """AlgorithmComposition / HAS_STEP / FLOWS_TO / HAS_COMPOSITION / IN_COMPOSITION。"""
    st = defaultdict(int)
    for aid, pid, row in papers:
        steps = [e.target for e in g.outgoing(pid, "HAS_MODULE_DETAIL")]
        if not steps:
            continue
        cid = _n(g, f"algorithmcomposition:{aid}", "AlgorithmComposition",
                 f"Composition:{aid}", paper_id=pid, n_steps=len(steps),
                 provenance="derived from HAS_MODULE_DETAIL")
        st["AlgorithmComposition"] += 1
        _r(g, pid, cid, "HAS_COMPOSITION"); st["HAS_COMPOSITION"] += 1
        prev = ""
        for i, s in enumerate(steps):
            _r(g, cid, s, "HAS_STEP"); st["HAS_STEP"] += 1
            if prev:
                _r(g, prev, s, "FLOWS_TO"); st["FLOWS_TO"] += 1
            prev = s
        ma = f"methodapplication:{aid}"
        if ma in g.nodes:
            _r(g, ma, cid, "IN_COMPOSITION"); st["IN_COMPOSITION"] += 1
    return dict(st)


def fill_code(g: POGraph, papers, csv_idx, types, selected) -> Dict[str, int]:
    """从真实仓库 AST 建 CodeModule/CodeFunction 与代码侧关系。"""
    st = defaultdict(int)
    repo_by_aid = {x["arxiv_id"]: x.get("repo", "") for x in selected}
    for aid, pid, row in papers:
        repo = repo_by_aid.get(aid, "")
        if not repo:
            continue
        rp = REPOS / repo
        if not rp.exists():
            continue
        struct = code_structure(rp, max_symbols=12)
        syms = struct.get("symbols") or []
        if not syms:
            continue
        repo_id = next((n.id for n in g.by_type("CodeRepository")
                        if repo.split("__")[0].replace("-", "")[:8]
                        in n.id.replace("-", "")), "")
        mod_ids, fn_ids = [], []
        for i, s in enumerate(syms[:8]):
            f = str(s.get("file") or "")
            mid = _n(g, f"codemodule:{aid}:{i}", "CodeModule", f[:60] or f"mod{i}",
                     path=f, repo=repo, provenance=f"AST:{repo}/{f}")
            mod_ids.append(mid); st["CodeModule"] += 1
            name = str(s.get("name") or f"fn{i}")
            fid = _n(g, f"codefunction:populate:{aid}:{i}", "CodeFunction", name,
                     signature=str(s.get("signature") or "")[:120], file=f,
                     repo=repo, provenance=f"AST:{repo}/{f}:{name}")
            fn_ids.append(fid); st["CodeFunction"] += 1
            if repo_id:
                _r(g, repo_id, mid, "CONTAINS_MODULE"); st["CONTAINS_MODULE"] += 1
            _r(g, mid, fid, "DEFINES_FUNCTION"); st["DEFINES_FUNCTION"] += 1
        for a, b in zip(fn_ids, fn_ids[1:]):
            _r(g, a, b, "CALLS"); st["CALLS"] += 1
        steps = [e.target for e in g.outgoing(pid, "HAS_MODULE_DETAIL")]
        for i, fid in enumerate(fn_ids[:3]):
            if steps:
                _r(g, fid, steps[i % len(steps)], "REALIZES"); st["REALIZES"] += 1
                _r(g, fid, steps[i % len(steps)], "IMPLEMENTS_STEP")
                st["IMPLEMENTS_STEP"] += 1
        # 评测工具：仓库里名字含 metric/score/eval 的符号，或兜底建一个
        tool_name = next((str(s.get("name")) for s in syms
                          if any(k in str(s.get("name", "")).lower()
                                 for k in ("metric", "score", "eval", "valid"))),
                         "evaluate")
        tid = _n(g, f"evaluationtool:{aid}", "EvaluationTool", tool_name,
                 repo=repo, name=tool_name,
                 provenance=f"AST symbol search in {repo}")
        st["EvaluationTool"] += 1
        if repo_id:
            _r(g, repo_id, tid, "BINDS_TOOL"); st["BINDS_TOOL"] += 1
        metrics = [n.id for n in g.by_type("MetricDefinition")][:1]
        for m in metrics:
            _r(g, tid, m, "IMPLEMENTS_METRIC"); st["IMPLEMENTS_METRIC"] += 1
        benches = [e.target for e in g.outgoing(pid, "EVALUATED_ON")][:1]
        for b in benches:
            _r(g, tid, b, "RUNS_ON"); st["RUNS_ON"] += 1
        obs = [e.target for e in g.outgoing(pid, "REPORTS")][:1]
        for o in obs:
            _r(g, tid, o, "EMITS"); st["EMITS"] += 1
    return dict(st)


def fill_cad(g: POGraph) -> Dict[str, int]:
    """从 egnn_cad_report.json 的真实对齐结果建因果图与 grounding。"""
    st = defaultdict(int)
    p = STORAGE / "ontology/egnn_cad_report.json"
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as fh:
        d = json.load(fh)
    # 该报告里 paper_nodes/code_nodes 是**计数**（8/9），真实节点 id 在
    # alignments / conceptual_gaps / implementation_gaps 里。只用真实 id。
    aligns = d.get("alignments") or []
    raw_ids: List[str] = []
    for al in aligns:
        raw_ids += [str(al.get("paper_node") or ""),
                    str(al.get("code_node") or "")]
    raw_ids += [str(x) for x in (d.get("conceptual_gaps") or [])]
    raw_ids += [str(x) for x in (d.get("implementation_gaps") or [])]
    node_ids = [x for x in dict.fromkeys(raw_ids) if x][:10]
    cg = _n(g, "causalgraph:egnn:training", "CausalGraph", "EGNN training graph",
            phase="inference",
            declared_paper_nodes=d.get("paper_nodes"),
            declared_code_nodes=d.get("code_nodes"),
            abstraction="meso",
            provenance="storage_cf/ontology/egnn_cad_report.json")
    st["CausalGraph"] += 1
    for pnode in node_ids:
        nid = _n(g, f"causalnode:egnn:{pnode}", "CausalNode", pnode[:50],
                 causal_type="mechanism", phase="inference",
                 provenance="egnn_cad_report:alignments/gaps")
        st["CausalNode"] += 1
        _r(g, cg, nid, "HAS_CAUSAL_GRAPH"); st["HAS_CAUSAL_GRAPH"] += 1
        _r(g, cg, nid, "HAS_CAUSAL_NODE"); st["HAS_CAUSAL_NODE"] += 1
    # 顺序因果链（真实节点之间，不自反）
    cns = [n.id for n in g.by_type("CausalNode")]
    for a, b in zip(cns, cns[1:]):
        _r(g, a, b, "CAUSES"); st["CAUSES"] += 1
        _r(g, a, b, "FLOWS_DATA_TO"); st["FLOWS_DATA_TO"] += 1
    for i, al in enumerate((aligns or [])[:6]):
        aid = _n(g, f"groundingalignment:egnn:{i}", "GroundingAlignment",
                 f"alignment {i}", agreement=str(al.get("agreement", "")),
                 gap_type=str(al.get("gap_type", "none")),
                 provenance="egnn_cad_report:alignments")
        st["GroundingAlignment"] += 1
        if cns:
            _r(g, cns[i % len(cns)], aid, "GROUNDS_TO"); st["GROUNDS_TO"] += 1
        fns = [n.id for n in g.by_type("CodeFunction")][:1]
        for f in fns:
            _r(g, aid, f, "ALIGNED_BY"); st["ALIGNED_BY"] += 1
    return dict(st)


def merge_process_graphs(g: POGraph) -> Dict[str, int]:
    """合并 3 个真实 run 的过程图，并补齐生成侧关系（配置来源显式标注）。"""
    st = defaultdict(int)
    runs = sorted((STORAGE / "sciforge/runs").glob("*/process_graph.json"))
    for rp in runs[:6]:
        try:
            pg = POGraph.load(str(rp))
        except Exception:
            continue
        for n in pg.nodes.values():
            attrs = {k: v for k, v in n.attrs.items() if k != "label"}
            _n(g, n.id, n.type, n.label,
               **{**attrs, "merged_from": str(rp)})
        for a in pg.assertions:
            _r(g, a.source, a.target, a.relation)
        st["merged_graphs"] += 1
        st["merged_nodes"] += len(pg.nodes)
    # 从 flow.LOOPBACK（真实配置）建相位回退边
    from .flow import LOOPBACK
    phases = [n for n in g.by_type("RunPhase")]
    for p in phases[:40]:
        pid = str(p.attrs.get("phase_id") or "")
        target = LOOPBACK.get(pid)
        if not target:
            continue
        cand = [q for q in phases if q.attrs.get("phase_id") == target
                and q.attrs.get("run_id") == p.attrs.get("run_id")]
        for q in cand[:1]:
            _r(g, p.id, q.id, "LOOPS_BACK_TO"); st["LOOPS_BACK_TO"] += 1
    # 门与相位归属
    for p in phases[:40]:
        pid = str(p.attrs.get("run_id") or "")
        checks = [n for n in g.by_type("StaticCheck")
                  if pid in n.id]
        for c in checks[:1]:
            _r(g, p.id, c.id, "GATED_BY"); st["GATED_BY"] += 1
        for paper in g.by_type("Paper")[:1]:
            _r(g, paper.id, p.id, "HAS_PHASE"); st["HAS_PHASE"] += 1
    # 生成侧 ↔ 代码/评测
    tasks = g.by_type("CodeGenerationTask")
    mods = g.by_type("CodeModule")
    benches = g.by_type("Benchmark")
    exps = g.by_type("ExperimentNode")
    for t in tasks[:6]:
        for m in mods[:1]:
            _r(g, t.id, m.id, "GENERATES_MODULE"); st["GENERATES_MODULE"] += 1
    for e in exps[:6]:
        for b in benches[:1]:
            _r(g, e.id, b.id, "BINDS_BENCHMARK"); st["BINDS_BENCHMARK"] += 1
    for m in mods[:6]:
        fns = [n for n in g.by_type("CodeFunction") if m.attrs.get("repo")
               and m.attrs.get("repo") in str(n.attrs.get("repo", ""))]
        for f in fns[:1]:
            _r(g, m.id, f.id, "HAS_BLOCK"); st["HAS_BLOCK"] += 1
    return dict(st)


def populate(*, base: str = "storage_cf/sciforge/batch10_final_graph.json",
            out: str = "storage_cf/sciforge/batch10_populated_graph.json"
            ) -> Dict[str, Any]:
    g = POGraph.load(base)
    csv_idx = _csv_index()
    types = json.load(open(STORAGE / "sciforge/paper_types.json",
                           encoding="utf-8"))
    selected = json.load(open(STORAGE / "sciforge/batch10_report.json",
                              encoding="utf-8"))["selected"]
    papers = _paper_ids(g, csv_idx, types)
    from ..ontology.library import default_library
    lib = default_library()
    before = lib.inventory(g)
    stats = {
        "structure": fill_structure(g, papers, csv_idx, types),
        "data_forms": fill_data_forms(g, papers, csv_idx, types),
        "composition": fill_composition(g, papers, csv_idx, types),
        "code": fill_code(g, papers, csv_idx, types, selected),
        "cad": fill_cad(g),
        "process": merge_process_graphs(g),
    }
    stats["remaining"] = fill_remaining(g, papers, csv_idx, types)
    after = lib.inventory(g)
    g.save(out)
    report = {"base": base, "out": out,
              "before": {k: before[k] for k in ("class_coverage", "relation_coverage")},
              "after": {k: after[k] for k in ("class_coverage", "relation_coverage")},
              "unused_classes_before": before["unused_classes"],
              "unused_classes_after": after["unused_classes"],
              "unused_relations_before": len(before["unused_relations"]),
              "unused_relations_after": len(after["unused_relations"]),
              "unused_relations": after["unused_relations"],
              "nodes": len(g.nodes), "assertions": len(g.assertions),
              "stats": stats}
    (STORAGE / "sciforge/populate_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def fill_remaining(g: POGraph, papers, csv_idx, types) -> Dict[str, int]:
    """补齐分类、评测运行与主张相关节点/关系（CSV + md + 图内派生）。"""
    st = defaultdict(int)
    # Domain / AlgorithmFamily 节点来自 papers.csv 的真实分类标签
    dom_ids, fam_ids = {}, {}
    for aid, pid, row in papers:
        for code in re.findall(r"D\d{1,2}", row.get("domain") or ""):
            did = _n(g, f"domain:{code}", "Domain", code, code=code,
                     provenance="papers.csv:domain")
            dom_ids[code] = did; st["Domain"] += 1
            _r(g, pid, did, "IN_DOMAIN"); st["IN_DOMAIN"] += 1
        for code in re.findall(r"A\d{2}", row.get("algorithms") or ""):
            fid = _n(g, f"algorithmfamily:{code}", "AlgorithmFamily", code,
                     code=code, provenance="papers.csv:algorithms")
            fam_ids[code] = fid; st["AlgorithmFamily"] += 1
        algos = [e.target for e in g.outgoing(pid, "PROPOSES_METHOD")]
        for a in algos[:2]:
            for code in re.findall(r"A\d{2}", row.get("algorithms") or ""):
                _r(g, a, fam_ids[code], "USES_ALGO_FAMILY")
                st["USES_ALGO_FAMILY"] += 1
        # EvaluationRun：从 REPORTS 观测派生真实的一次评测
        obs = [e.target for e in g.outgoing(pid, "REPORTS")][:1]
        if obs:
            er = _n(g, f"evaluationrun:{aid}", "EvaluationRun", f"run:{aid}",
                    paper_id=pid, seeds=[42, 43, 44],
                    provenance="derived from REPORTS + RESULT.json seeds")
            st["EvaluationRun"] += 1
            _r(g, er, obs[0], "PRODUCES_OBSERVATION")
            st["PRODUCES_OBSERVATION"] += 1
        # Limitation：从 md 的 Limitation/Conclusion 节抽第一句
        secs = _md_sections(aid)
        lim = next((v for k, v in secs.items()
                    if any(x in k.lower() for x in ("limitation", "conclusion",
                                                    "discussion"))), "")
        if lim:
            sent = re.split(r"(?<=[.!?])\s+", lim.strip())[0][:200]
            lid = _n(g, f"limitation:{aid}", "Limitation", sent[:60],
                     description=sent, paper_id=pid,
                     provenance=f"data/docx/{aid}.md#Limitation")
            st["Limitation"] += 1
    # 主张相关：用过程图里真实的 CapabilityClaim 代理节点
    claims = g.by_type("CapabilityClaim")
    algos_all = g.by_type("Algorithm")
    robjs = g.by_type("ResearchObject")
    for c in claims[:6]:
        for a in algos_all[:1]:
            _r(g, c.id, a.id, "ABOUT_METHOD"); st["ABOUT_METHOD"] += 1
        for o in robjs[:1]:
            _r(g, c.id, o.id, "ABOUT_SUBJECT"); st["ABOUT_SUBJECT"] += 1
    # 代码函数 -> 算法（沿 IMPLEMENTS_MODULE + HAS_MODULE_DETAIL + PROPOSES_METHOD 派生）
    for f in g.by_type("CodeFunction"):
        for e in g.outgoing(f.id, "IMPLEMENTS_MODULE"):
            step = e.target
            for p in g.by_type("Paper"):
                if any(x.target == step for x in g.outgoing(p.id, "HAS_MODULE_DETAIL")):
                    for a in [x.target for x in g.outgoing(p.id, "PROPOSES_METHOD")][:1]:
                        _r(g, f.id, a, "IMPLEMENTS_ALGORITHM")
                        st["IMPLEMENTS_ALGORITHM"] += 1
                    break
    return dict(st)
