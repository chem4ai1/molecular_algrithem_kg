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
    return re.sub(r"[^a-z0-9]+", "_", str(s or "").lower()).strip("_")[:50]


class WritingContext:
    """一次写作 run 的上下文；所有节点 id 都带 run_id 前缀。"""

    def __init__(self, graph: Any, run_id: str,
                 *, persist_path: Optional[Path] = None) -> None:
        self.g = graph
        self.run_id = run_id
        self.persist_path = Path(persist_path) if persist_path else None

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
