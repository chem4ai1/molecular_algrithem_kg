"""P2/P3/P4：基准库扩充、同族属性统一、指标与模型结果挂载、模板抽取器。

诚实原则：新增基准属性来自领域认知（provenance=domain_knowledge），
**不编造测试结果**；metrics/model_results 一律从 PG `kg.result` 取。
"""
from __future__ import annotations
import json, re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .benchmark_schema import (FAMILIES, FAMILY_IDS, classify_rule,
                               schema_for, enum_values)

OUT = Path("storage_cf/sciforge/benchmark_fill_report.json")

KNOWN: Dict[str, Dict[str, Dict[str, Any]]] = {
    "molecule_generation": {
        "ZINC-250k": {"n_molecules": "250000", "generation_budget": "10000",
                      "validity_checker": "RDKit",
                      "metric_family": ["validity", "uniqueness", "novelty"],
                      "input_form": "SMILES", "output_form": "分子"},
        "MOSES": {"n_molecules": "1900000", "generation_budget": "30000",
                  "validity_checker": "RDKit",
                  "metric_family": ["FCD", "SNN", "scaffold similarity"],
                  "input_form": "SMILES", "output_form": "分子"},
        "GuacaMol": {"n_molecules": "1600000",
                     "metric_family": ["validity", "KL divergence", "FCD"],
                     "input_form": "SMILES", "output_form": "分子"},
        "ChEMBL": {"n_molecules": "2000000",
                   "metric_family": ["validity", "uniqueness"],
                   "input_form": "SMILES", "output_form": "分子"},
        "GEOM-Drugs": {"n_molecules": "430000", "n_conformers": "多构象",
                       "metric_family": ["coverage", "matching"],
                       "input_form": "3D 坐标", "output_form": "构象"},
        "ZINC-15": {"n_molecules": ">100M", "validity_checker": "RDKit",
                    "input_form": "SMILES", "output_form": "分子"},
        "GDB-17": {"n_molecules": "166000000000", "input_form": "SMILES",
                   "output_form": "分子"},
        "PubChem": {"n_molecules": ">100M", "input_form": "SMILES",
                    "output_form": "分子"},
    },
    "property_prediction": {
        "QM9": {"n_samples": "134000",
                "target_properties": ["HOMO", "LUMO", "gap", "μ", "α"],
                "task_type": "回归", "label_source": "DFT",
                "metric_family": ["MAE"], "input_form": "3D 坐标"},
        "ESOL": {"n_samples": "1128", "target_properties": ["水溶性"],
                 "task_type": "回归", "metric_family": ["RMSE"]},
        "FreeSolv": {"n_samples": "642", "target_properties": ["水合自由能"],
                     "task_type": "回归", "metric_family": ["RMSE", "MAE"]},
        "Lipophilicity": {"n_samples": "4200", "target_properties": ["logD"],
                          "task_type": "回归", "metric_family": ["RMSE"]},
        "BBBP": {"n_samples": "2050", "target_properties": ["血脑屏障穿透"],
                 "task_type": "分类", "metric_family": ["AUC"]},
        "HIV": {"n_samples": "41127", "target_properties": ["HIV 复制抑制"],
                "task_type": "分类", "metric_family": ["AUC"]},
        "Tox21": {"n_samples": "7831", "n_tasks": "12",
                  "target_properties": ["核受体", "应激通路"],
                  "task_type": "多任务分类", "metric_family": ["AUC"]},
        "ClinTox": {"n_samples": "1478", "target_properties": ["临床毒性"],
                    "task_type": "分类", "metric_family": ["AUC"]},
        "SIDER": {"n_samples": "1427", "n_tasks": "27",
                  "target_properties": ["副作用"], "task_type": "多任务分类"},
        "TDC-ADMET": {"n_tasks": "22", "target_properties": ["ADMET 性质族"],
                      "metric_family": ["MAE", "AUC", "Spearman"]},
        "AqSolDB": {"n_samples": "9982", "target_properties": ["溶解度"],
                    "task_type": "回归", "metric_family": ["RMSE"]},
    },
    "quantum_energy": {
        "S22x5": {"n_systems": "22", "n_conformers": "5 个间距/体系",
                  "reference_method": "CCSD(T)", "energy_unit": "kcal/mol",
                  "metric_family": ["MAE"]},
        "S66x8": {"n_systems": "66", "n_conformers": "8 个间距/体系",
                  "reference_method": "CCSD(T)", "metric_family": ["MAE"]},
        "ANI-1x": {"n_systems": "有机小分子构象", "reference_method": "DFT",
                   "energy_unit": "kcal/mol", "force_labels": "有"},
        "QM7-X": {"n_systems": "6950", "n_conformers": "42000",
                  "reference_method": "DFT", "metric_family": ["MAE"]},
        "MD17": {"n_systems": "8 个分子", "n_conformers": "分子动力学轨迹",
                 "reference_method": "DFT", "force_labels": "有",
                 "metric_family": ["MAE"]},
        "ISO17": {"n_systems": "C7O2H10 异构体", "reference_method": "DFT",
                  "metric_family": ["MAE"]},
    },
    "structure_docking": {
        "PDBbind": {"n_complexes": "19443", "n_targets": "多靶点",
                    "rmsd_threshold": "2.0 Å",
                    "metric_family": ["RMSE", "Pearson r"]},
        "CASF-2016": {"n_complexes": "285", "n_targets": "57",
                      "metric_family": ["Pearson r", "RMSE"]},
        "CrossDocked2020": {"n_complexes": "22500000",
                            "pocket_definition": "跨口袋对齐",
                            "metric_family": ["QED", "diversity", "rmsd"]},
        "DUD-E": {"n_targets": "102", "decoy_ratio": "50:1",
                  "rmsd_threshold": "2.0 Å",
                  "metric_family": ["QED", "diversity"]},
        "TorsionNet500": {"n_targets": "500",
                          "metric_family": ["torsion profile MAE"]},
        "BindingDB": {"n_complexes": ">2M",
                      "target_properties": ["结合亲和力"]},
        "antibody CDRH3 test set": {"n_targets": "抗体 CDRH3",
                                   "metric_family": ["amino acid recovery"]},
    },
    "peptide_sequence": {
        "DBAASP": {"n_sequences": ">19000", "activity_label": "MIC 实测",
                   "mic_measurement": "μg/ml", "metric_family": ["MIC"]},
        "CAMP": {"n_sequences": "抗菌肽序列库", "activity_label": "AMP 活性"},
        "UniProt": {"n_sequences": ">200M", "activity_label": "无标签"},
        "APD3": {"n_sequences": ">3000", "activity_label": "AMP 活性"},
        "Real AMPs sequence database": {"n_sequences": "实验验证 AMP",
                                        "activity_label": "MIC 实测",
                                        "metric_family": ["validity", "uniqueness", "novelty"]},
        "AMP Scanner ensemble": {"predictor_ensemble": ["CAMP", "AMP Scanner", "Macrel"],
                                 "activity_label": "AMP 活性"},
    },
    "instruction_dataset": {
        "ChEBI-20": {"n_instructions": "33000",
                     "modalities": ["SMILES", "文本"],
                     "metric_family": ["BLEU", "ROUGE", "Exact Match"]},
        "SMolInstruct": {"n_instructions": "2M+", "n_tasks": "多任务",
                         "modalities": ["SMILES", "文本", "3D"]},
        "PubChemQC": {"n_instructions": "量子化学性质问答",
                      "source_db": "PubChem", "modalities": ["文本", "分子"]},
        "Mol-Instructions": {"n_tasks": "20+",
                             "modalities": ["文本", "SMILES", "蛋白质序列"],
                             "source_db": "PubChem/UniProt"},
    },
    "reaction_synthesis": {
        "USPTO-50k": {"n_reactions": "50000", "reaction_type": "逆合成",
                      "split_type": "random split",
                      "metric_family": ["top-k accuracy"]},
        "USPTO-MIT": {"n_reactions": "479000",
                      "reaction_type": "正向反应预测",
                      "metric_family": ["top-k accuracy"]},
        "Pistachio": {"n_reactions": ">10M",
                      "reaction_type": "正向反应预测"},
        "ORD": {"n_reactions": "开放反应数据库", "reaction_type": "产率预测"},
    },
}


