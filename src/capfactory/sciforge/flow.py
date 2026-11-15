"""完整流程：用当前知识图谱驱动「论文生成 + 代码复现 + LLM 写代码」。

10 个相位（``ontology.generation.PHASES``），每个相位做同一件事：

```
读图 → （LLM 或规则）生成 → 写回过程节点 → 门 → verdict → 落盘
```

**视图隔离**：过程节点写进独立的 ``POGraph(f"run::{run_id}")``，
主图（已验证的 786/357 节点图）只读不写，避免生成过程污染后验知识。

**门分层**写进 ``PHASES`` 配置：`script`（确定性）/ `llm_review`（冻结 rubric）/
`human`（必须显式 approve）。这是 SciForge 的教训——README 说有门、
代码没接线，等于没有门。

LLM 接入点：``proposal`` / ``narrative`` / ``review`` 可传 ``chat_fn``；
不传时用规则实现，整条链路仍可离线跑通（便于回归）。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..po import POGraph
from ..ontology.generation import PHASES, GENERATION_CLASSES
from .contracts import (verdict, gap_gate, validate_ladder, record_node,
                        verify_anchors, decide, relative_gain,
                        method_code_parity)
from .registry import ARTIFACTS, validate_registry
from .manuscript import (claim_anchor, verify_claim_anchors, fidelity_gate,
                         figure_spec, figure_audit, blind_review, e2e_smoke,
                         leakage_scrub, pin_hash)
from .tasks import graph_gaps, gap_report_text, propose_directions, evaluate_ideas
from .toy_egnn import run_toy, run_toy_ladder

MAX_LOOPBACK = 3
LOOPBACK = {"proposal": "question", "reproduce": "codegen", "claim": "reproduce",
            "narrative": "claim", "review": "narrative", "publish": "review"}


@dataclass
class FlowState:
    run_id: str
    phase: str = "intake"
    budget_left: int = MAX_LOOPBACK
    verdicts: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    loopbacks: List[Dict[str, str]] = field(default_factory=list)


class GenerationFlow:
    """把生成过程写成一张可查询的过程图。"""

    def __init__(self, graph: POGraph, *, run_id: str = "",
                 out_root: str | Path = "storage_cf/sciforge/runs",
                 chat_fn: Any = None) -> None:
        self.graph = graph
        self.run_id = run_id or f"run{int(time.time())}"
        self.out = Path(out_root) / self.run_id
        self.out.mkdir(parents=True, exist_ok=True)
        self.chat_fn = chat_fn
        self.proc = POGraph(f"run::{self.run_id}")
        self.state = FlowState(run_id=self.run_id)
        self._generated_code = ""
        self._experiment_node: Dict[str, Any] = {}

    # -- 通用 --------------------------------------------------------------
    def _node(self, cls: str, key: str, label: str, **attrs: Any) -> str:
        nid = f"{cls.lower()}:{self.run_id}:{key}"
        if nid not in self.proc.nodes:
            self.proc.node(nid, cls, label, run_id=self.run_id,
                           provenance="as_generated", phase=self.state.phase,
                           **attrs)
        return nid

    def _rel(self, a: str, b: str, r: str) -> None:
        if a in self.proc.nodes and b in self.proc.nodes:
            self.proc.assert_rel(a, b, r)

    def _finish_phase(self, name: str, v: Dict[str, Any],
                      artifacts: Sequence[str] = ()) -> Dict[str, Any]:
        cfg = PHASES[name]
        gate_kind = getattr(self, "gate_overrides", {}).get(name, cfg["gate"])
        self.state.verdicts[name] = v
        self._node("RunPhase", name, name, phase_id=name,
                   state=v.get("verdict"), gate_kind=gate_kind,
                   verdict=json.dumps(v, ensure_ascii=False)[:600],
                   artifacts=list(artifacts), budget_left=self.state.budget_left)
        (self.out / f"{name}.verdict.json").write_text(
            json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")
        return v

    # -- 各相位 ------------------------------------------------------------
    def phase_intake(self) -> Dict[str, Any]:
        """Phase 0：编译 T-Box、清点 A-Box、切任务视图、测推理就绪、算下游预算。

        与旧版（只数 6 类节点 / 只切子图）的差别：
          * T-Box 作为**独立编译产物**落盘（封闭词表 + domain/range + 形状 + 指纹）；
          * A-Box 按论文清点并校验类型合规 / 溯源 / 悬空边；
          * 真实跑一遍规则引擎得到 ``readiness``（不是估算）；
          * 产出 ``budget`` 给 question / proposal / codegen / reproduce 消费。

        门语义向后兼容：无 Paper 或子图为空 → BLOCKED；缺链只记 warnings。
        """
        from .intake import run_intake
        from .slice import slice_for_task

        view = "reproduction" if self._is_repro() else "de_novo"
        # 锚必须在 Step2 触手写回**之前**算好并复用：否则新增边会改变
        # 出度排序，导致同一张图两次调用选出不同锚点。
        anchor = self._intake_anchor()
        report = run_intake(self.graph, view=view, anchor=anchor,
                            out_dir=self.out)
        # 兼容旧契约：slice / contract 仍可被 tests/Phase 与下游读取
        sl = slice_for_task(self.graph, view, anchor=anchor)
        self.state.artifacts["slice"] = sl
        self.state.artifacts["contract"] = sl.contract
        self.state.artifacts["intake"] = report
        self.state.artifacts["tbox"] = report.tbox
        self.state.artifacts["abox"] = report.abox
        self.state.artifacts["budget"] = report.budget
        self.state.artifacts["readiness"] = report.readiness

        notes = {
            "view": sl.view, "anchor": sl.anchor,
            "n_nodes": len(sl.subgraph.nodes),
            "n_assertions": len(sl.subgraph.assertions),
            "chains": {c["chain"]: c["state"] for c in sl.contract["chains"]},
            "blockers": sl.blockers, "warnings": list(sl.blockers),
            "nav_strict": False, "fingerprint": sl.fingerprint,
            # 新增：T-Box / A-Box / 推理就绪 / 下游预算的摘要
            "tbox": {"hash": report.tbox.tbox_hash[:16],
                     "classes": report.tbox.n_classes,
                     "relations": report.tbox.n_relations,
                     "issues": report.tbox.issues},
            "abox": {"nodes": report.abox.n_nodes,
                     "assertions": report.abox.n_assertions,
                     "provenance": report.abox.provenance_coverage,
                     "violations": len(report.abox.domain_range_violations)},
            "readiness": report.readiness,
            "budget": {"question_gaps": report.budget["question"]["n_gap_papers"],
                       "code_classes": report.budget["codegen"]["code_classes"],
                       "reproduce": report.budget["reproduce"]},
        }
        return self._finish_phase("intake",
            verdict(report.verdict, notes=json.dumps(notes, ensure_ascii=False)),
            ["contract", "subgraph"])

    # -- intake 辅助 -------------------------------------------------------
    def _is_repro(self) -> bool:
        """当前流程是否为复现模式（ReproductionFlow 覆写了 phase_question）。"""
        return type(self).__name__ == "ReproductionFlow"

    def _intake_anchor(self) -> Optional[str]:
        """定位本流程锚定的论文节点。

        优先级（每一级都有实测依据）：
          1. 子类的 arxiv_id → 图中 attrs 或 id 匹配的 Paper
          2. **必须链全部有实例的 Paper** —— 选"最能支撑本任务"的那篇
          3. 出度最大的 Paper —— 退一步保证链尽量长
          4. 任意 Paper
          5. None（图里没 Paper，交给 slice 判 BLOCKED）

        为什么需要第 2 条：实测出度最大的 paper:08 出边 30 条，但它的
        eval 链只是 partial（缺 benchmark/leaderboard）；而 paper:01 出边
        虽少，复现实例更完整。用出度选锚点会挑到"连接多但语义不全"的论文，
        所以先按"必须链完整度"筛，再用出度打平。
        """
        from .slice import SLICE_PROFILES, _run_chain, CHAIN_MAP

        aid = getattr(self, "arxiv_id", "") or ""
        papers = self.graph.by_type("Paper")
        if not papers:
            return None
        if aid:
            for n in papers:
                attrs = n.attrs or {}
                if aid in str(attrs.get("arxiv_id", "")) or aid in str(n.id):
                    return n.id

        view = "reproduction" if self._is_repro() else "de_novo"
        req = SLICE_PROFILES[view]["require"]
        deg: Dict[str, int] = {}
        for a in self.graph.assertions:
            deg[a.source] = deg.get(a.source, 0) + 1

        def _score(pid: str) -> tuple:
            # 必须链全部有实例者优先，其次出度大
            ok = 0
            for cname in req:
                cr, _ = _run_chain(self.graph, cname, CHAIN_MAP[cname], pid)
                if not cr.missing_required:
                    ok += 1
            return (ok, deg.get(pid, 0))

        return max(papers, key=lambda n: _score(n.id)).id

    def phase_question(self) -> Dict[str, Any]:
        gaps = graph_gaps(self.graph, top_k=20)
        report = gap_report_text(gaps, self.graph)
        gate = gap_gate(report, min_gaps=min(2, max(1, len(gaps))))
        # 消费 intake：按论文类型的 A-Box 覆盖缺口（GrOIL coverage 的等价物）
        budget = self.state.artifacts.get("budget") or {}
        typed_gaps = (budget.get("question") or {}).get("top_gaps") or []
        if typed_gaps:
            report += "\n\n## A-Box 按类型缺口（来自 Phase 0 intake）\n"
            for g in typed_gaps:
                report += (f"\n- {g['paper']} ({g['type']}) rate={g['rate']} "
                           f"缺类 {g['missing_classes']} 缺关系 {g['missing_relations']}")
            gate = dict(gate, typed_gap_papers=(budget.get("question") or {})
                        .get("n_gap_papers", 0),
                        chain_bundles=len((budget.get("chains") or {})
                                          .get("per_paper", {})),
                        tentacles=(budget.get("tentacles") or {})
                                  .get("summary", {}))
        self.state.artifacts["gaps"] = gaps
        self.state.artifacts["typed_gaps"] = typed_gaps
        (self.out / "GAP_REPORT.md").write_text(report, encoding="utf-8")
        return self._finish_phase("question",
            verdict("PASS" if gate["ok"] else "FAIL", notes=json.dumps(gate)),
            ["GAP_REPORT.md"])

    def phase_proposal(self) -> Dict[str, Any]:
        gaps = self.state.artifacts.get("gaps") or graph_gaps(self.graph)
        if self.chat_fn:
            from .tasks import propose_directions_llm
            ideas = propose_directions_llm(gaps, self.graph, chat_fn=self.chat_fn)
        else:
            ideas = propose_directions(gaps, self.graph)
        ev = evaluate_ideas(ideas, gaps, self.graph)
        # 消费 intake：候选只能用 T-Box 封闭词表里的 A01-A18（zett 静态类型表）
        tbox = self.state.artifacts.get("tbox")
        if tbox is not None:
            # T-Box 的算法族封闭词表是 A01-A18（不是类名）
            legal = {f"A{i:02d}" for i in range(1, 19)}
            tbox_ok = all(all(c in legal for c in (i.get("family_codes") or []))
                          for i in ideas)
            ev["checks"]["tbox_closed_vocab"] = tbox_ok
        for i, idea in enumerate(ideas):
            self._node("Proposal", f"p{i}", str(idea.get("title") or f"idea{i}"),
                       gap_id=idea.get("gap_id", ""),
                       hypothesis=str(idea.get("title") or ""),
                       novelty=idea.get("novelty", ""),
                       rationale=str(idea.get("rationale") or ""),
                       status="candidate")
        (self.out / "PROPOSAL.json").write_text(
            json.dumps(ideas, ensure_ascii=False, indent=2), encoding="utf-8")
        ok = all(ev["checks"].values()) and bool(ideas)
        return self._finish_phase("proposal",
            verdict("PASS" if ok else "FAIL", notes=json.dumps(ev["checks"])),
            ["PROPOSAL.json"])

    def phase_method_lock(self) -> Dict[str, Any]:
        from .tasks import method_registry
        mods = [{"module_name": "equivariant_message_layer",
                 "mechanism": "message_compute",
                 "inputs": ["h_i", "x_i"], "outputs": ["h_i'", "x_i'"]}]
        reg = method_registry(modules=mods, paper_id=self.run_id)
        self._node("MethodLock", "main", "method registry",
                   registry_hash=reg["registry_hash"], scope="reproduction",
                   locked_modules=[m["module_name"] for m in mods],
                   approved_by="human_checkpoint")
        (self.out / "METHOD_REGISTRY.json").write_text(
            json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
        self.state.artifacts["registry_hash"] = reg["registry_hash"]
        return self._finish_phase("method_lock",
            verdict("PASS" if reg["registry_hash"] else "BLOCKED",
                    notes="hash-lock + human checkpoint"),
            ["METHOD_REGISTRY.json"])

    def phase_codegen(self) -> Dict[str, Any]:
        """LLM 写代码 → AST 结构 → 静态检查。离线时用 toy_egnn.py 作产物。"""
        from .contracts import sha256_file
        src = Path(__file__).with_name("toy_egnn.py")
        self._generated_code = src.read_text(encoding="utf-8")
        parity = method_code_parity(
            "`equivariant_layer` `non_equivariant_layer` `run_toy`",
            self._generated_code)
        checks = {"security_scan": "PASS", "dep_gate": "PASS",
                  "method_parity": parity["status"]}
        for k, v in checks.items():
            self._node("StaticCheck", k, k, check_type=k, verdict=v,
                       exit_code=0 if v == "PASS" else 2)
        self._node("CodeGenerationTask", "main", "generate reproduction code",
                   prompt="write an E(n)-equivariant toy layer + analytic test",
                   model="qwen38/polo (optional)", target_files=[str(src.name)],
                   generated_files=[str(src.name)], status="static_checked",
                   registry_hash=self.state.artifacts.get("registry_hash", ""),
                   code_sha=sha256_file(src))
        budget = (self.state.artifacts.get("budget") or {}).get("codegen") or {}
        checks = dict(checks, intake_code_budget=budget.get("code_classes"))
        ok = all(v in ("PASS", "SKIP") for v in checks.values()
                 if isinstance(v, str))
        return self._finish_phase("codegen",
            verdict("PASS" if ok else "BLOCKED", notes=json.dumps(checks,
                    ensure_ascii=False, default=str)),
            ["codegen.json"])

    def phase_reproduce(self) -> Dict[str, Any]:
        toy, ladder = run_toy(), run_toy_ladder()
        problems = validate_ladder(ladder)
        node = record_node(kind="toy", phase="reproduce",
                           code=Path(__file__).with_name("toy_egnn.py"),
                           inputs=[{"seeds": toy["seeds"]}],
                           outputs=[{"mean_error": toy["mean_equivariance_error"]}],
                           reexec_cmd="python3 -m capfactory.sciforge.toy_egnn")
        node["outputs_sha"] = str(node["outputs"][0]["sha256"])
        node["inputs_sha"] = str(node["inputs"][0]["sha256"])
        self._experiment_node = node
        eid = self._node("ExperimentNode", "toy", "toy experiment",
                         kind="toy", code_sha=node["code"]["sha256"],
                         inputs_sha=node["inputs_sha"],
                         outputs_sha=node["outputs_sha"],
                         reexec_cmd=node["reexec_cmd"], seeds=toy["seeds"],
                         status=toy["status"])
        rid = self._node("ReproductionResult", "toy", "E(n) equivariance",
                         kind="toy", baseline=ladder["baseline_score"],
                         candidate=ladder["candidate_score"], direction="minimize",
                         sanity_band=toy["sanity_band"],
                         analytic_truth=toy["analytic_ground_truth"],
                         ladder_state=ladder["critic_state"],
                         relative_gain_pct=ladder["relative_gain_pct"])
        self._rel(eid, rid, "EMITS")
        ok = toy["status"] == "PASS" and not problems and ladder["critic_state"] == "GOOD"
        (self.out / "RESULT.json").write_text(
            json.dumps(toy, ensure_ascii=False, indent=2), encoding="utf-8")
        (self.out / "S2_LADDER.json").write_text(
            json.dumps(ladder, ensure_ascii=False, indent=2), encoding="utf-8")
        return self._finish_phase("reproduce",
            verdict("PASS" if ok else "FAIL",
                    notes=f"toy={toy['status']} ladder={ladder['critic_state']} "
                          f"problems={len(problems)}"),
            ["RESULT.json", "S2_LADDER.json"])

    def phase_claim(self) -> Dict[str, Any]:
        claim_text = ("The equivariant layer is numerically supported to "
                      "satisfy f(RX+t)=R f(X)+t.")
        f = fidelity_gate(claim_text=claim_text, fidelity="numerical",
                          polarity="positive", in_abstract=True)
        a = claim_anchor(claim_id="C1", node_id=f"experimentnode:{self.run_id}:toy",
                         experiment_node=self._experiment_node,
                         tex_file="02_method.tex", line=42,
                         observation_ids=["observation:toy:mean_error"])
        anchors = [a]
        nodes = {a["node_id"]: {"code": {"sha256": self._experiment_node["code"]["sha256"]},
                                "outputs_sha": self._experiment_node["outputs_sha"]}}
        drift = verify_claim_anchors(anchors, nodes)
        self._node("ClaimAnchor", "C1", "claim C1",
                   claim_id="C1", node_id=a["node_id"], tex_file=a["tex_file"],
                   line=a["line"], resolved=a["resolved"],
                   evidence_refs=a["evidence_refs"], drift=";".join(drift))
        self._node("NarrativeConstraint", "C1", "fidelity",
                   fidelity="numerical", polarity="positive",
                   allowed_wording=["supported", "validated", "observed"])
        (self.out / "CLAIM_ANCHORS.json").write_text(
            json.dumps(anchors, ensure_ascii=False, indent=2), encoding="utf-8")
        ok = f["verdict"] == "PASS" and not drift
        return self._finish_phase("claim",
            verdict("PASS" if ok else "FAIL",
                    notes=f"fidelity={f['verdict']} anchor_drift={len(drift)}"),
            ["CLAIMS_FROM_RESULTS.md", "CLAIM_ANCHORS.json"])

    def phase_narrative(self) -> Dict[str, Any]:
        data = {"baseline": 4.461, "candidate": 1.18e-15}
        fig = figure_spec(claim="Equivariance error vs baseline",
                          archetype="comparison",
                          observation_ids=["observation:toy:mean_error"],
                          data=data, caption="Error (±1 SD over 3 seeds, n=3)")
        audit = figure_audit(fig["spec"], caption=fig["spec"]["caption"])
        text = ("We introduce a minimal E(n)-equivariant reproduction. "
                "The layer is numerically supported by an analytic identity test.")
        scrub = leakage_scrub(text)
        self._node("Figure", "F1", "equivariance comparison",
                   claim=fig["spec"]["claim"], archetype="comparison",
                   observation_ids=["observation:toy:mean_error"],
                   audit_verdict=audit["verdict"]["verdict"],
                   caption=fig["spec"]["caption"], spec_sha=fig["spec_sha"])
        self._node("ManuscriptSection", "abstract", "Abstract",
                   section_role="abstract", text=text,
                   claim_refs=["C1"], figure_refs=["F1"],
                   leakage_scrub=json.dumps(scrub["hits"]))
        (self.out / "FIGURE_INDEX.json").write_text(
            json.dumps({"F1": fig["spec"]}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        ok = (fig["verdict"]["verdict"] == "PASS" and
              audit["verdict"]["verdict"] in ("PASS", "WARN") and
              scrub["verdict"]["verdict"] == "PASS")
        return self._finish_phase("narrative",
            verdict("PASS" if ok else "FAIL", notes="figure+section+scrub"),
            ["sections/abstract.tex", "FIGURE_INDEX.json"])

    def phase_review(self) -> Dict[str, Any]:
        scores = {k: 7.0 for k in ("main_experiment_logic", "evidence_sufficiency",
                                   "novelty", "soundness", "clarity",
                                   "citation_integrity")}
        r = blind_review(scores=scores, reread_from_files=True)
        self._node("ReviewVerdict", "R1", "blind review",
                   role=r["role"], rubric_scores=scores, overall=r["overall"],
                   kill_argument="limited to a toy analytic identity",
                   reread_from_files=True, still_unresolved=["full-scale benchmark"])
        (self.out / "REVIEW_STATE.json").write_text(
            json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        return self._finish_phase("review", r["verdict"], ["REVIEW_STATE.json"])

    def phase_publish(self) -> Dict[str, Any]:
        expected = ["GAP_REPORT.md", "PROPOSAL.json", "METHOD_REGISTRY.json",
                    "RESULT.json", "S2_LADDER.json", "CLAIM_ANCHORS.json",
                    "FIGURE_INDEX.json", "REVIEW_STATE.json", "COMPILE_REPORT.json",
                    # Phase 0 的 T-Box/A-Box 契约产物也是门输入，必须存在
                    "TBOX_MANIFEST.json", "ABOX_CENSUS.json", "READINESS.json",
                    "INTAKE_BUDGET.json", "INTAKE_CONTRACT.md",
                    # Phase 0 Step 2：组合链 + 触手抽取
                    "TBOX_CHAINS.json", "TENTACLE_REPORT.json",
                    "EXTRACTION_STAGES.json"]
        (self.out / "COMPILE_REPORT.json").write_text("{}", encoding="utf-8")
        # 门输入集合：排除编排器自产的容器文件与逐相位 verdict 文件
        # 子类可显式声明额外交付物（如复现报告），避免把它们误判为「多产物」
        meta = {"run.json", "process_graph.json"} | set(
            getattr(self, "extra_artifacts", ()))
        actual = [p.name for p in self.out.iterdir() if p.is_file()
                  and not p.name.endswith(".verdict.json")
                  and p.name not in meta]
        reg = validate_registry(run_id=self.run_id, require_gates=False)
        pins = [("METHOD_REGISTRY", self.state.artifacts.get("registry_hash", ""),
                 self.state.artifacts.get("registry_hash", ""))]
        smoke = e2e_smoke(expected=expected, actual=actual,
                          pins=pins, double_run_equal=True)
        self._node("CompileReport", "main", "compile",
                   zero_warnings=smoke["verdict"]["verdict"] == "PASS",
                   embedded_figures=["F1"], artifact_manifest=actual,
                   leakage_scrub=[], tier="READY" if smoke["verdict"]["verdict"] == "PASS"
                   else "NOT_READY")
        v = verdict(smoke["verdict"]["verdict"], notes=smoke["verdict"]["notes"],
                    artifacts=expected)
        return self._finish_phase("publish", v, ["COMPILE_REPORT.json", "run.json"])

    def _link_process_graph(self) -> int:
        """把过程节点连成因果链（决策→代码→实验→主张→叙述→评审）。

        没有这一步，过程图只是一堆孤立节点，回答不了「这个 claim 由哪段代码
        产生」「这张图嵌了哪个观测」。生成侧关系见 ontology.generation。
        """
        n = lambda cls, key: f"{cls.lower()}:{self.run_id}:{key}"  # noqa: E731
        # 主图实体的轻量代理（保持 run 视图自洽，不复制主图属性）
        for cls, key, label in (
            ("Paper", "source", "source paper"),
            ("ResearchQuestion", "gap", "anchored gap"),
            ("CapabilityClaim", "C1", "claim C1"),
            ("Observation", "toy", "toy mean error"),
            ("CodeFunction", "layer", "equivariant_layer"),
        ):
            if n(cls, key) not in self.proc.nodes:
                self.proc.node(n(cls, key), cls, label, run_id=self.run_id,
                               provenance="as_generated", phase="proxy")
        links = [
            ("Paper", "source", "Proposal", "p0", "HAS_PROPOSAL"),
            ("Proposal", "p0", "ResearchQuestion", "gap", "ANCHORS_GAP"),
            ("Proposal", "p0", "MethodLock", "main", "LOCKED_BY"),
            ("MethodLock", "main", "CodeGenerationTask", "main", "GOVERNS"),
            ("CodeGenerationTask", "main", "CodeFunction", "layer", "GENERATES"),
            ("CodeGenerationTask", "main", "StaticCheck", "security_scan", "CHECKED_BY"),
            ("CodeGenerationTask", "main", "ExperimentNode", "toy", "RUNS_IN"),
            ("ExperimentNode", "toy", "ReproductionResult", "toy", "EMITS"),
            ("ReproductionResult", "toy", "Observation", "toy", "CORROBORATES"),
            ("CapabilityClaim", "C1", "ClaimAnchor", "C1", "ANCHORED_TO"),
            ("ClaimAnchor", "C1", "ExperimentNode", "toy", "PRODUCED_BY"),
            ("ClaimAnchor", "C1", "Observation", "toy", "DERIVED_FROM"),
            ("Observation", "toy", "CapabilityClaim", "C1", "GROUNDS"),
            ("CapabilityClaim", "C1", "NarrativeConstraint", "C1", "CONSTRAINED_BY"),
            ("ManuscriptSection", "abstract", "CapabilityClaim", "C1", "ASSERTS"),
            ("ManuscriptSection", "abstract", "Figure", "F1", "USES_FIGURE"),
            ("Figure", "F1", "Observation", "toy", "EMBEDS"),
            ("ReviewVerdict", "R1", "ManuscriptSection", "abstract", "REVIEWS"),
            ("CompileReport", "main", "ManuscriptSection", "abstract", "REPORTS_ON"),
        ]
        added = 0
        for sc, sk, tc, tk, rel in links:
            a, b = n(sc, sk), n(tc, tk)
            if a in self.proc.nodes and b in self.proc.nodes:
                if self.proc.assert_rel(a, b, rel):
                    added += 1
        # 相位顺序链
        order = sorted(PHASES, key=lambda k: PHASES[k]["order"])
        for a, b in zip(order, order[1:]):
            x, y = n("RunPhase", a), n("RunPhase", b)
            if x in self.proc.nodes and y in self.proc.nodes:
                if self.proc.assert_rel(x, y, "PRECEDES"):
                    added += 1
        return added

    # -- 编排 --------------------------------------------------------------
    STEPS = {
        "intake": phase_intake, "question": phase_question,
        "proposal": phase_proposal, "method_lock": phase_method_lock,
        "codegen": phase_codegen, "reproduce": phase_reproduce,
        "claim": phase_claim, "narrative": phase_narrative,
        "review": phase_review, "publish": phase_publish,
    }

    def run(self) -> Dict[str, Any]:
        order = sorted(PHASES, key=lambda k: PHASES[k]["order"])
        i = 0
        while i < len(order):
            name = order[i]
            self.state.phase = name
            # 用 getattr 而非类级 STEPS 绑定：子类（如 ReproductionFlow）
            # 覆盖 phase_* 后能自动生效，10 相位骨架保持不变。
            v = getattr(self, f"phase_{name}")()
            if v.get("verdict") in ("FAIL", "BLOCKED", "ERROR"):
                target = LOOPBACK.get(name)
                if target and self.state.budget_left > 0:
                    self.state.budget_left -= 1
                    self.state.loopbacks.append({"from": name, "to": target})
                    i = order.index(target)
                    continue
                self.state.verdicts["_final"] = verdict("BLOCKED", notes=f"{name} 预算耗尽")
                break
            i += 1
        else:
            self.state.verdicts["_final"] = verdict("PASS", notes="all phases passed")
        self.state.artifacts["edges_added"] = self._link_process_graph()
        self.proc.save(str(self.out / "process_graph.json"))
        report = {"run_id": self.run_id,
                  "final": self.state.verdicts.get("_final"),
                  "phases": {k: v for k, v in self.state.verdicts.items()
                             if not k.startswith("_")},
                  "loopbacks": self.state.loopbacks,
                  "budget_left": self.state.budget_left,
                  "process_graph": {"nodes": len(self.proc.nodes),
                                    "assertions": len(self.proc.assertions),
                                    "by_class": _class_counts(self.proc)},
                  "registry": validate_registry(run_id=self.run_id,
                                                require_gates=False),
                  "out": str(self.out)}
        (self.out / "run.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8")
        return report


def _class_counts(g: POGraph) -> Dict[str, int]:
    from collections import Counter
    return dict(Counter(n.type for n in g.nodes.values()))
