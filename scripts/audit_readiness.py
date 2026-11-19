#!/usr/bin/env python3
"""抽取就绪度审计 CLI：判断能否推理到各阶段。"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from capfactory.po import POGraph
from capfactory.applayer.readiness import audit_graph

GRAPH = ROOT / "storage/sciforge/factory_knowledge_rules.json"
OUT = ROOT / "storage/sciforge/readiness_report.json"

g = POGraph.load(str(GRAPH))
rep = audit_graph(g)
OUT.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"论文 {rep['n_papers']} 篇")
print("\n各阶段就绪度：")
for ph, s in rep["stats"].items():
    n = rep["n_papers"]
    print(f"  {ph}: READY {s['READY']:>2}/{n}  PARTIAL {s['PARTIAL']:>2}  BLOCKED {s['BLOCKED']:>2}")
print("\n缺什么（按需求项统计）：")
for k, v in sorted(rep["missing_by_requirement"].items(), key=lambda x: -x[1]):
    print(f"  {k:<40} {v} 篇")
print("\n待补抽：")
for refine, ids in rep["pending_refine"].items():
    print(f"  {refine}: {len(ids)} 篇")