# 族级核心属性默认（用户要求只保留 6 类属性，避免一堆 unknown）
FAMILY_CORE = {
    "molecule_generation": ("SMILES", "分子", "1D 序列/SMILES",
                            "小分子", "大规模 (>100k)"),
    "property_prediction": ("分子结构/描述符", "性质标签",
                            "性质向量/表格", "小分子", "中规模 (1k–100k)"),
    "quantum_energy": ("原子坐标", "能量/力", "3D 结构/坐标",
                       "材料/力场", "小规模 (<1k)"),
    "structure_docking": ("蛋白口袋+配体", "3D 构象/对接分数",
                          "3D 结构/坐标", "蛋白/口袋", "中规模 (1k–100k)"),
    "peptide_sequence": ("氨基酸序列", "活性/MIC 标签",
                         "1D 序列/SMILES", "多肽", "中规模 (1k–100k)"),
    "instruction_dataset": ("文本指令+分子", "文本/分子",
                            "文本/指令", "小分子", "大规模 (>100k)"),
    "reaction_synthesis": ("反应物 SMILES", "产物 SMILES",
                           "1D 序列/SMILES", "反应/合成", "大规模 (>100k)"),
}
SAMPLE_HINTS = {
    "ZINC": "约 5,000 生成分子（Table 1）",
    "DUD-E": "101 靶点", "SAPT10k": "10k 二聚体构象",
    "QUID": "量子化学相互作用能数据集",
    "JSCH-2005": "JSCH-2005 基准集", "PLA15": "PLA15 构象集",
    "TorsionNet500": "500  torsion 体系",
    "Real AMPs sequence database": "实验验证 AMP 序列集",
    "Crambin in water": "水溶液体系模拟",
    "Side-chain pKa of pentapeptides": "五肽侧链 pKa 数据",
    "ZINC-15": ">100M 可购化合物",
}


