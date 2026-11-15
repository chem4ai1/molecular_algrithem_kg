"""PostgreSQL 存储：实体/关系 + 强类型榜单表（模型 × 指标 × 基准）。

设计要点（利用 PG 特性）：
* `entity.attrs jsonb` + GIN：图谱属性可扩展，不牺牲查询；
* `paper.algorithm_codes text[]`：数组存 A 码；
* `result` 唯一约束 (benchmark, model, metric, stage)：导入幂等；
* `v_leaderboard` 视图 + `mv_benchmark_columns` 物化视图：前端榜单直读；
* `numeric` 存数值、`value_raw` 保留原文，避免精度/格式丢失。
"""
from __future__ import annotations
import csv, json, os, re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

DSN = dict(host=os.environ.get("XKG_PG_HOST", "127.0.0.1"),
           port=int(os.environ.get("XKG_PG_PORT", "54321")),
           user=os.environ.get("XKG_PG_USER", "zengshuxin"),
           dbname=os.environ.get("XKG_PG_DB", "xkg"))

PROJ = Path("/home/zengshuxin/xKG-main/xKG-main")
ROOT = Path("/home/zengshuxin/xKG-main")
PAPERS_CSV = ROOT / "data/papers/papers.csv"


def connect():
    import psycopg2
    from psycopg2.extras import RealDictCursor
    return psycopg2.connect(cursor_factory=RealDictCursor, **DSN)


