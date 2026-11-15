"""A4 Materialize：确定性写图 / CSV / 榜单（失败不吞，边前做 TBox 校验）。"""
from __future__ import annotations
import csv, json, re
from pathlib import Path
from typing import Any, Dict, List


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s or "").lower()).strip("_")


def _tbox_allows(src_type: str, rel: str, dst_type: str) -> bool:
    """统一走 ontology.tbox 的权威判定（不再自行实现口径）。"""
    from ...ontology.tbox import check_domain_range
    return check_domain_range(src_type, rel, dst_type)


def materialize(inp: Any, norm: Any, plan: Any, *, graph: Any
                ) -> Dict[str, Any]:
    rep: Dict[str, Any] = {"nodes_added": {}, "edges_added": {},
                           "violations": [], "warnings": [], "csv_rows": {},
                           "pg_rows": 0, "sota_changes": []}
    trace = {"source_locator": f"stage3:{inp.arxiv_id}",
             "assembly_provenance": "stage3_assembly", "run_id": inp.run_id,
             "inputs_sha": inp.inputs_sha}

    def add_node(nid: str, typ: str, label: str, **attrs):
        if nid in graph.nodes:
            return False
        graph.node(nid, typ, label, **{**trace, **attrs})
        rep["nodes_added"][typ] = rep["nodes_added"].get(typ, 0) + 1
        return True

    def add_edge(src: str, rel: str, dst: str, **props):
        if src not in graph.nodes or dst not in graph.nodes:
            rep["violations"].append({"kind": "dangling_edge",
                                      "src": src, "rel": rel, "dst": dst})
            return False
        st, dt = graph.nodes[src].type, graph.nodes[dst].type
        if not _tbox_allows(st, rel, dt):
            rep["violations"].append({"kind": "domain_range",
                                      "src": src, "rel": rel, "dst": dst,
                                      "src_type": st, "dst_type": dt})
            return False
        graph.assert_rel(src, dst, rel, **props)
        rep["edges_added"][rel] = rep["edges_added"].get(rel, 0) + 1
        return True

    # ① 补根边（蓝图 §3.3.1 自举）
    for e in plan.root_edges:
        add_node(e["dst"], e.get("type") or "Benchmark",
                 e.get("label") or e["dst"])
        add_edge(e["src"], e["rel"], e["dst"], **trace)
    # ② 数据契约与观测
    for i, b in enumerate(norm.benchmarks):
        bid = f"benchmark:{_slug(b.get('name') or '')}"
        if not b.get("name") or bid not in graph.nodes:
            continue
        did = f"datacontract:{inp.arxiv_id}:{i}"
        add_node(did, "DataContract", f"DataContract {i}",
                 input_form=b.get("input_form"), output_form=b.get("output_form"),
                 metrics=b.get("metrics") or [])
        add_edge(bid, "HAS_DATA_CONTRACT", did, **trace)
    for i, o in enumerate(norm.observations):
        oid = f"observation:{inp.arxiv_id}:{i}"
        add_node(oid, "Observation",
                 f"{o.get('metric','')}={o.get('value','')}",
                 metric=o.get("metric"), value=o.get("value"),
                 unit=o.get("unit"))
    # ③ 科技树 8 关系（SourcePaper 占位，保留 rel 与 evidence）
    for i, e in enumerate(norm.tree_edges):
        rel = e["rel"]
        # 蓝图 §5.1：不同关系的目标节点类型不同
        dst_type = {"HAS_LIMITATION": "Limitation",
                    "ON_METRIC": "MetricDefinition",
                    "DELTA": "Observation"}.get(rel, "SourcePaper")
        dst_prefix = {"HAS_LIMITATION": "limitation",
                      "ON_METRIC": "metric",
                      "DELTA": "observation"}.get(rel, "sourcepaper:tree")
        a = f"sourcepaper:tree:{_slug(e.get('src',''))}"
        b = f"{dst_prefix}:{inp.arxiv_id}:{_slug(e.get('dst',''))}"
        add_node(a, "SourcePaper", str(e.get("src") or f"src{i}"))
        add_node(b, dst_type, str(e.get("dst") or f"dst{i}"),
                 delta=e.get("delta", ""))
        add_edge(a, e["rel"], b, tree_style=e.get("style", ""),
                 evidence=e.get("evidence", ""))
    # ④ AST 命中符号写回（蓝图 P2-9）
    for s in plan.ast_hits:
        cid = f"codefunction:ast:{_slug(s)}"
        add_node(cid, "CodeFunction", s)
    # ⑤ 三份 CSV（run-scoped，修 E1）
    d = Path(inp.out_dir) / "sources"
    d.mkdir(parents=True, exist_ok=True)
    for kind, rows in (("algorithm", [{"name": x} for x in norm.methods]),
                       ("benchmark", [{"name": x.get("name"),
                                       "input_form": x.get("input_form")}
                                      for x in norm.benchmarks]),
                       ("related_paper", [{"name": x["name"],
                                           "status": x.get("status", "")}
                                          for x in plan.source_refs])):
        p = d / f"{kind}.csv"
        fields = sorted({k for r in rows for k in r}) or ["name"]
        with p.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        rep["csv_rows"][kind] = len(rows)
    from .hydrate import hydrate_derived_nodes
    rep["hydrated"] = hydrate_derived_nodes(graph)
    (d / "SOURCE_INDEX.json").write_text(json.dumps(
        {"run_id": inp.run_id, "inputs_sha": inp.inputs_sha,
         "csv_rows": rep["csv_rows"]}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return rep