def _pg_rows() -> Dict[str, List[Dict[str, Any]]]:
    """从 PG 取每个基准的指标与模型结果。"""
    try:
        from .pgstore import connect
        conn = connect()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT benchmark_id, model_name, metric_name,
                           value, value_raw, unit, paper_id, provenance
                    FROM kg.result WHERE value IS NOT NULL
                """)
                rows = [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    except Exception:  # noqa: BLE001
        return {}
    out: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r["benchmark_id"], []).append(r)
    return out


def _lists_for(bid: str, pg: Dict[str, List[Dict[str, Any]]]
               ) -> Dict[str, Any]:
    """从 PG 取全部结果 → 指标列表 + 可更新矩阵 + 动态 SOTA。"""
    from .leaderboard import matrix as _matrix, direction_of
    rows = [{"model_name": r["model_name"],
             "metric_name": r["metric_name"], "value": r["value"],
             "value_raw": r["value_raw"], "unit": r["unit"],
             "paper_id": r["paper_id"], "provenance": r["provenance"]}
            for r in (pg.get(bid) or [])]
    is_evaluation = "benchmark:table:" not in str(bid)
    mat = _matrix(rows)
    if not is_evaluation:
        # 属性区间表不是评测基准，不计算 SOTA（修 E15）
        mat["sota_by_metric"] = {}
        for m in mat["metrics"]:
            m["sota_model"] = ""
            m["sota_value"] = ""
        for m in mat["models"]:
            for c in m["cells"].values():
                c["is_sota"] = False
    papers = sorted({r["paper_id"] for r in rows if r.get("paper_id")})
    return {"metrics": mat["metrics"],
            "model_results": [
                {"model": m["name"], "metric": k, "value": c["value"],
                 "unit": c["unit"], "is_sota": c["is_sota"],
                 "paper_id": c["paper_id"]}
                for m in mat["models"]
                for k, c in m["cells"].items()],
            "sota_by_metric": mat["sota_by_metric"],
            "is_evaluation": is_evaluation,
            "source_papers": papers,
            "matrix": {"metrics": mat["metrics"],
                       "models": mat["models"], "stats": mat["stats"]}}


def _uniform(family: str, values: Dict[str, Any]) -> Dict[str, Any]:
    """只保留用户指定的 6 类核心属性 + 可更新表格，删掉冗余 unknown 字段。"""
    from .leaderboard import CORE_FIELDS
    out: Dict[str, Any] = {"schema_family": family,
                           "schema_version": "v2_lean"}
    for k in CORE_FIELDS:
        v = values.get(k)
        if v in (None, ""):
            v = [] if k in ("metrics", "model_results", "source_papers") \
                else ({} if k == "sota_by_metric" else
                      (True if k == "is_evaluation" else "unknown"))
        out[k] = v
    return out


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def expand_and_fill(graph: Any, *, persist: bool = True,
                    save_graph: bool = True,
                    graph_path: str = "storage_cf/sciforge/batch10_final_graph.json",
                    report_path: Optional[str] = None) -> Dict[str, Any]:
    """大幅扩充 + 同族属性统一 + 每个基准挂指标列表与模型结果列表。"""
    pg = _pg_rows()
    rep: Dict[str, Any] = {"n_existing": 0, "n_added": 0,
                           "by_family": {}, "n_fields": 0,
                           "with_metrics": 0, "with_results": 0,
                           "added_ids": []}
    existing = {n.label.strip().lower(): n
                for n in graph.by_type("Benchmark")
                if "canonical:" not in n.id}

    def _apply(n, family: str, base: Dict[str, Any]):
        lists = _lists_for(n.id, pg)
        inp, outp, mod, obj, scale = FAMILY_CORE.get(
            family, ("unknown", "unknown", "unknown", "unknown", "unknown"))
        values = {"name": n.label, "input_form": inp, "output_form": outp,
                  "modality": mod, "research_object": obj, "scale": scale,
                  "n_samples": SAMPLE_HINTS.get(n.label, "unknown"),
                  "provenance": base.pop("provenance", "graph_extraction")}
        # KNOWN / 图节点里已有的核心属性优先
        for k in ("input_form", "output_form", "modality", "research_object",
                  "scale", "n_samples"):
            v = base.get(k) or n.attrs.get(k)
            if v and v != "unknown":
                values[k] = v
        values.update(lists)
        uniform = _uniform(family, values)
        label = n.label
        # E9：不再 attrs.clear() 抹掉溯源，保留 4 个装配溯源键与内部 id
        keep = {k: v for k, v in n.attrs.items()
                if k in ("label", "source_locator", "assembly_provenance",
                         "run_id", "inputs_sha", "paper_ids",
                         "canonical_id", "canonical_name")}
        n.attrs.clear()
        n.attrs.update(keep)
        n.attrs.update({"label": label,
                        "filled_by": "benchmark_lean_v2"})
        n.attrs.update(uniform)
        n.attrs["matrix"] = lists.get("matrix")
        rep["n_fields"] += len(uniform)
        rep["by_family"][family] = rep["by_family"].get(family, 0) + 1
        rep["with_metrics"] += int(bool(lists["metrics"]))
        rep["with_results"] += int(bool(lists["model_results"]))

    for n in graph.by_type("Benchmark"):
        if "canonical:" in n.id:
            continue
        fam = classify_rule(n.label) or "molecule_generation"
        base: Dict[str, Any] = {}
        for f, table in KNOWN.items():
            if n.label in table:
                fam, base = f, dict(table[n.label])
                break
        base.setdefault("provenance", "graph_extraction+domain_knowledge")
        _apply(n, fam, base)
        rep["n_existing"] += 1

    for fam, table in KNOWN.items():
        for label, fields in table.items():
            if label.strip().lower() in existing:
                continue
            bid = "benchmark:kb:" + _slug(label)
            if bid in graph.nodes:
                continue
            n = graph.node(bid, "Benchmark", label,
                           provenance="domain_knowledge",
                           filled_by="benchmark_expand_v1")
            rep["n_added"] += 1
            rep["added_ids"].append(bid)
            _apply(n, fam, {**fields, "provenance": "domain_knowledge"})
    if persist:
        p = Path(report_path) if report_path else OUT
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rep, ensure_ascii=False, indent=2),
                     encoding="utf-8")
        if save_graph:
            graph.save(graph_path)
    return rep


CLASSIFY_PROMPT = """你是基准族判定器。只根据基准名称从封闭词表里选**一个**类别，
输出严格 JSON（纯 JSON，不要代码块）：
{"family_id":"","confidence":0.9,"evidence":"逐字引文"}
词表：{families}
只能选词表里的 id；判断不了输出 {"family_id":"unknown"}。
【基准名】{name}
【上下文】{context}
"""

EXTRACT_PROMPT = """你是「{label}」基准属性抽取器。
该类基准特征：{description}
只基于【论文片段】抽取下面字段，输出严格 JSON（纯 JSON，不要代码块）：
{fields}
规则：
1. 枚举字段只能从候选里选；没有依据填 "unknown"，列表字段填 []，禁止编造。
2. 文本字段 ≤60 字；evidence 必须是【论文片段】逐字短句（≤100 字）。
3. 不要输出词表外的字段。metrics/baselines/model_results 必须是数组。
【基准名】{name}
【论文片段】{text}
"""


def _norm_ev(s: str) -> str:
    s = re.sub(r"-\s*\n\s*", "", str(s or ""))
    s = re.sub(r"-\s+(?=[a-z])", "", s)
    return re.sub(r"\s+", " ", s).strip().lower().replace("’", "'")


def _validate(family: str, data: Dict[str, Any], text: str = ""
              ) -> List[str]:
    issues: List[str] = []
    enums = enum_values(family)
    specs = schema_for(family).get("all_fields", {})
    for k, v in (data or {}).items():
        if k not in specs:
            issues.append(f"unknown_field:{k}")
            continue
        spec = specs[k]
        if spec.get("type") == "list":
            if not isinstance(v, list):
                issues.append(f"needs_list:{k}")
            continue
        if k in enums and v not in enums[k] and v != "unknown":
            issues.append(f"bad_enum:{k}={v}")
        if isinstance(v, (dict, list)):
            issues.append(f"bad_type:{k}")
    ev = str((data or {}).get("evidence") or "")
    if ev and text and ev != "unknown" and \
            _norm_ev(ev) not in _norm_ev(text) and \
            _norm_ev(ev)[:60] not in _norm_ev(text):
        issues.append("evidence_not_verbatim")
    return issues


def classify_family(name: str, context: str = "", *, chat_fn: Any = None,
                    use_llm: bool = True) -> Dict[str, Any]:
    fam = classify_rule(name)
    if fam:
        return {"family_id": fam, "source": "rule",
                "label": FAMILIES[fam]["label"], "confidence": 1.0}
    if not use_llm:
        return {"family_id": "unknown", "source": "none",
                "label": "未分类", "confidence": 0.0}
    from ..llm.backends import chat as _chat
    from ..utils import parse_llm_json
    fn = chat_fn or (lambda p, **kw: _chat(p, backend="vllm", **kw))
    prompt = (CLASSIFY_PROMPT.replace("{families}", ", ".join(FAMILY_IDS))
              .replace("{name}", name)
              .replace("{context}", (context or "")[:1400]))
    try:
        d = parse_llm_json(fn(prompt, max_tokens=600, timeout=180)) or {}
        fid = str(d.get("family_id") or "unknown")
        if fid not in FAMILIES:
            fid = "unknown"
        ev = str(d.get("evidence") or "")
        no_signal = (not any(a in name.lower()
                            for f in FAMILIES.values() for a in f["aliases"])
                     and not ev)
        return {"family_id": fid, "source": "llm",
                "label": FAMILIES.get(fid, {}).get("label", "未分类"),
                "confidence": d.get("confidence"),
                "needs_review": no_signal}
    except Exception as exc:  # noqa: BLE001
        return {"family_id": "unknown", "source": "error",
                "label": "未分类", "error": f"{type(exc).__name__}:{exc}"[:120]}


FAMILY_FACET = {
    "molecule_generation": ("分子生成", "小分子", "1D 序列/SMILES"),
    "property_prediction": ("性质/能量预测", "小分子", "性质向量/表格"),
    "quantum_energy": ("性质/能量预测", "材料/力场", "3D 结构/坐标"),
    "structure_docking": ("结构/对接", "蛋白/口袋", "3D 结构/坐标"),
    "peptide_sequence": ("多肽/序列设计", "多肽", "1D 序列/SMILES"),
    "instruction_dataset": ("指令/数据集", "小分子", "文本/指令"),
    "reaction_synthesis": ("反应/合成", "反应/合成", "1D 序列/SMILES"),
}


def extract_by_family(name: str, family: str, text: str, *,
                      chat_fn: Any = None) -> Dict[str, Any]:
    """按族模板生成专属 prompt，LLM 理解填充，规则校验。"""
    sch = schema_for(family)
    if not sch:
        return {"ok": False, "issues": [f"unknown_family:{family}"]}
    lines = []
    for k, spec in sch["all_fields"].items():
        if spec.get("type") == "enum":
            lines.append(f'  "{k}": 只能从 {spec["enum"]} 选')
        elif spec.get("type") == "list":
            lines.append(f'  "{k}": 数组（无依据填 []）')
        else:
            lines.append(f'  "{k}": {spec.get("hint") or "短文本"}')
    prompt = (EXTRACT_PROMPT.replace("{label}", sch["label"])
              .replace("{description}", sch["description"])
              .replace("{fields}", "字段说明：\n" + "\n".join(lines))
              .replace("{name}", name)
              .replace("{text}", (text or "")[:6000]))
    from ..llm.backends import chat as _chat
    from ..utils import parse_llm_json
    fn = chat_fn or (lambda p, **kw: _chat(p, backend="vllm", **kw))
    attempts, issues = [], []
    for i in range(3):
        try:
            raw = fn(prompt, max_tokens=1500, timeout=240)
            data = parse_llm_json(raw) or {}
            issues = _validate(family, data, text)
            attempts.append({"i": i, "issues": issues[:6],
                             "out_chars": len(raw or "")})
            if not issues:
                # 类别判定之后，公共分类字段由规则按族锁定，避免 LLM 与族冲突
                t, o, m = FAMILY_FACET.get(family, (None, None, None))
                if t:
                    data["task_family"] = t
                    data["research_object"] = o
                    data["modality"] = m
                return {"ok": True, "family": family, "data": data,
                        "uniform": _uniform(family, data),
                        "rule_override": ["task_family", "research_object",
                                          "modality"],
                        "attempts": attempts}
            if i == 1:
                prompt += ('\n【收窄契约】只输出 6 个字段：name, task_family, '
                           'research_object, modality, metrics, evidence；'
                           'metrics 填 []，evidence 留空字符串。')
            else:
                prompt += "\n【修正】" + "; ".join(issues[:4])
        except Exception as exc:  # noqa: BLE001
            attempts.append({"i": i, "error": str(exc)[:120]})
    return {"ok": False, "family": family, "data": {},
            "issues": issues, "attempts": attempts}


def extract_benchmark(name: str, text: str, *, chat_fn: Any = None,
                      use_llm: bool = True) -> Dict[str, Any]:
    cls = classify_family(name, text, chat_fn=chat_fn, use_llm=use_llm)
    if cls["family_id"] == "unknown":
        return {"ok": False, "stage": "classify", "classify": cls}
    ex = extract_by_family(name, cls["family_id"], text, chat_fn=chat_fn)
    return {"ok": ex["ok"], "stage": "extract", "classify": cls,
            "extract": ex}


def refresh_from_pg(graph: Any, *, benchmark_ids: Optional[List[str]] = None,
                    persist: bool = True, save_graph: bool = True,
                    graph_path: str = "storage_cf/sciforge/batch10_final_graph.json"
                    ) -> Dict[str, Any]:
    """新论文抽取后刷新基准节点的可更新表（含 SOTA 重算）。

    这是「表格会变化」的关键：PG 里新增/覆盖行之后，图节点的
    metrics / model_results / sota_by_metric / matrix / source_papers 全部重算。
    """
    pg = _pg_rows()
    ids = set(benchmark_ids) if benchmark_ids else None
    rep: Dict[str, Any] = {"refreshed": 0, "with_results": 0,
                           "sota_changes": []}
    for n in graph.by_type("Benchmark"):
        if "canonical:" in n.id or (ids and n.id not in ids):
            continue
        lists = _lists_for(n.id, pg)
        old = n.attrs.get("sota_by_metric") or {}
        new = lists["sota_by_metric"]
        for metric, s in new.items():
            prev = (old.get(metric) or {}).get("model")
            if prev and prev != s["model"]:
                rep["sota_changes"].append(
                    {"benchmark": n.id, "metric": metric,
                     "from": prev, "to": s["model"]})
        n.attrs.update({"is_evaluation": lists.get("is_evaluation", True),
                        "metrics": lists["metrics"],
                        "model_results": lists["model_results"],
                        "sota_by_metric": new,
                        "matrix": lists["matrix"]})
        n.attrs.pop("source_papers", None)
        n.attrs.pop("provenance", None)
        rep["refreshed"] += 1
        rep["with_results"] += int(bool(lists["model_results"]))
    if persist and save_graph:
        graph.save(graph_path)
    return rep


def extract_and_refresh(aid: str, graph: Any, md_text: str, *,
                        persist: bool = True) -> Dict[str, Any]:
    """端到端：论文表格抽取 → 写 PG → 刷新图节点的可更新表与 SOTA。"""
    from .pgstore import import_tables
    paper_id = f"paper:{aid}"
    imp = import_tables(aid, paper_id, md_text)
    ref = refresh_from_pg(
        graph, benchmark_ids=imp.get("benchmark_ids"), persist=persist,
        save_graph=False)   # 存图由 assemble_stage3 统一做
    return {"import": imp, "refresh": ref}