def _num(v: Any) -> Optional[float]:
    try:
        return float(str(v).replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _is_ours(subject: str, title: str) -> bool:
    s = (subject or "").lower()
    return bool(re.search(r"ours|our method|本文", s)) or \
        (bool(s) and s in (title or "").lower())


def _paper_meta() -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    if not PAPERS_CSV.exists():
        return out
    with open(PAPERS_CSV, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            aid = (r.get("arxiv_id") or "").strip()
            if aid:
                out[aid] = {"title": r.get("title") or "",
                            "abstract": r.get("abstract") or "",
                            "year": r.get("year") or "",
                            "venue": r.get("venue") or "",
                            "domain": r.get("domain") or ""}
    return out


def import_graph(graph: Any, *, refresh: bool = True) -> Dict[str, Any]:
    """把 POGraph 导入 PG；榜单优先取 LeaderboardEntry（自带 benchmark）。"""
    from .taxonomy import classify, domain_label, family_label
    meta = _paper_meta()
    rows_entity, rows_assert, rows_paper = [], [], []
    rows_model, rows_bench, rows_metric = [], {}, {}
    rows_result: List[Dict[str, Any]] = []
    seen_result: set = set()

    for n in graph.nodes.values():
        rows_entity.append((n.id, n.type, n.label,
                            json.dumps(n.attrs, ensure_ascii=False, default=str),
                            n.attrs.get("provenance")))
        if n.type == "Paper":
            aid = str(n.attrs.get("arxiv_id") or n.id.split(":")[-1])
            m = meta.get(aid, {})
            title = m.get("title") or n.label
            taxonomy = classify(title, m.get("abstract", ""),
                                domain_code=(n.attrs.get("domain_codes") or [""])[0],
                                paper_type=n.attrs.get("paper_type") or "")
            rows_paper.append((
                n.id, aid, title[:300], int(m["year"]) if m.get("year", "").isdigit() else None,
                m.get("venue"), (n.attrs.get("domain_codes") or [None])[0],
                list(n.attrs.get("algo_codes") or []),
                n.attrs.get("paper_type"),
                taxonomy["object_kind"], taxonomy["task_kind"],
                taxonomy["modality"]))
        elif n.type == "Algorithm":
            fam = (n.attrs.get("algo_codes") or [None])
            fam = fam[0] if isinstance(fam, list) and fam else n.attrs.get("algo_code")
            rows_model.append((n.id, n.label, fam, None, False))
        elif n.type == "Benchmark":
            rows_bench[n.id] = {"id": n.id, "name": n.label,
                                "family": (n.attrs.get("problem_ids") or [None])[0],
                                "domain_code": n.attrs.get("domain_code")}
        elif n.type == "MetricDefinition":
            rows_metric[n.id] = {"id": n.id, "name": n.label,
                                 "unit": n.attrs.get("unit"),
                                 "direction": n.attrs.get("direction") or "max"}
    for a in graph.assertions:
        rows_assert.append((a.source, a.relation, a.target,
                            json.dumps(getattr(a, "attrs", None) or {},
                                       ensure_ascii=False, default=str)))

    # 算法族归属：Paper.algo_codes 通过 PROPOSES_METHOD 回填到 Algorithm
    algo_family: Dict[str, str] = {}
    for a in graph.assertions:
        if a.relation != "PROPOSES_METHOD":
            continue
        pn = graph.nodes.get(a.source)
        if not pn:
            continue
        codes = [str(c) for c in (pn.attrs.get("algo_codes") or [])]
        if codes:
            algo_family.setdefault(a.target, codes[0])
    rows_model = [(mid, name, fam or algo_family.get(mid), pid, ours)
                  for mid, name, fam, pid, ours in rows_model]

    # 同 (benchmark, metric, value) 的「未标注模型」行合并到具名模型
    def _key(r: Dict[str, Any]) -> tuple:
        v = (f"{round(r['value'], 6)}" if r["value"] is not None
             else str(r["value_raw"]))
        return (r["benchmark_id"], r["metric_name"], v)

    named = {_key(r) for r in rows_result if r["model_name"] != "未标注模型"}
    rows_result = [r for r in rows_result
                   if r["model_name"] != "未标注模型" or _key(r) not in named]

    papers = {p[0]: p for p in rows_paper}
    for n in graph.by_type("LeaderboardEntry"):
        at = n.attrs
        bid = (at.get("benchmark_id") or "").replace(
            "benchmark:canonical:", "benchmark:")
        subj = str(at.get("subject") or "")
        metric = str(at.get("metric") or
                     (at.get("label") or "").split("=")[0] or "")
        if not bid or not metric:
            continue
        key = (bid, subj, metric, str(at.get("stage") or ""))
        if key in seen_result:
            continue
        seen_result.add(key)
        mid = at.get("metric_id") or f"metric:{metric.lower()}"
        rows_metric.setdefault(mid, {"id": mid, "name": metric,
                                     "unit": at.get("unit"),
                                     "direction": "min" if metric.lower() in
                                     ("mae", "rmse", "rmsd", "error") else "max"})
        pid = at.get("paper_id")
        rows_result.append({
            "benchmark_id": bid, "model_name": subj or "未标注模型",
            "model_id": None, "metric_id": mid, "metric_name": metric,
            "value": _num(at.get("value")), "value_raw": str(at.get("value")),
            "unit": at.get("unit"), "stage": str(at.get("stage") or ""),
            "paper_id": pid,
            "is_ours": _is_ours(subj, (papers.get(pid) or [None, None, ""])[2]),
            "provenance": "leaderboard_entry"})
    return _write(rows_entity, rows_assert, rows_paper, rows_model,
                  rows_bench, rows_metric, rows_result, refresh=refresh)


def _write(rows_entity, rows_assert, rows_paper, rows_model, rows_bench,
           rows_metric, rows_result, *, refresh: bool) -> Dict[str, Any]:
    from psycopg2.extras import execute_values
    conn = connect()
    out: Dict[str, Any] = {}
    try:
        with conn, conn.cursor() as cur:
            execute_values(cur, """
                INSERT INTO kg.entity (id, type, label, attrs, provenance)
                VALUES %s ON CONFLICT (id) DO UPDATE SET
                  label=EXCLUDED.label, attrs=EXCLUDED.attrs,
                  provenance=EXCLUDED.provenance, updated_at=now()
            """, rows_entity, page_size=500)
            out["entity"] = len(rows_entity)
            execute_values(cur, """
                INSERT INTO kg.assertion (source, relation, target, attrs)
                VALUES %s ON CONFLICT DO NOTHING
            """, rows_assert, page_size=500)
            out["assertion"] = len(rows_assert)
            execute_values(cur, """
                INSERT INTO kg.paper (id, arxiv_id, title, year, venue,
                    domain_code, algorithm_codes, paper_type, object_kind,
                    task_kind, modality)
                VALUES %s ON CONFLICT (id) DO UPDATE SET
                  title=EXCLUDED.title, year=EXCLUDED.year,
                  domain_code=EXCLUDED.domain_code,
                  algorithm_codes=EXCLUDED.algorithm_codes,
                  paper_type=EXCLUDED.paper_type,
                  object_kind=EXCLUDED.object_kind,
                  task_kind=EXCLUDED.task_kind, modality=EXCLUDED.modality
            """, rows_paper, page_size=200)
            out["paper"] = len(rows_paper)
            if rows_model:
                execute_values(cur, """
                    INSERT INTO kg.model (id, name, family_code, paper_id, is_ours)
                    VALUES %s ON CONFLICT (id) DO UPDATE SET
                      name=EXCLUDED.name, family_code=EXCLUDED.family_code
                """, rows_model, page_size=200)
            out["model"] = len(rows_model)
            if rows_bench:
                execute_values(cur, """
                    INSERT INTO kg.benchmark (id, name, family, domain_code)
                    VALUES %s ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name
                """, [(b["id"], b["name"], b["family"], b["domain_code"])
                      for b in rows_bench.values()], page_size=200)
            out["benchmark"] = len(rows_bench)
            if rows_metric:
                execute_values(cur, """
                    INSERT INTO kg.metric (id, name, unit, direction)
                    VALUES %s ON CONFLICT (id) DO UPDATE SET
                      name=EXCLUDED.name,
                      unit=COALESCE(EXCLUDED.unit, kg.metric.unit)
                """, [(m["id"], m["name"], m["unit"],
                       m["direction"] if m["direction"] in ("min", "max", "none")
                       else "max") for m in rows_metric.values()], page_size=200)
            out["metric"] = len(rows_metric)
            if rows_result:
                execute_values(cur, """
                    INSERT INTO kg.result (benchmark_id, model_id, model_name,
                        metric_id, metric_name, value, value_raw, unit, stage,
                        paper_id, is_ours, provenance)
                    VALUES %s ON CONFLICT
                      (benchmark_id, model_name, metric_name, stage)
                    DO UPDATE SET value=EXCLUDED.value,
                      value_raw=EXCLUDED.value_raw, unit=EXCLUDED.unit,
                      is_ours=EXCLUDED.is_ours
                """, [(r["benchmark_id"], r["model_id"], r["model_name"],
                       r["metric_id"], r["metric_name"], r["value"],
                       r["value_raw"], r["unit"], r["stage"], r["paper_id"],
                       r["is_ours"], r["provenance"])
                      for r in rows_result], page_size=300)
            out["result"] = len(rows_result)
            if refresh:
                cur.execute("REFRESH MATERIALIZED VIEW kg.mv_benchmark_columns")
    finally:
        conn.close()
    return out


def leaderboard(benchmark_id: str, *, limit: int = 60) -> Dict[str, Any]:
    """一个基准的「模型 × 指标」可更新矩阵 + 动态 SOTA。"""
    from .leaderboard import matrix as _matrix, direction_of
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, family FROM kg.benchmark WHERE id=%s",
                        (benchmark_id,))
            b = cur.fetchone()
            if not b:
                raise KeyError(benchmark_id)
            cur.execute("""
                SELECT model_name, metric_name, value, value_raw, unit,
                       paper_id, provenance
                FROM kg.result
                WHERE benchmark_id=%s AND value IS NOT NULL
            """, (benchmark_id,))
            rows = [{"model_name": r["model_name"],
                     "metric_name": r["metric_name"],
                     "value": r["value"], "value_raw": r["value_raw"],
                     "unit": r["unit"], "paper_id": r["paper_id"],
                     "provenance": r["provenance"]} for r in cur.fetchall()]
            cur.execute("""
                SELECT id, name, direction FROM kg.metric
            """)
            dirs = {r["name"]: r["direction"] for r in cur.fetchall()
                    if r["direction"]}
            cur.execute("""
                SELECT DISTINCT metric_name FROM kg.result
                WHERE benchmark_id=%s
            """, (benchmark_id,))
            for r in cur.fetchall():
                dirs.setdefault(r["metric_name"],
                                direction_of(r["metric_name"]))
    finally:
        conn.close()
    mat = _matrix(rows, directions=dirs, declared_metrics=dirs)
    if limit:
        mat["models"] = mat["models"][:limit]
    return {"benchmark": {"id": b["id"], "name": b["name"],
                          "family": b["family"]},
            "metrics": mat["metrics"], "models": mat["models"],
            "sota_by_metric": mat["sota_by_metric"],
            "stats": mat["stats"],
            "updatable": True,
            "note": "SOTA 按每个指标方向从全部已入库结果动态计算；"
                    "抽取新论文后自动新增行并可能切换 SOTA"}


def overview() -> Dict[str, Any]:
    """所有基准的规模概览（物化视图 + 榜单视图）。"""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT b.id, b.name, mv.metrics, mv.models, mv.n_values
                FROM kg.mv_benchmark_columns mv
                JOIN kg.benchmark b ON b.id = mv.benchmark_id
                ORDER BY mv.n_values DESC
            """)
            return {"benchmarks": [dict(r) for r in cur.fetchall()]}
    finally:
        conn.close()


FACET_LABELS = {
    "object": {"antibody": "抗体", "peptide": "多肽", "protein": "蛋白/口袋",
               "material": "材料/力场", "reaction": "反应/合成",
               "molecule": "小分子", "other": "未分类对象"},
    "task": {"instruction": "指令/LLM", "benchmark": "基准/数据集",
             "structure": "结构/对接", "optimization": "优化/校准",
             "prediction": "性质/能量预测", "generation": "生成/设计",
             "other": "未分类问题"},
    "modality": {"text": "文本/指令", "3d": "3D 结构/坐标", "graph": "2D 图",
                 "sequence": "1D 序列/SMILES", "tabular": "性质向量/表格",
                 "other": "未分类模态"},
}


def facets() -> Dict[str, List[Dict[str, Any]]]:
    """数据树 facet：领域 / 对象 / 问题 / 模态 / 算法族（中文标签）。"""
    from .taxonomy import domain_label, family_label
    conn = connect()
    try:
        out: Dict[str, List[Dict[str, Any]]] = {}
        with conn.cursor() as cur:
            for key, sql in (
                ("domain", "SELECT domain_code id, count(*) n FROM kg.paper GROUP BY 1"),
                ("object", "SELECT object_kind id, count(*) n FROM kg.paper GROUP BY 1"),
                ("task", "SELECT task_kind id, count(*) n FROM kg.paper GROUP BY 1"),
                ("modality", "SELECT modality id, count(*) n FROM kg.paper GROUP BY 1"),
            ):
                cur.execute(sql)
                out[key] = [{"id": r["id"], "count": r["n"]} for r in cur.fetchall()]
            cur.execute("""
                SELECT family_code id, count(*) n FROM kg.model
                WHERE family_code IS NOT NULL GROUP BY 1
            """)
            out["algorithm"] = [{"id": r["id"], "count": r["n"]}
                                for r in cur.fetchall()]
        for row in out["domain"]:
            row["label"] = domain_label(row["id"])
        for row in out["algorithm"]:
            row["label"] = family_label(row["id"])
        for key, m in FACET_LABELS.items():
            for row in out.get(key, []):
                row["label"] = m.get(row["id"], row["id"])
        return out
    finally:
        conn.close()


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def guess_benchmark(caption: str, benchmarks: List[Dict[str, Any]],
                    paper_benches: List[str], *, aid: str,
                    table_no: str, allow_fallback: bool = True
                    ) -> Dict[str, str]:
    """表标题 → 基准：优先匹配已知基准名，其次该论文首个基准，最后建表级基准。"""
    cap = _norm(caption)
    allowed = {x.replace("benchmark:canonical:", "benchmark:")
               for x in (paper_benches or [])}
    best = None
    for b in benchmarks:
        if "canonical:" in b["id"]:
            continue
        if allowed and b["id"] not in allowed:
            continue          # 只允许匹配本文评测过的基准，避免跨论文污染
        name = _norm(b["name"])
        if not name or len(name) < 3:
            continue
        if name in cap:
            best = (len(name), b)
    if best:
        return {"id": best[1]["id"], "name": best[1]["name"]}
    if paper_benches and allow_fallback:
        b = next((x for x in benchmarks if x["id"] == paper_benches[0]), None)
        return {"id": paper_benches[0],
                "name": b["name"] if b else paper_benches[0].split(":")[-1]}
    return {"id": f"benchmark:table:{aid}:{table_no}",
            "name": f"Table {table_no} · {aid}"}


def import_tables(aid: str, paper_id: str, md: str, *,
                  benchmarks: Optional[List[Dict[str, Any]]] = None,
                  paper_benches: Optional[List[str]] = None,
                  refresh: bool = True) -> Dict[str, Any]:
    """把一篇论文的表格矩阵写入 kg.result（幂等）。"""
    from .table_extract import parse_tables, _clean_metric, _num as _tnum
    from psycopg2.extras import execute_values
    tables = parse_tables(md)
    if not tables:
        return {"arxiv_id": aid, "tables": 0, "rows": 0}
    conn = connect()
    try:
        with conn.cursor() as cur:
            if benchmarks is None:
                cur.execute("SELECT id, name FROM kg.benchmark")
                benchmarks = [dict(r) for r in cur.fetchall()]
            if paper_benches is None:
                cur.execute("""
                    SELECT target FROM kg.assertion
                    WHERE source=%s AND relation='EVALUATED_ON'
                """, (paper_id,))
                paper_benches = [r["target"] for r in cur.fetchall()]
        from .leaderboard import rows_from_tables
        rows_pg: List[tuple] = []
        benches_made: Dict[str, str] = {}
        for ti, t in enumerate(tables):
            b = guess_benchmark(t["caption"], benchmarks, paper_benches,
                                aid=aid, table_no=t["table_no"],
                                allow_fallback=(ti == 0))
            b["id"] = b["id"].replace("benchmark:canonical:", "benchmark:")
            benches_made[b["id"]] = b["name"]
            for r in rows_from_tables(
                    [t], paper_id=paper_id, benchmark_id=b["id"]):
                metric_id = "metric:" + re.sub(r"[^a-z0-9]+", "_",
                                               r["metric_name"].lower())
                rows_pg.append((b["id"], None, r["model_name"], metric_id,
                                r["metric_name"], r["value"], r["value_raw"],
                                r["unit"], "", r["paper_id"], False,
                                r["provenance"]))
        if not rows_pg:
            return {"arxiv_id": aid, "tables": len(tables), "rows": 0}
        rows = rows_pg
        with conn, conn.cursor() as cur:
            execute_values(cur, """
                INSERT INTO kg.benchmark (id, name) VALUES %s
                ON CONFLICT (id) DO NOTHING
            """, list(benches_made.items()), page_size=100)
            execute_values(cur, """
                INSERT INTO kg.metric (id, name, direction) VALUES %s
                ON CONFLICT (id) DO NOTHING
            """, list({(r[3], r[4], "min" if r[4].lower() in
                        ("mae", "rmse", "rmsd", "frag_ratio") else "max")
                       for r in rows}), page_size=200)
            execute_values(cur, """
                INSERT INTO kg.result (benchmark_id, model_id, model_name,
                    metric_id, metric_name, value, value_raw, unit, stage,
                    paper_id, is_ours, provenance)
                VALUES %s ON CONFLICT
                  (benchmark_id, model_name, metric_name, stage)
                DO UPDATE SET value=EXCLUDED.value,
                  value_raw=EXCLUDED.value_raw,
                  provenance=EXCLUDED.provenance
            """, rows, page_size=300)
            if refresh:
                cur.execute("REFRESH MATERIALIZED VIEW kg.benchmark_columns"
                            if False else
                            "REFRESH MATERIALIZED VIEW kg.mv_benchmark_columns")
    finally:
        conn.close()
    return {"arxiv_id": aid, "tables": len(tables), "rows": len(rows),
            "benchmarks": len(benches_made),
            "benchmark_ids": sorted(benches_made)}
