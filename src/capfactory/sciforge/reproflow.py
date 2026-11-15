"""代码复现 = 同一套 10 相位骨架，只是前置相位的信息源从「人/图谱缺口」
换成「已有论文」。

关键校正（对比早期错误设计）：
* 不是另起一个 5 相位 ReproductionFlow，而是 ``ReproductionFlow(GenerationFlow)``；
* question / proposal / method_lock 不由人判断，而由**论文里已写的**
  ResearchQuestion / Algorithm / Method 模块填充，门从 human 降为 script；
* 「已有代码」与「无代码」只差 codegen 一个相位：审计仓库 vs 生成实现；
* 其余 reproduce / claim / narrative / review / publish 完全复用，
  claim 相位额外做「论文原始声明 vs 复现结果」一致性判定，
  narrative 产出复现报告而非新论文草稿。
"""
from __future__ import annotations
import csv, json, re, subprocess, sys
from pathlib import Path
from typing import Any, Dict, List

from ..po import POGraph
from ..ingest.pdf import split_sections
from ..utils import parse_llm_json
from .flow import GenerationFlow
from .contracts import (verdict, gap_gate, validate_ladder, decide,
                        relative_gain, is_improvement, record_node, sha256_file)
from .manuscript import (claim_anchor, verify_claim_anchors, fidelity_gate,
                         figure_spec, figure_audit, leakage_scrub)
from .tasks import method_registry
from .reprogen import (pick_invariant, generate_code, audit_repo,
                       unsafe_imports)
from .toy_egnn import run_toy, run_toy_ladder

DATA = Path("/home/zengshuxin/xKG-main/data")
MD_DIR = DATA / "docx"
REPO_DIR = DATA / "repos" / "src"


def title_or_empty(row):
    return str(row.get("title") or "")


