"""写作任务上下文：按需实例化 CitedPaper / ResearchGap。

与 `miner.mine_all` 的分工：
  mine_all           产「全库候选」——所有论文的贡献、实验组、假设、失败模式
  WritingContext     产「本次实例」——这次写作要填的 gap、这次实际引用的论文

为什么分开：gap 与引用都是「针对当下任务」的选择，
把全库汇成一个节点会失去「这次为什么选它」的上下文。
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

GAP_TYPES = ("capability", "scale", "data", "theory", "efficiency")


def _slug(s: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "_", str(s or "").lower()).strip("_")[:50]
    if out:
        return out
    # 中文/纯符号：用短 hash 兜底，避免 id 以 ":" 结尾
    import hashlib
    return "x" + hashlib.sha256(str(s or "").encode("utf-8")).hexdigest()[:8]


class WritingContext:
    """一次写作 run 的上下文；所有节点 id 都带 run_id 前缀。"""

    def __init__(self, graph: Any, run_id: str,
                 *, persist_path: Optional[Path] = None) -> None:
        self.g = graph
        self.run_id = run_id
        self.persist_path = Path(persist_path) if persist_path else None
        self.decisions: List[Dict[str, Any]] = []   # append-only decision log

    # -- 内部 --------------------------------------------------------------
    def _next_index(self, prefix: str) -> int:
        n = 0
        for nid in self.g.nodes:
            if nid.startswith(prefix):
                n += 1
        return n + 1

    def _add(self, nid: str, typ: str, label: str, **attrs) -> str:
        if nid in self.g.nodes:
            for k, v in attrs.items():
                if v not in (None, "", []):
                    self.g.nodes[nid].attrs[k] = v
            return nid
        self.g.node(nid, typ, label[:80], layer="application", task="writing",
                    miner="writing_context", **attrs)
        return nid

    # -- 阶段01：问题锚定 --------------------------------------------------
    def freeze_problem(self, *, question: str,
               seed_ids: Optional[List[str]] = None,
               source_span: str = "") -> str:
        """冻结问题锚点（INV-G1）：qid = Q-<sha256前12>。

        同一 run 重复调用返回同一节点；问题文本变了会记 redirected_from。
        """
        import hashlib
        q = str(question or "").strip()
        h = hashlib.sha256(q.encode("utf-8")).hexdigest()[:12]
        qid = f"Q-{h}"
        nid = f"anchor:{self.run_id}:{qid}"
        old = self.g.nodes.get(nid)
        if old is not None:
            if old.attrs.get("content_hash") != h:
                old.attrs["redirected_from"] = old.attrs.get("content_hash", "")
                old.attrs["content_hash"] = h
                old.attrs["status"] = "redirected"
            return nid
        self.g.node(nid, "ProblemAnchor", q[:80], layer="application",
                    task="writing", miner="writing_context",
                    run_id=self.run_id, qid=qid, question=q,
                    content_hash=h, frozen_at=self._now(),
                    source_span=source_span, status="frozen")
        for sid in seed_ids or []:
            if sid in self.g.nodes:
                self.g.assert_rel(nid, sid, "GROUNDED_IN", layer="application")
        return nid

    def hint(self, *, anchor_id: str,
             domain_profile: Optional[List[str]] = None,
             methodology_profile: Optional[List[str]] = None,
             writing_profile: Optional[List[str]] = None,
             failure_mode_profile: Optional[List[str]] = None,
             data_profile: Optional[List[str]] = None,
             confidence: float = 0.0, origin: str = "rule") -> str:
        """登记 provisional 领域签名（阶段01 OPTIONAL hint）。

        confidence < 0.5 时下游应回落 general；hint 永不冒充 learned profile。
        """
        nid = f"hint:{self.run_id}:{_slug(anchor_id)}"
        self._add(nid, "DomainHint", f"hint:{confidence:.2f}",
                  run_id=self.run_id, domain_profile=list(domain_profile or []),
                  methodology_profile=list(methodology_profile or []),
                  writing_profile=list(writing_profile or []),
                  failure_mode_profile=list(failure_mode_profile or []),
                  data_profile=list(data_profile or []),
                  confidence=float(confidence), origin=origin,
                  provisional=True)
        if anchor_id in self.g.nodes:
            self.g.assert_rel(nid, anchor_id, "HINTS", layer="application")
        return nid

    # -- 空白 --------------------------------------------------------------
    def seek_gap(self, *, statement: str, gap_type: str,
                 source_papers: Optional[List[str]] = None,
                 evidence: str = "", priority: str = "medium") -> str:
        """登记「这次要填的空白」；同类陈述复用同一节点。"""
        gt = gap_type if gap_type in GAP_TYPES else "capability"
        key = _slug(f"{gt}:{statement}")
        nid = f"gap:{self.run_id}:{key}"
        self._add(nid, "ResearchGap", statement, run_id=self.run_id,
                  gap_id=nid, gap_type=gt, statement=statement,
                  evidence=evidence, priority=priority,
                  source_papers=list(source_papers or []),
                  selected_at=self._now())
        for pid in source_papers or []:
            if pid in self.g.nodes:
                self.g.assert_rel(nid, pid, "SEEKS_FROM", layer="application")
        return nid

    # -- 引用 --------------------------------------------------------------
    def cite(self, *, cite_key: str, title: str, doi: str = "",
             year: str = "", venue: str = "", authors: str = "",
             section_id: str = "", context_quote: str = "") -> str:
        """登记「这次实际引用的一篇」；同 cite_key 复用同一节点。"""
        nid = f"cited:{self.run_id}:{_slug(cite_key)}"
        cited_in = []
        if section_id:
            cited_in = [section_id]
        self._add(nid, "CitedPaper", title or cite_key, run_id=self.run_id,
                  cite_key=cite_key, title=title or cite_key, doi=doi,
                  authors=authors, year=year, venue=venue,
                  context_quote=context_quote, cited_in=cited_in,
                  existence="unknown", metadata_ok="unknown",
                  context_ok="unknown", layers=[])
        if section_id and section_id in self.g.nodes:
            self.g.assert_rel(section_id, nid, "CITES", layer="application")
        return nid

    # -- 章节实例 ----------------------------------------------------------
    def plan_section(self, *, section: str, section_plan: str = "",
                     claims: Optional[List[str]] = None,
                     word_budget: Optional[int] = None) -> str:
        """登记「本次这一节怎么写」；同 section 复用。"""
        nid = f"draft:{self.run_id}:{_slug(section)}"
        self._add(nid, "SectionDraft", section, run_id=self.run_id,
                  section=section, section_plan=section_plan or "",
                  claims=list(claims or []), word_budget=word_budget,
                  status="planned", cited=[], evidence=[])
        if section_plan and section_plan in self.g.nodes:
            self.g.assert_rel(nid, section_plan, "INSTANCE_OF", layer="application")
        return nid

    def use_evidence(self, draft_id: str, evidence_id: str) -> None:
        if draft_id in self.g.nodes and evidence_id in self.g.nodes:
            self.g.assert_rel(draft_id, evidence_id, "USES_EVIDENCE",
                              layer="application")

    # -- 检索候选（task-r） ------------------------------------------------
    def retrieved(self, *, paper_id: str, query: str,
                  score: float | None = None, bm25: float | None = None,
                  vector: float | None = None, domain_hint: str = "",
                  rank: int = 0, draft_id: str = "") -> str:
        """登记一次检索召回的候选；同 run 同 paper 复用，更新更高分。

        domain_hint 只记领域标签作为**检索线索**，不用于推导证据规范。
        """
        nid = f"related:{self.run_id}:{_slug(paper_id)}"
        row = {"run_id": self.run_id, "paper_id": paper_id, "query": query,
               "score": score, "bm25": bm25, "vector": vector,
               "domain_hint": domain_hint, "rank": rank,
               "decision": "pending", "retrieved_at": self._now()}
        if nid in self.g.nodes:
            old = self.g.nodes[nid].attrs
            if (score or 0) >= (old.get("score") or 0):
                for k, v in row.items():
                    if v not in (None, ""):
                        old[k] = v
        else:
            self.g.node(nid, "RelatedPaper", paper_id[:80],
                        layer="application", task="writing",
                        miner="writing_context", **row)
        if paper_id in self.g.nodes:
            self.g.assert_rel(nid, paper_id, "ABOUT", layer="application")
        if draft_id and draft_id in self.g.nodes:
            self.g.assert_rel(draft_id, nid, "RETRIEVED", layer="application")
        return nid

    def retrieve(self, query: str, *, k: int = 8,
                 types: List[str] | None = None,
                 domain_hint: str = "", draft_id: str = "",
                 searcher: Any = None) -> List[str]:
        """调向量检索并把命中登记为 RelatedPaper。

        searcher 可注入（便于测试）；默认用 semantic.vector_sync.search。
        领域标签只作为 domain_hint 传入，不参与相似度计算或证据规范推导。
        """
        if searcher is None:
            from ..semantic.vector_sync import search as searcher  # type: ignore
        hits = searcher(query, types=types or ["Paper"], k=k)
        ids = []
        for i, h in enumerate(hits, 1):
            pid = str(h.get("id") or h.get("node_id") or "")
            if not pid:
                continue
            ids.append(self.retrieved(
                paper_id=pid, query=query, score=h.get("score"),
                bm25=h.get("bm25"), vector=h.get("vector"),
                domain_hint=domain_hint or str(self.g.nodes[pid].attrs.get("domain") or "")
                if pid in self.g.nodes else domain_hint,
                rank=i, draft_id=draft_id))
        return ids

    def decide(self, related_id: str, decision: str,
               *, cited_id: str = "") -> None:
        """候选处理：cited / consulted / rejected。"""
        if related_id not in self.g.nodes:
            return
        self.g.nodes[related_id].attrs["decision"] = decision
        if decision == "cited" and cited_id and cited_id in self.g.nodes:
            self.g.assert_rel(related_id, cited_id, "LED_TO",
                              layer="application")

    # -- 预演与自检 --------------------------------------------------------
    def review(self, *, contribution_id: str, axis: str, attack: str,
               severity: str = "high", response: str = "",
               evidence_gap: str = "") -> str:
        """登记「本次针对这条贡献预演的一条反驳」。"""
        nid = f"review:{self.run_id}:{_slug(f'{contribution_id}:{axis}')}"
        self._add(nid, "ReviewPoint", f"{axis} · {attack[:24]}",
                  run_id=self.run_id, axis=axis, attack=attack,
                  response=response, severity=severity,
                  evidence_gap=evidence_gap)
        if contribution_id in self.g.nodes:
            self.g.assert_rel(contribution_id, nid, "CHALLENGED_BY",
                              layer="application")
        return nid

    def check(self, *, failure_mode_id: str, status: str,
              note: str = "") -> str:
        """登记「本次对某条失败模式的自检结果」。"""
        nid = f"check:{self.run_id}:{_slug(failure_mode_id)}"
        self._add(nid, "FailureCheck", failure_mode_id, run_id=self.run_id,
                  status=status, note=note, checked_at=self._now())
        if failure_mode_id in self.g.nodes:
            self.g.assert_rel(nid, failure_mode_id, "CHECK_OF",
                              layer="application")
        return nid

    # -- 查阅（未引） ------------------------------------------------------
    def consult(self, *, paper_id: str, reason: str = "",
                draft_id: str = "") -> str:
        """登记「查过但没引」的论文；用于回答「为什么没引它」。"""
        nid = f"consult:{self.run_id}:{_slug(paper_id)}"
        self._add(nid, "ConsultedPaper", paper_id, run_id=self.run_id,
                  paper_id=paper_id, reason=reason,
                  used_in=[draft_id] if draft_id else [])
        if draft_id and draft_id in self.g.nodes:
            self.g.assert_rel(draft_id, nid, "CONSULTED", layer="application")
        return nid

    # ===== C 类决策接口（类型化 + 自动绑定 B 类 provenance）=====
    def _log(self, kind: str, nid: str, *, intent: str, source: str = "",
             via: str = "", verdict: str = "CREATED", **extra) -> None:
        """append-only decision log：每个决策绑定 intent + provenance。"""
        self.decisions.append({"kind": kind, "node": nid, "run_id": self.run_id,
            "intent": intent, "source": source, "via": via,
            "verdict": verdict, "at": self._now(), **extra})

    def formulate_gap(self, *, statement: str, anchor_id: str = "",
                      task_type: str = "", cite_key: str = "",
                      source_span: str = "", delta: str = "",
                      why_not_before: str = "") -> str:
        """② GapTriple：frontier_baseline 自动从 MethodLineage 查，不手写。"""
        from .graph_query import query_frontier_baseline
        fr = query_frontier_baseline(self.g, task_type)
        nid = f"gaptriple:{self.run_id}:{_slug(statement)}"
        self._add(nid, "GapTriple", statement[:80], run_id=self.run_id,
                  frontier_baseline=fr["baseline"], delta=delta or statement[:80],
                  why_not_before=why_not_before, cite_key=cite_key,
                  source_span=source_span, frontier_source=fr["source"],
                  frontier_via=fr["via"])
        if anchor_id and anchor_id in self.g.nodes:
            self.g.assert_rel(nid, anchor_id, "GAP_FOR", layer="application")
        if fr.get("source") and fr["source"] in self.g.nodes:
            self.g.assert_rel(nid, fr["source"], "DERIVED_FROM_GRAPH", layer="application")
        self._log("GapTriple", nid, intent="把空白形式化为三元组",
                  source=fr["source"], via=fr["via"], found=fr["found"])
        return nid

    def propose_idea(self, *, gap_id: str, mechanism: str,
                     novelty_delta: str, expected_direction: str,
                     falsification_condition: str) -> str:
        """③ IdeaCandidate：必带机制与证伪条件。"""
        nid = f"idea:{self.run_id}:{_slug(mechanism)}"
        self._add(nid, "IdeaCandidate", mechanism[:80], run_id=self.run_id,
                  mechanism=mechanism, novelty_delta=novelty_delta,
                  expected_direction=expected_direction,
                  falsification_condition=falsification_condition, selected=False)
        if gap_id in self.g.nodes:
            self.g.assert_rel(gap_id, nid, "IDEA_FOR", layer="application")
        self._log("IdeaCandidate", nid, intent="提出可证伪想法",
                  source=gap_id, via="IDEA_FOR",
                  verdict="LOCKED" if mechanism and falsification_condition else "REJECTED")
        return nid

    def formalize_claim(self, *, idea_id: str, anchor_id: str,
                        statement: str, polarity: str = "positive",
                        evidence_type: str = "",
                        refutation_condition: str = "") -> str:
        """④ Claim：expected_fidelity 自动从 EvaluationNorm 查；无推翻条件则拒绝。"""
        from .graph_query import query_evaluation_norm
        if not refutation_condition:
            self._log("Claim", "REJECTED", intent="主张形式化",
                      verdict="BLOCKED:no_refutation_condition")
            return ""
        norm = query_evaluation_norm(self.g, evidence_type)
        nid = f"claim:{self.run_id}:{_slug(statement)}"
        self._add(nid, "Claim", statement[:80], run_id=self.run_id,
                  statement=statement, polarity=polarity,
                  expected_fidelity=norm["min_fidelity"],
                  refutation_condition=refutation_condition,
                  locked_at=self._now(), grade="pending",
                  norm_source=norm["source"], norm_found=norm["found"])
        for src, rel in ((idea_id, "FULFILLS"), (anchor_id, "CLAIM_OF"),
                         (norm.get("source"), "GROUNDED_IN_NORM")):
            if src and src in self.g.nodes:
                self.g.assert_rel(nid, src, rel, layer="application")
        self._log("Claim", nid, intent="冻结可证伪主张",
                  source=norm["source"], via="GROUNDED_IN", verdict="LOCKED")
        return nid

    def grade_claim(self, *, claim_id: str, has_numeric_evidence: bool,
                    n_checks: int = 0) -> str:
        """⑦ 定档：从 FailureModeLibrary 查失败模式，规则计算 grade。"""
        from .graph_query import query_failure_checks
        from .edge_verdict import verify_edge, EdgeVerdict
        fails = query_failure_checks(self.g)
        claim = self.g.nodes.get(claim_id)
        target = claim.attrs.get("norm_source") if claim else None
        total = len(self.g.by_type("Paper"))
        # TruthHypo 范式：三值门 + 置信度
        v = verify_edge(self.g, claim_source=claim_id,
                        relation="GROUNDED_IN_NORM", target_id=target or "",
                        total_papers=total,
                        contradiction_terms=["不支持", "无法", "失败"] if not has_numeric_evidence else [])
        if not has_numeric_evidence and v.verdict == "SUPPORTED":
            v = EdgeVerdict("INSUFFICIENT", v.confidence, supporting=v.supporting,
                            reason="no numeric evidence")
        grade = {"SUPPORTED": "supported", "REFUTED": "refuted",
                 "INSUFFICIENT": "suggests"}[v.verdict]
        if claim:
            claim.attrs["grade"] = grade
            claim.attrs["verdict"] = v.to_dict()
            claim.attrs["audit_source"] = fails["source"]
            if fails["source"] and fails["source"] in self.g.nodes:
                self.g.assert_rel(claim_id, fails["source"], "AUDITED_BY", layer="application")
        self._log("ClaimGrading", claim_id, intent="三值门定档",
                  source=fails["source"], via="AUDITED_BY", verdict=v.verdict,
                  confidence=v.confidence, n_checks=len(fails["checks"]))
        return grade

    def design_narrative(self, *, claim_id: str, section: str,
                         fig_label: str, word_budget: int = 800) -> str:
        """⑧ SectionPlan + FigurePlan：venue 惯例从 VenueProfile 查。"""
        from .graph_query import query_venue_profile
        vp = query_venue_profile(self.g)
        sid = f"section:{self.run_id}:{_slug(section)}"
        self._add(sid, "SectionPlan", section, run_id=self.run_id, section=section,
                  claims=[claim_id], word_budget=word_budget,
                  venue_found=vp["found"], venue_source=vp["source"],
                  venue_pattern=vp.get("section_pattern") or [])
        fid = f"fig:{self.run_id}:{_slug(fig_label)}"
        self._add(fid, "FigurePlan", fig_label, run_id=self.run_id,
                  fig_label=fig_label, claim_ref=claim_id, inferential_role="main_effect")
        if claim_id in self.g.nodes:
            self.g.assert_rel(sid, claim_id, "USES_EVIDENCE", layer="application")
        self._log("Narrative", sid, intent="先定结构后起草",
                  source=vp["source"], via="VENUE_OF",
                  verdict="PASS" if vp["found"] else "WARN:no_venue", figure=fid)
        return sid

    def deliver(self, *, claim_id: str, code_snapshot: str,
                data_snapshot: str, env_spec: str,
                one_click_script: str, verification: str = "pending") -> str:
        """⑩ ReproductionPackage：verification 非 pass 时不得投。"""
        nid = f"pkg:{self.run_id}"
        self._add(nid, "ReproductionPackage", f"复现包:{self.run_id}",
                  run_id=self.run_id, code_snapshot=code_snapshot,
                  data_snapshot=data_snapshot, env_spec=env_spec,
                  one_click_script=one_click_script, verification=verification)
        if claim_id in self.g.nodes:
            self.g.assert_rel(claim_id, nid, "DELIVERED_BY", layer="application")
        verdict = "PASS" if verification == "pass" else "BLOCKED:verification"
        self._log("Delivery", nid, intent="独立复现交付", source=claim_id,
                  via="DELIVERED_BY", verdict=verdict)
        return nid

    # -- 关联 --------------------------------------------------------------
    def support(self, gap_id: str, cite_key: str) -> None:
        nid = f"cited:{self.run_id}:{_slug(cite_key)}"
        if gap_id in self.g.nodes and nid in self.g.nodes:
            self.g.assert_rel(gap_id, nid, "GAP_SUPPORTED_BY", layer="application")

    def anchor(self, gap_id: str, contribution_id: str) -> None:
        if gap_id in self.g.nodes and contribution_id in self.g.nodes:
            self.g.assert_rel(gap_id, contribution_id, "ANCHORS",
                              layer="application")

    # -- 查询与落盘 --------------------------------------------------------
    def gaps(self) -> List[Dict[str, Any]]:
        return [n.to_dict() for n in self.g.nodes.values()
                if n.type == "ResearchGap"
                and n.attrs.get("run_id") == self.run_id]

    def cited(self) -> List[Dict[str, Any]]:
        return [n.to_dict() for n in self.g.nodes.values()
                if n.type == "CitedPaper"
                and n.attrs.get("run_id") == self.run_id]

    def save(self) -> str:
        if not self.persist_path:
            return ""
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        self.g.save(str(self.persist_path))
        return str(self.persist_path)

    @staticmethod
    def _now() -> str:
        from datetime import datetime
        return datetime.now().isoformat(timespec="seconds")