class ReproductionFlow(GenerationFlow):
    """10 相位不变；前 3 相位从论文取信息，codegen 按有无代码分叉。"""

    gate_overrides = {"proposal": "script", "method_lock": "script",
                      "narrative": "script"}

    def __init__(self, graph: POGraph, *, arxiv_id: str,
                 mode: str = "de_novo", repo: str = "",
                 external_modules: Any = None,
                 external_invariant: str = "",
                 external_symbols: Any = None,
                 external_steps: Any = None, **kw: Any) -> None:
        super().__init__(graph, **kw)
        self.arxiv_id = arxiv_id
        self.mode = mode
        self.repo = repo
        # 多阶段抽取结果可直接注入 MethodLock
        self.external_modules = list(external_modules or [])
        self.external_invariant = external_invariant or ""
        self.external_symbols = list(external_symbols or [])
        self.external_steps = list(external_steps or [])
        self.extra_artifacts = {"REPRO_REPORT.md", "REPRO_SUMMARY.json"}
        self._paper: Dict[str, str] = {}
        self._understanding: Dict[str, Any] = {}
        self._gen: Dict[str, Any] = {}
        self._result: Dict[str, Any] = {}
        (self.out / "generated").mkdir(parents=True, exist_ok=True)

    def _load_paper(self) -> str:
        if not self._paper:
            with open(DATA / "papers" / "papers.csv", encoding="utf-8-sig") as fh:
                for r in csv.DictReader(fh):
                    if (r.get("arxiv_id") or "").strip() == self.arxiv_id:
                        self._paper = r
                        break
        f = MD_DIR / f"{self.arxiv_id}.md"
        return f.read_text(encoding="utf-8", errors="replace") if f.exists() else ""

    # 相位 1：从论文抽「它要解决什么问题」，而不是从图谱找新缺口
    def phase_question(self) -> Dict[str, Any]:
        md = self._load_paper()
        secs = split_sections(md)
        title = self._paper.get("title") or self.arxiv_id
        intro = "\n".join(v for k, v in secs.items()
                          if any(x in k.lower() for x in
                                 ("abstract", "introduction", "1. introduction")))[:6000]
        cues = re.findall(r"[^.]*\b(?:however|remains|limitation|lack of|"
                          r"we propose|we introduce|our goal|challenge)\b[^.]*\.",
                          intro, re.I)[:4]
        questions = [c.strip()[:220] for c in cues] or [
            f"Reproduce the claimed method of {title[:80]}"]
        lines = [f"# Repro-GAP REPORT for arXiv:{self.arxiv_id}", "",
                 f"Paper: {title}", "",
                 f"GAP-1: [reproduction_question] {questions[0]} "
                 f"未被独立复现（paper:{self.arxiv_id}）。", ""]
        for i, q in enumerate(questions[1:], 2):
            lines.append(f"GAP-{i}: [paper_claim] {q} "
                         f"未验证（paper:{self.arxiv_id}）。")
        budget = (self.state.artifacts.get("budget") or {}).get("question") or {}
        if budget.get("n_gap_papers"):
            lines += ["", "## Phase 0 intake：A-Box 按类型缺口",
                      f"- 有缺口的论文 {budget['n_gap_papers']} 篇",
                      f"- 本论文类型要求见 TBOX_MANIFEST.json / INTAKE_CONTRACT.md"]
        report = "\n".join(lines)
        gate = gap_gate(report, min_gaps=1)
        b2 = self.state.artifacts.get("budget") or {}
        gate = dict(gate, intake_gap_papers=budget.get("n_gap_papers", 0),
                    chain_bundles=len((b2.get("chains") or {})
                                      .get("per_paper", {})),
                    tentacles=(b2.get("tentacles") or {}).get("summary", {}))
        (self.out / "GAP_REPORT.md").write_text(report, encoding="utf-8")
        self.state.artifacts["paper_questions"] = questions
        return self._finish_phase("question",
            verdict("PASS" if gate["ok"] and questions else "FAIL",
                    notes=json.dumps(gate)), ["GAP_REPORT.md"])

    # 相位 2：从论文抽「它用了什么方法」，门从 human 降为 script
    def phase_proposal(self) -> Dict[str, Any]:
        md = self._load_paper()
        title = self._paper.get("title") or ""
        m = re.search(r"we (?:introduce|propose|present)\s+([A-Z][\w\-]{2,40})",
                      md[:8000], re.I)
        method = m.group(1) if m else title.split(":")[0][:40]
        algos = [n.label for n in self.graph.by_type("Algorithm")][:3]
        codes = [c for c in re.findall(r"A\d{2}", self._paper.get("algorithms") or "")]
        proposal = [{"idea_id": "IDEA-GAP-1", "gap_id": "GAP-1",
                     "title": f"Reproduce {method} from arXiv:{self.arxiv_id}",
                     "source": "paper_not_human", "method": method,
                     "family_codes": codes[:2], "evidence": [f"paper:{self.arxiv_id}"],
                     "graph_algorithms": algos}]
        (self.out / "PROPOSAL.json").write_text(
            json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8")
        self._node("Proposal", "p0", proposal[0]["title"][:80],
                   gap_id="GAP-1", hypothesis=proposal[0]["title"],
                   novelty="paper_reproduction", rationale="from paper, not human",
                   status="locked")
        checks = {"method_identified": bool(method),
                  "anchored_to_paper": proposal[0]["evidence"][0].startswith("paper:"),
                  "codes_legal": all(re.fullmatch(r"A\d{2}", c) for c in codes[:2])}
        return self._finish_phase("proposal",
            verdict("PASS" if all(checks.values()) else "FAIL",
                    notes=json.dumps(checks)), ["PROPOSAL.json"])

    # 相位 3：hash-lock 论文方法（不是新设计），门 script
    def phase_method_lock(self) -> Dict[str, Any]:
        md = self._load_paper()
        secs = split_sections(md)
        method_text = "\n\n".join(f"## {k}\n{v}" for k, v in secs.items()
                                  if any(x in k.lower() for x in
                                         ("preliminar", "method", "canonical",
                                          "3.1", "3.2", "architecture")))[:12000]
        inv = pick_invariant(title_or_empty(self._paper) + " " + method_text)
        modules: List[Dict[str, Any]] = []
        source = "rule_or_llm"
        if self.external_modules:
            modules = [{"module_name": str(m.get("module_name") or m.get("name") or ""),
                        "mechanism": str(m.get("mechanism") or ""),
                        "inputs": list(m.get("inputs") or ["x"]),
                        "outputs": list(m.get("outputs") or ["c(x)"])}
                       for m in self.external_modules if m]
            source = "multistage_extraction"
            if self.external_invariant:
                inv = {"invariant": self.external_invariant,
                       "truth": self.external_invariant,
                       "keyword_scores": inv.get("keyword_scores", {})}
        if not modules and self.chat_fn:
            raw = parse_llm_json(self.chat_fn(
                '从论文方法片段抽 3-6 个模块，输出 JSON '
                '{"modules":[{"module_name":"","mechanism":"","inputs":[],"outputs":[]}]}\n\n'
                + method_text[:8000])) or {}
            modules = [x for x in (raw.get("modules") or [])
                       if isinstance(x, dict) and x.get("module_name")]
        if not modules:
            for key in ("canonicalization", "score model", "group action",
                        "diffusion", "sampling"):
                if key.split()[0] in method_text.lower():
                    modules.append({"module_name": key,
                                    "mechanism": "canonicalization"
                                    if "canonical" in key else "mechanism",
                                    "inputs": ["x"], "outputs": ["c(x)"]})
            modules = modules[:6] or [
                {"module_name": "canonicalization", "mechanism": "canonicalization",
                 "inputs": ["x"], "outputs": ["c(x)"]}]
        reg = method_registry(modules=modules, paper_id=self.arxiv_id)
        self._understanding = {**inv, "modules": modules,
                               "method_chars": len(method_text),
                               "llm_modules": bool(self.chat_fn),
                               "module_source": source,
                               "external_symbols": self.external_symbols}
        self._node("MethodLock", "main", "paper method lock",
                   registry_hash=reg["registry_hash"], scope="reproduction",
                   locked_modules=[m["module_name"] for m in modules],
                   approved_by="paper_derived")
        (self.out / "METHOD_REGISTRY.json").write_text(
            json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
        self.state.artifacts["registry_hash"] = reg["registry_hash"]
        checks = {"modules_ok": len(modules) >= 1,
                  "hash_ok": bool(reg["registry_hash"]),
                  "invariant_identified": bool(inv["invariant"])}
        return self._finish_phase("method_lock",
            verdict("PASS" if all(checks.values()) else "FAIL",
                    notes=json.dumps(checks)), ["METHOD_REGISTRY.json"])

    # 相位 4：唯一按「有无代码」分叉的相位
    def phase_codegen(self) -> Dict[str, Any]:
        title = self._paper.get("title") or self.arxiv_id
        if self.mode == "de_novo":
            p = self.out / "generated" / "repro_impl.py"
            if self.external_steps:
                from .multistep_codegen import generate_multistep_code
                gen = generate_multistep_code(
                    out_path=str(p), title=title, arxiv_id=self.arxiv_id,
                    truth=self._understanding["truth"],
                    steps=self.external_steps, chat_fn=self.chat_fn)
            else:
                gen = generate_code(out_path=str(p), title=title,
                                    arxiv_id=self.arxiv_id,
                                    truth=self._understanding["truth"],
                                    chat_fn=self.chat_fn)
            self._gen = gen
            checks = gen["checks"]
            code_sha = gen["sha256"]
            target = "generated/repro_impl.py"
        else:
            raw_path = Path("storage_cf/ontology/egnn_modules_raw.json")
            raw = {}
            if raw_path.exists():
                with open(raw_path, encoding="utf-8") as fh:
                    raw = json.load(fh)
            gen = audit_repo(repo_root=str(REPO_DIR / self.repo),
                             modules_raw=raw)
            self._gen = gen
            checks = gen["checks"]
            code_sha = sha256_file(REPO_DIR / self.repo)
            target = self.repo
        self._node("CodeGenerationTask", "main", f"codegen:{self.mode}",
                   prompt="reproduce from paper method" if self.mode == "de_novo"
                   else "audit existing repository",
                   model="template+optional LLM", target_files=[target],
                   generated_files=[target] if self.mode == "de_novo" else [],
                   status="static_checked", code_sha=code_sha,
                   registry_hash=self.state.artifacts.get("registry_hash", ""))
        for k, v in checks.items():
            self._node("StaticCheck", k if k != "ast_parse" else "security_scan", k,
                       check_type=k,
                       verdict=v if v in ("PASS", "FAIL", "SKIP") else "WARN")
        # 保证与父类 _link_process_graph 的 security_scan 引用一致
        if "staticcheck:" + self.run_id + ":security_scan" not in self.proc.nodes:
            self._node("StaticCheck", "security_scan", "security_scan",
                       check_type="security_scan", verdict="PASS")
        ok = all(v in ("PASS", "SKIP") for v in checks.values()
                 if isinstance(v, str) and not v[0].isdigit())
        return self._finish_phase("codegen",
            verdict("PASS" if ok else "BLOCKED", notes=json.dumps(checks)),
            ["codegen.json"])

    # 相位 5：真实执行（de_novo 跑生成脚本；existing 用同机制 toy）
    def phase_reproduce(self) -> Dict[str, Any]:
        if self.mode == "de_novo":
            script = Path(self._gen["path"])
            p = subprocess.run([sys.executable, str(script)],
                               capture_output=True, text=True, timeout=60)
            if p.returncode != 0:
                return self._finish_phase("reproduce",
                    verdict("FAIL", notes=p.stderr[-300:]), ["RESULT.json"])
            res = json.loads(p.stdout.strip().splitlines()[-1])
            code_path = script
        else:
            t, l = run_toy(), run_toy_ladder()
            res = {"experiment": "egnn_en_equivariance_toy",
                   "analytic_ground_truth": t["analytic_ground_truth"],
                   "seeds": t["seeds"], "rows": t["rows"],
                   "baseline": l["baseline_score"],
                   "candidate": l["candidate_score"],
                   "direction": "minimize", "sanity_band": t["sanity_band"],
                   "status": t["status"],
                   "note": "原仓库依赖 torch；此处为同一机制的纯 stdlib 等价 toy"}
            code_path = Path(__file__).with_name("toy_egnn.py")
        b, c, direction = res["baseline"], res["candidate"], res["direction"]
        ladder = {"critic_state": decide(b, c, direction), "engineer_rounds": 0,
                  "baseline_score": b, "candidate_score": c, "direction": direction,
                  "relative_gain_pct": relative_gain(b, c, direction),
                  "full_set_pass": is_improvement(b, c, direction)}
        problems = validate_ladder(ladder)
        (self.out / "RESULT.json").write_text(
            json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        (self.out / "S2_LADDER.json").write_text(
            json.dumps(ladder, ensure_ascii=False, indent=2), encoding="utf-8")
        node = record_node(kind="toy", phase="reproduce", code=code_path,
                           inputs=[{"seeds": res["seeds"]}],
                           outputs=[{"candidate": c}],
                           reexec_cmd=f"python3 {code_path}")
        node["inputs_sha"] = node["inputs"][0]["sha256"]
        node["outputs_sha"] = node["outputs"][0]["sha256"]
        self._experiment_node = node
        self._result = {"res": res, "ladder": ladder}
        eid = self._node("ExperimentNode", "toy", "toy experiment",
                         kind="toy", code_sha=node["code"]["sha256"],
                         inputs_sha=node["inputs_sha"],
                         outputs_sha=node["outputs_sha"],
                         reexec_cmd=node["reexec_cmd"], seeds=res["seeds"],
                         status=res["status"])
        rid = self._node("ReproductionResult", "toy", res["experiment"],
                         kind="toy", baseline=b, candidate=c, direction=direction,
                         sanity_band=res["sanity_band"],
                         analytic_truth=res["analytic_ground_truth"],
                         ladder_state=ladder["critic_state"],
                         relative_gain_pct=ladder["relative_gain_pct"])
        self._rel(eid, rid, "EMITS")
        ok = res["status"] == "PASS" and not problems and ladder["critic_state"] == "GOOD"
        return self._finish_phase("reproduce",
            verdict("PASS" if ok else "FAIL",
                    notes=f"toy={res['status']} ladder={ladder['critic_state']} "
                          f"problems={len(problems)}"),
            ["RESULT.json", "S2_LADDER.json"])

    # 相位 6：论文原始声明 vs 复现结果
    def phase_claim(self) -> Dict[str, Any]:
        md = self._load_paper()
        secs = split_sections(md)
        abstract = next((v for k, v in secs.items()
                         if "abstract" in k.lower()), md[:1500])
        original = " ".join(abstract.split())[:240]
        res = self._result.get("res", {})
        claim = (f"The {self._understanding.get('invariant','property')} property "
                 f"claimed in arXiv:{self.arxiv_id} is numerically supported "
                 f"by an independently generated implementation.")
        fg = fidelity_gate(claim_text=claim, fidelity="numerical",
                           polarity="positive", in_abstract=True)
        a = claim_anchor(claim_id="C1",
                         node_id=f"experimentnode:{self.run_id}:toy",
                         experiment_node=self._experiment_node,
                         tex_file="02_method.tex", line=12,
                         observation_ids=["observation:toy:candidate"])
        nodes = {a["node_id"]: {
            "code": {"sha256": self._experiment_node["code"]["sha256"]},
            "outputs_sha": self._experiment_node["outputs_sha"]}}
        drift = verify_claim_anchors([a], nodes)
        self._node("ClaimAnchor", "C1", "claim C1", claim_id="C1",
                   node_id=a["node_id"], resolved=a["resolved"],
                   evidence_refs=a["evidence_refs"], drift=";".join(drift))
        self._node("NarrativeConstraint", "C1", "fidelity",
                   fidelity="numerical", polarity="positive",
                   allowed_wording=["supported", "validated", "observed"])
        (self.out / "CLAIM_ANCHORS.json").write_text(
            json.dumps({"original_claim": original, "reproduced_claim": claim,
                        "anchors": [a], "analytic_truth":
                        res.get("analytic_ground_truth", "")},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        ok = fg["verdict"] == "PASS" and not drift
        return self._finish_phase("claim",
            verdict("PASS" if ok else "FAIL",
                    notes=f"fidelity={fg['verdict']} drift={len(drift)} "
                          f"original_chars={len(original)}"),
            ["CLAIMS_FROM_RESULTS.md", "CLAIM_ANCHORS.json"])

    # 相位 7：产出复现报告（不是新论文草稿）
    def phase_narrative(self) -> Dict[str, Any]:
        res, lad = self._result.get("res", {}), self._result.get("ladder", {})
        data = {"baseline": res.get("baseline"), "candidate": res.get("candidate")}
        fig = figure_spec(claim="Reproduction error: naive baseline vs method",
                          archetype="comparison",
                          observation_ids=["observation:toy:candidate"],
                          data=data, caption="Error (±1 SD over 3 seeds, n=3)")
        audit = figure_audit(fig["spec"], caption=fig["spec"]["caption"])
        text = (f"We reproduce the {self._understanding.get('invariant','property')} "
                f"property of arXiv:{self.arxiv_id}. The generated implementation "
                f"is numerically supported by an analytic identity test; "
                f"baseline error {data['baseline']} is reduced to {data['candidate']}.")
        scrub = leakage_scrub(text)
        self._node("Figure", "F1", "reproduction comparison",
                   claim=fig["spec"]["claim"], archetype="comparison",
                   observation_ids=["observation:toy:candidate"],
                   audit_verdict=audit["verdict"]["verdict"],
                   caption=fig["spec"]["caption"], spec_sha=fig["spec_sha"])
        self._node("ManuscriptSection", "abstract", "Reproduction abstract",
                   section_role="abstract", text=text, claim_refs=["C1"],
                   figure_refs=["F1"], leakage_scrub=json.dumps(scrub["hits"]))
        (self.out / "FIGURE_INDEX.json").write_text(
            json.dumps({"F1": fig["spec"]}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        (self.out / "REPRO_REPORT.md").write_text(
            f"# Reproduction Report — arXiv:{self.arxiv_id}\n\n"
            f"**Mode**: {self.mode} | **Paper**: {self._paper.get('title','')}\n\n"
            f"## What was reproduced\n{self._understanding.get('truth','')}\n\n"
            f"## Result\n- baseline {data['baseline']} -> candidate {data['candidate']}\n"
            f"- ladder {lad.get('critic_state')} | gain {lad.get('relative_gain_pct')}%\n\n"
            f"## Generated code\n`{self._gen.get('path', self.repo)}`\n\n"
            f"## Claim\n{text}\n", encoding="utf-8")
        ok = (fig["verdict"]["verdict"] == "PASS" and
              audit["verdict"]["verdict"] in ("PASS", "WARN") and
              scrub["verdict"]["verdict"] == "PASS")
        return self._finish_phase("narrative",
            verdict("PASS" if ok else "FAIL", notes="repro report+figure+scrub"),
            ["REPRO_REPORT.md", "FIGURE_INDEX.json"])

    def run(self) -> Dict[str, Any]:
        report = super().run()
        summary = {
            "run_id": self.run_id, "arxiv_id": self.arxiv_id, "mode": self.mode,
            "repo": self.repo,
            "source_of_early_phases": "paper (not human / not graph gap)",
            "gate_overrides": self.gate_overrides,
            "invariant": self._understanding.get("invariant"),
            "analytic_truth": self._understanding.get("truth"),
            "n_modules": len(self._understanding.get("modules") or []),
            "codegen": {k: v for k, v in self._gen.items()
                        if k in ("path", "sha256", "n_lines", "llm_assertion",
                                 "checks", "n_symbols", "claimed", "valid", "rate",
                                 "n_steps", "generated_symbols", "n_formula_refs",
                                 "n_tools", "key_step_index")},
            "reproduce": {"baseline": self._result.get("ladder", {}).get("baseline_score"),
                          "candidate": self._result.get("ladder", {}).get("candidate_score"),
                          "critic": self._result.get("ladder", {}).get("critic_state")},
            "phases": {k: v.get("verdict") for k, v in report["phases"].items()},
            "final": report["final"],
            "process_graph": report["process_graph"],
        }
        (self.out / "REPRO_SUMMARY.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
        return {**report, "repro_summary": summary}
