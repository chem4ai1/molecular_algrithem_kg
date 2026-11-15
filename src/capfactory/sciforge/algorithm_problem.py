"""算法框架 v2：以「解决什么问题 + 机理」为核心，而非「论文角色」。

用户要求：
* 论文角色是动态概念（同一算法在不同论文里可能是方法/基线），改成**任务类型**，
  便于以后找相关基线做对比实验；
* 算法最重要的是「解决什么问题、机理是什么」，即使原文没谈也要由大模型
  **分析理解**填充（标 filled_by=llm_inference，与原文事实区分）；
* 要能基于「我要解决的问题/描述」智能搜索到能解决该问题的方法；
* 抽取时给出**原论文**：找到算法名附近的引用标号 [n]，反查参考文献。
"""
from __future__ import annotations
import json, re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .algorithm_schema import classify_rule, schema_for, FAMILIES

TASK_TYPES = {
    "molecule_generation": "分子生成",
    "molecule_optimization": "分子优化/多目标",
    "property_prediction": "性质/能量预测",
    "structure_docking": "结构预测/对接",
    "sequence_design": "序列/多肽设计",
    "reaction_prediction": "反应/逆合成预测",
    "instruction_multitask": "指令/多任务",
    "sampling_acceleration": "采样加速/推测解码",
    "forcefield_simulation": "力场/分子模拟",
    "representation_pretrain": "表示学习/预训练",
    "classifier_screening": "分类器引导/筛选",
    "wetlab_baseline": "湿实验/实验基线",
}

CORE_FIELDS = ("name", "schema_family", "task_type", "task_type_label",
               "problems_solved", "mechanism", "mechanism_steps",
               "why_it_works", "applicable_to", "limitations",
               "source_paper", "source_ref_no", "baseline_group",
               "object_kind", "modality", "search_text")

CORE_LABELS = {
    "name": "算法名称", "schema_family": "算法族",
    "task_type": "任务类型", "task_type_label": "任务类型（中文）",
    "problems_solved": "能解决什么问题", "mechanism": "机理",
    "mechanism_steps": "机理分步", "why_it_works": "为什么有效（LLM 理解）",
    "applicable_to": "适用场景", "limitations": "局限",
    "source_paper": "原论文", "source_ref_no": "引用标号",
    "baseline_group": "可对比基线分组", "object_kind": "作用对象",
    "modality": "数据模态", "search_text": "检索文本"}

# 族级任务类型与机理解释（用于未单独描述的算法）
FAMILY_TASK = {
    "autoregressive": ("instruction_multitask", "序列自回归生成"),
    "vae": ("molecule_generation", "编码-潜空间-解码重建"),
    "gan": ("molecule_generation", "生成器与判别器对抗"),
    "diffusion": ("molecule_generation", "逐步加噪与去噪采样"),
    "flow": ("molecule_generation", "连续向量场/ODE 映射"),
    "geometric_gnn": ("property_prediction", "等变消息传递"),
    "fragment": ("molecule_generation", "片段分解与自回归组装"),
    "classical_forcefield": ("forcefield_simulation", "参数化解析势函数"),
    "rnn": ("sequence_design", "循环网络逐 token 生成"),
    "instruction_tuning": ("instruction_multitask", "提示/条件 token 适配"),
    "speculative_sampling": ("sampling_acceleration", "廉价提议+精确校验"),
    "classifier_guidance": ("classifier_screening", "分类器引导/筛选"),
    "evolutionary": ("molecule_optimization", "种群搜索与适应度"),
    "wetlab": ("wetlab_baseline", "湿实验合成与筛选"),
}

KNOWN_PROBLEMS: Dict[str, Dict[str, Any]] = {
    "MolMiner": {
        "task_type": "molecule_generation",
        "problems_solved": [
            "需要 3D 感知、可控的分子从头设计，避免 SMILES 逐字符生成造成结构不合法",
            "需要在生成阶段直接控制环/片段骨架，而不是事后过滤"],
        "mechanism": "用 RDKit 把分子切成片段并建立带对称性规范化映射的连接点词表，"
                     "再用 decoder-only Transformer 自回归预测下一片段与连接位置，"
                     "用几何感知约束保证 3D 合理性",
        "why_it_works": "把化学合法性约束前移到片段词表与连接点表示层，减少无效采样",
        "applicable_to": ["无条件分子生成", "属性条件分子生成", "骨架约束设计"],
        "limitations": ["依赖片段词表覆盖度"]},
    "SO3LR Tauri": {
        "task_type": "forcefield_simulation",
        "problems_solved": ["需要可迁移到多种体系的机器学习力场，同时给出能量与力",
                            "需要统一建模长程相互作用与短程等变几何"],
        "mechanism": "SO3krates 等变消息传递网络学习短程势，叠加显式长程静电/色散项，"
                     "在能量与力上联合训练",
        "why_it_works": "等变性保证旋转平移下的物理正确性，显式长程项弥补感受野限制",
        "applicable_to": ["分子动力学", "能量/力预测", "水与材料体系"]},
    "AntiFold": {
        "task_type": "structure_docking",
        "problems_solved": ["给定抗体骨架结构，设计能保持结合能力的 CDR 序列"],
        "mechanism": "以 ESM-IF1 逆折叠模型为底座，用抗体 IMGT 编号与结构几何微调，"
                     "在骨架条件下自回归采样 CDR 残基",
        "why_it_works": "结构条件把序列空间约束到可折叠子集",
        "applicable_to": ["抗体 CDR 设计", "结构基序列设计"]},
    "AMP-Designer": {
        "task_type": "sequence_design",
        "problems_solved": ["需要生成同时具备抗菌活性与低毒性的短肽序列"],
        "mechanism": "AMP-GPT 自回归生成候选肽，配合提示微调、条件 token 与蒸馏，"
                     "再用多预测器集成与 MIC 回归筛选",
        "why_it_works": "生成模型探索序列空间，判别/回归模型把活性约束回填到采样",
        "applicable_to": ["抗菌肽设计", "序列活性优化"]},
    "Lingo3DMol": {
        "task_type": "structure_docking",
        "problems_solved": ["给定蛋白口袋，生成 3D 构象合理且能结合的配体分子"],
        "mechanism": "Transformer encoder-decoder 编码口袋与已生成片段，"
                     "自回归产生受 NCI 约束的 3D 坐标",
        "why_it_works": "把口袋几何与非共价相互作用模式作为条件，减少对接失败率",
        "applicable_to": ["口袋条件分子生成", "结构基药物设计"]},
    "TargetDiff": {
        "task_type": "molecule_generation",
        "problems_solved": ["需要同时生成原子类型与 3D 坐标，且满足口袋几何"],
        "mechanism": "在连续 3D 坐标与离散原子类型上做扩散，等变 GNN 去噪，"
                     "从噪声逐步还原口袋条件分子",
        "why_it_works": "扩散天然处理连续坐标，等变性保证旋转下的一致预测",
        "applicable_to": ["口袋条件 3D 生成"]},
    "Mol-Instructions": {
        "task_type": "instruction_multitask",
        "problems_solved": ["让语言模型遵循自然语言指令完成多种分子/蛋白任务"],
        "mechanism": "构建跨分子、蛋白质、生物文本的指令数据集并对基座 LM 微调",
        "why_it_works": "统一任务表述让一个模型共享不同分子任务的归纳偏置",
        "applicable_to": ["分子描述", "性质预测", "反应预测"]},
    "MOLGEN": {
        "task_type": "molecule_generation",
        "problems_solved": ["需要生成语法完全合法且可针对属性优化的分子"],
        "mechanism": "基于 SELFIES 的双向+自回归预训练，配合分子前缀微调与化学反馈对齐",
        "why_it_works": "SELFIES 保证每个 token 串都能解析成合法分子，前缀微调注入属性目标",
        "applicable_to": ["分子生成", "属性优化"]},
    "Langevin Speculative Dynamics": {
        "task_type": "sampling_acceleration",
        "problems_solved": ["生成采样（尤其扩散/朗之万）步数多、代价高，需要加速"],
        "mechanism": "用廉价 Langevin 提议产生多个候选，再用精确校验/拒绝采样接受",
        "why_it_works": "把串行去噪换成可并行提议+批量校验，减少昂贵网络前向次数",
        "applicable_to": ["扩散采样加速", "分子构象采样"]},
    "SchNet": {
        "task_type": "property_prediction",
        "problems_solved": ["从原子坐标直接预测分子能量/性质，无需手工描述符"],
        "mechanism": "连续滤波卷积在原子间距离上做消息传递，聚合得到能量",
        "why_it_works": "距离连续滤波对几何扰动平滑，适合量子化学回归",
        "applicable_to": ["能量预测", "力预测"]},
    "ChemicalVAE": {
        "task_type": "molecule_generation",
        "problems_solved": ["需要可插值、可优化的连续分子隐空间"],
        "mechanism": "CNN 编码 SMILES 到高斯潜空间，RNN 解码重建，KL 约束先验",
        "why_it_works": "连续潜空间支持贝叶斯优化与属性插值",
        "limitations": ["SMILES 合法性不稳"]},
    "CLaSS": {
        "task_type": "classifier_screening",
        "problems_solved": ["从生成候选里筛出符合活性/属性标签的分子"],
        "mechanism": "用分类器对候选打分，按阈值或 TopK 筛选",
        "why_it_works": "把判别模型知识作为生成后验的近似",
        "applicable_to": ["条件生成", "候选筛选"]},
    "CFPS": {
        "task_type": "wetlab_baseline",
        "problems_solved": ["实验验证候选肽的真实抗菌活性（非计算方法）"],
        "mechanism": "细胞游离蛋白合成体系表达肽并测 MIC",
        "why_it_works": "体外实测绕开预测器偏差，是真值来源",
        "applicable_to": ["AMP 实验验证"]},
}


def _defaults(n: Any, family: str) -> Dict[str, Any]:
    task, mech = FAMILY_TASK.get(family, ("instruction_multitask", "见算法族"))
    label = schema_for(family).get("label", family)
    return {
        "task_type": task,
        "problems_solved": [f"面向{label}类任务的方法/基线，可用于同类问题对比实验"],
        "mechanism": f"{label}：{mech}",
        "why_it_works": "unknown（待 LLM 基于原论文分析填充）",
        "applicable_to": [TASK_TYPES.get(task, task)],
        "limitations": [],
    }


def core_of(n: Any, graph: Any) -> Dict[str, Any]:
    family = n.attrs.get("schema_family") or classify_rule(n.label) \
        or "autoregressive"
    d = KNOWN_PROBLEMS.get(n.label) or _defaults(n, family)
    task = d["task_type"]
    src = n.attrs.get("source_paper") or {}
    if isinstance(src, str):
        src = {"title": src}
    obj = n.attrs.get("object_kind") or "unknown"
    mod = n.attrs.get("modality") or "unknown"
    mech = d["mechanism"]
    search_text = (f"{n.label}. 任务类型：{TASK_TYPES.get(task, task)}. "
                   f"能解决的问题：{' '.join(d['problems_solved'])}. "
                   f"机理：{mech}. 为什么有效：{d.get('why_it_works','')}. "
                   f"适用：{' '.join(d.get('applicable_to') or [])}")
    return {
        "name": n.label, "schema_family": family,
        "task_type": task, "task_type_label": TASK_TYPES.get(task, task),
        "problems_solved": d["problems_solved"],
        "mechanism": mech,
        "mechanism_steps": [x.strip() for x in re.split(r"[；;，,]", mech)
                            if x.strip()][:4],
        "why_it_works": d.get("why_it_works", "unknown"),
        "applicable_to": d.get("applicable_to") or [],
        "limitations": d.get("limitations") or [],
        "source_paper": src,
        "source_ref_no": n.attrs.get("source_ref_no") or "",
        # 以任务类型为主分组，保证同任务能找到可对比基线；
        # 对象已知时再细分，但不再用常为 unknown 的 modality 把组切碎
        "baseline_group": (task if obj in ("unknown", "未分类对象", "")
                           else f"{task}|{obj}"),
        "object_kind": obj, "modality": mod,
        "search_text": search_text,
        "filled_by": ("domain_knowledge" if n.label in KNOWN_PROBLEMS
                      else "family_default"),
        "schema_version": "v2_problem_centric",
    }


def fill_library(graph: Any, *, persist: bool = True,
                 report_path: str = "storage_cf/sciforge/algorithm_problem_report.json"
                 ) -> Dict[str, Any]:
    rep: Dict[str, Any] = {"n_algorithms": 0, "by_task_type": {},
                           "with_explicit_mechanism": 0,
                           "with_source_paper": 0, "baseline_groups": {}}
    for n in graph.by_type("Algorithm"):
        core = core_of(n, graph)
        label = n.label
        n.attrs.clear()
        n.attrs.update({"label": label})
        n.attrs.update(core)
        rep["n_algorithms"] += 1
        rep["by_task_type"][core["task_type"]] = \
            rep["by_task_type"].get(core["task_type"], 0) + 1
        rep["with_explicit_mechanism"] += int(
            bool(core["mechanism"]) and "见算法族" not in core["mechanism"])
        rep["with_source_paper"] += int(bool(core["source_paper"]))
        g = core["baseline_group"]
        rep["baseline_groups"][g] = rep["baseline_groups"].get(g, 0) + 1
    if persist:
        p = Path(report_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rep, ensure_ascii=False, indent=2),
                     encoding="utf-8")
        graph.save("storage_cf/sciforge/batch10_final_graph.json")
    return rep


def find_source_paper(name: str, md: str, *, host_title: str = "",
                      host_arxiv_id: str = "") -> Dict[str, Any]:
    """找算法名附近的引用标号 [n]，多位置投票后反查参考文献。

    避免两个已知噪声：本文方法名旁的自引用、标题区附近的编号。
    """
    from .citations import parse_references
    import collections as _c
    refs = {r["ref_no"]: r for r in parse_references(md)}
    if not refs:
        return {"ref_no": "", "status": "no_references_section"}
    text = md or ""
    head_end = min(600, len(text))
    # 本论文提出的方法：原论文就是当前论文，不必反查引用
    if host_title and _norm_text(name) in _norm_text(host_title):
        return {"ref_no": "", "status": "host_paper",
                "title": host_title, "arxiv_id": host_arxiv_id,
                "doi": "", "year": "", "raw": ""}
    votes: List[str] = []
    pat = re.compile(re.escape(name.strip()), re.I)
    for m in pat.finditer(text):
        window = text[max(0, m.start() - 160): m.end() + 160]
        votes += [x for x in re.findall(r"\[(\d{1,3})\]", window)]
    votes = [v for v in votes if v in refs]
    if not votes:
        return {"ref_no": "", "status": "no_nearby_marker"}
    count = _c.Counter(votes)
    # 标题区出现过的不优先（多为自引用）
    ordered = [v for v, _ in count.most_common()
               if not re.search(r"\[" + re.escape(v) + r"\]", text[:head_end])]
    best = (ordered or list(count))[0]
    r = refs[best]
    out = {"ref_no": best, "status": "resolved",
           "title": r.get("title", ""), "arxiv_id": r.get("arxiv_id", ""),
           "doi": r.get("doi", ""), "year": r.get("year", ""),
           "raw": r.get("raw", "")[:200],
           "votes": dict(count)}
    if count[best] == 1 and re.search(r"\[" + re.escape(best) + r"\]",
                                     text[:head_end]):
        out["status"] = "self_citation_suspect"
    return out


def _norm_text(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s or "").lower())


def local_context(name: str, md: str, *, window: int = 700) -> str:
    """只取算法名附近片段，避免把宿主论文主方法的机制误套到基线算法上。"""
    text = md or ""
    pat = re.compile(re.escape(name.strip()), re.I)
    ms = list(pat.finditer(text))[:3]
    chunks = []
    for m in ms:
        chunks.append(text[max(0, m.start() - window): m.end() + window])
    return "\n...\n".join(chunks)[:5000] or text[:3000]


INFER_PROMPT = """你是算法机理分析器。目标不是复述原文，而是**理解并推断**
这个算法「能解决什么问题、机理是什么、为什么有效」，用于后续按问题语义检索方法。

【算法名】{name}
【算法族】{family_label}（特征：{family_desc}）
【该算法附近的论文片段】{text}

重要约束：{name} 只是本篇论文里的一个方法或基线算法，**不是宿主论文的主方法**。
只描述该算法自身的机理，禁止把论文主方法的机制（如神经网络结构、训练规模）
套到它上面。若片段里没有描述它，就基于「算法族」做合理推断，
并在 inference_basis 明确写「由算法族推断」，不要伪装成原文依据。

输出严格 JSON（纯 JSON，不要代码块）：
{
 "task_type": 只能从 {task_types} 选一个,
 "problems_solved": ["它具体能解决什么问题（1-3 条，每条<=60字）"],
 "mechanism": "用 1-2 句说明它怎么做（<=140字）",
 "why_it_works": "为什么这个机理有效（<=100字）",
 "applicable_to": ["适用场景"],
 "limitations": ["已知或合理推断的局限"],
 "confidence": 0.0-1.0,
 "inference_basis": "原文依据 / 由算法族推断 / 由名称推断"
}
规则：
1. 即使原文没有直接说明，也要基于算法名称、算法族与上下文做**合理分析推断**，
   并在 inference_basis 里明确标注；不要输出空数组。
2. task_type 必须是给定枚举 id 之一；其它字段不得编造具体数值或引用。
3. 不要输出词表外的字段。
"""


def infer_problem_core(name: str, family: str, text: str, *,
                       chat_fn: Any = None) -> Dict[str, Any]:
    """LLM 分析理解填充问题/机理；即使原文没谈也要给合理推断并标注来源。"""
    from ..llm.backends import chat as _chat
    from ..utils import parse_llm_json
    sch = schema_for(family)
    prompt = (INFER_PROMPT
              .replace("{name}", name)
              .replace("{family_label}", sch.get("label", family))
              .replace("{family_desc}", sch.get("description", ""))
              .replace("{task_types}", ", ".join(TASK_TYPES))
              .replace("{text}", local_context(name, text)))
    fn = chat_fn or (lambda p, **kw: _chat(p, backend="vllm", **kw))
    issues: List[str] = []
    for i in range(2):
        try:
            raw = fn(prompt, max_tokens=1200, timeout=240)
            d = parse_llm_json(raw) or {}
            issues = []
            if d.get("task_type") not in TASK_TYPES:
                issues.append("bad_task_type")
            for k in ("problems_solved", "applicable_to", "limitations"):
                if not isinstance(d.get(k), list):
                    issues.append(f"needs_list:{k}")
            for k in ("mechanism", "why_it_works"):
                if not isinstance(d.get(k), str) or len(d[k]) < 8:
                    issues.append(f"needs_text:{k}")
            blob = (str(d.get("mechanism") or "") + " " +
                    str(d.get("why_it_works") or "")).lower()
            if family == "classical_forcefield" and re.search(
                    r"so3krates|transformer|神经网络|1\.48亿|消息传递网络", blob):
                issues.append("family_conflict:经典力场不应是神经网络势")
            if not issues:
                d["filled_by"] = "llm_inference"
                d["schema_family"] = family
                d["source_paper"] = {}
                return {"ok": True, "data": d, "attempts": i + 1}
            prompt += "\n【修正】" + "; ".join(issues[:4])
        except Exception as exc:  # noqa: BLE001
            issues.append(f"{type(exc).__name__}:{exc}"[:100])
    return {"ok": False, "issues": issues, "attempts": 2}


def extract_algorithm_v2(name: str, md: str, *, chat_fn: Any = None,
                         use_llm: bool = True, host_title: str = "",
                         host_arxiv_id: str = "") -> Dict[str, Any]:
    """算法抽取入口：判族 → 引用反查原论文 → LLM 分析问题/机理。"""
    family = classify_rule(name) or "autoregressive"
    src = find_source_paper(name, md, host_title=host_title,
                            host_arxiv_id=host_arxiv_id)
    out: Dict[str, Any] = {"name": name, "family": family,
                           "source_paper": src}
    if use_llm:
        r = infer_problem_core(name, family, md, chat_fn=chat_fn)
        out["inference"] = r
        if r["ok"]:
            d = r["data"]
            d["source_paper"] = src
            d["source_ref_no"] = src.get("ref_no", "")
            out["core"] = d
    return out


INDEX_PATH = Path("storage_cf/sciforge/algorithm_search_index.json")


def build_index(graph: Any) -> Dict[str, Any]:
    """为每个算法建检索文本索引（向量优先，失败则落 JSON 供关键词降级）。"""
    items = []
    for n in graph.by_type("Algorithm"):
        txt = n.attrs.get("search_text")
        if not txt:
            core = core_of(n, graph)
            txt = core["search_text"]
        items.append({"id": n.id, "text": txt,
                      "meta": {"name": n.label,
                               "task_type": n.attrs.get("task_type"),
                               "baseline_group": n.attrs.get("baseline_group")}})
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    stored = 0
    try:
        from ..vector.store import VectorStore
        vs = VectorStore(name="algorithms")
        stored = vs.add(items)
        vs.save()
        return {"ok": True, "backend": "bge-m3+VectorStore",
                "n_items": len(items), "n_new_vectors": stored,
                "path": str(INDEX_PATH)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": True, "backend": "json_keyword_fallback",
                "n_items": len(items), "n_new_vectors": 0,
                "error": f"{type(exc).__name__}:{exc}"[:120],
                "path": str(INDEX_PATH)}


def _keyword_score(query: str, text: str) -> float:
    import difflib
    q, t = _norm_text(query), _norm_text(text)
    if not q or not t:
        return 0.0
    base = difflib.SequenceMatcher(None, q, t).ratio()
    # 中文/英文词级命中加权
    words = [w for w in re.split(r"[\s,，、;；。]+", query.lower()) if len(w) >= 2]
    hit = sum(1 for w in words if w.lower() in text.lower())
    return round(min(1.0, base + 0.12 * hit), 4)


def search_algorithms(query: str, *, graph: Any = None,
                      top_k: int = 8, task_type: str = "",
                      include_baselines: bool = True) -> Dict[str, Any]:
    """基于问题描述智能找到可用方法，并给出可对比基线。"""
    if graph is None:
        from ..po import POGraph
        from ..web.extraction_api import GRAPH_PATH
        graph = POGraph.load(str(GRAPH_PATH))
    if not INDEX_PATH.exists():
        build_index(graph)
    items = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    hits: List[Dict[str, Any]] = []
    try:
        from ..vector.store import VectorStore
        vs = VectorStore(name="algorithms")
        hits = vs.search(query, top_k=top_k * 3,
                         filter_fn=lambda it: not task_type or
                         (it.get("meta") or {}).get("task_type") == task_type)
        backend = "bge-m3"
    except Exception:  # noqa: BLE001
        backend = "keyword_fallback"
        scored = []
        for it in items:
            meta = it.get("meta") or {}
            if task_type and meta.get("task_type") != task_type:
                continue
            scored.append((_keyword_score(query, it["text"]), it))
        scored.sort(key=lambda x: -x[0])
        hits = [{"id": it["id"], "score": sc,
                 "text": it["text"][:300], "meta": it["meta"]}
                for sc, it in scored[:top_k * 3] if sc > 0]
    by_id = {n.id: n for n in graph.by_type("Algorithm")}
    out = []
    for h in hits:
        n = by_id.get(h["id"])
        if not n:
            continue
        a = n.attrs
        entry = {"id": n.id, "name": n.label, "score": h["score"],
                 "task_type": a.get("task_type"),
                 "task_type_label": a.get("task_type_label"),
                 "problems_solved": a.get("problems_solved") or [],
                 "mechanism": a.get("mechanism"),
                 "why_it_works": a.get("why_it_works"),
                 "source_paper": a.get("source_paper") or {},
                 "baseline_group": a.get("baseline_group")}
        if include_baselines:
            group = a.get("baseline_group")
            task = a.get("task_type")
            same_group, same_task = [], []
            for x in graph.by_type("Algorithm"):
                if x.id == n.id:
                    continue
                if x.attrs.get("baseline_group") == group:
                    same_group.append(x.label)
                elif x.attrs.get("task_type") == task:
                    same_task.append(x.label)
            entry["comparable_baselines"] = (same_group + same_task)[:8]
            entry["baseline_scope"] = "同任务+同对象" if same_group else "同任务"
        out.append(entry)
        if len(out) >= top_k:
            break
    return {"query": query, "backend": backend, "count": len(out),
            "task_type_filter": task_type or None, "results": out}


# 新族默认任务（依据全量 LLM 推断结果校准族-任务映射）
FAMILY_TASK.update({
    "ml_potential": ("forcefield_simulation", "神经网络拟合势能面"),
    "inverse_folding": ("sequence_design", "结构条件逆折叠"),
    "general_lm": ("representation_pretrain", "通用预训练基座"),
    "peptide_lm": ("sequence_design", "氨基酸序列语言模型"),
})
# 通用 LM 白名单：防止宿主分子论文把 LLaMA 判成「分子生成」
GENERAL_LM = {"LLaMA", "Stanford Alpaca", "GPT4All", "SMILES-based PLMs"}
ML_POTENTIAL = {"SO3LR", "SO3LR Tauri", "MACE-POLAR-1-M",
                "AIMNet2-2025", "UMA-S-1.2.1", "SchNet"}
INVERSE_FOLDING = {"ESM-IF1", "ProteinMPNN", "AbMPNN", "AntiFold"}


def reclassify(graph: Any, *, persist: bool = True) -> Dict[str, Any]:
    """结合新增算法族 + 全量推断结果，重新归类全部算法并统一任务类型。"""
    rep: Dict[str, Any] = {"n_algorithms": 0, "by_family": {},
                           "by_task_type": {}, "changed_family": [],
                           "changed_task": []}
    for n in graph.by_type("Algorithm"):
        old_fam = n.attrs.get("schema_family")
        old_task = n.attrs.get("task_type")
        name = n.label
        if name in GENERAL_LM:
            fam, task = "general_lm", "representation_pretrain"
        elif name in ML_POTENTIAL:
            fam, task = "ml_potential", "forcefield_simulation"
        elif name in INVERSE_FOLDING:
            fam, task = "inverse_folding", "sequence_design"
        elif name == "Huang et al. RNN":
            # 关键词 "rnn" 过宽选错论文，用族默认纠正
            fam, task = "rnn", "sequence_design"
        elif name.startswith("AMP-") or name in (
                "Condition Token (CT)", "Fine-Tuning (FT)"):
            fam = "peptide_lm" if name.startswith("AMP-") else \
                old_fam or "rnn"
            task = "sequence_design" if name.startswith("AMP-") else \
                (old_task or "sequence_design")
        else:
            fam = classify_rule(name) or old_fam or "autoregressive"
            task = old_task or FAMILY_TASK.get(fam, ("", ""))[0]
        if task not in TASK_TYPES:
            task = FAMILY_TASK.get(fam, ("", ""))[0] or "instruction_multitask"
        if old_fam != fam:
            rep["changed_family"].append({"name": name,
                                          "from": old_fam, "to": fam})
        if old_task != task:
            rep["changed_task"].append({"name": name,
                                        "from": old_task, "to": task})
        n.attrs["schema_family"] = fam
        n.attrs["task_type"] = task
        n.attrs["task_type_label"] = TASK_TYPES.get(task, task)
        obj = n.attrs.get("object_kind") or ""
        n.attrs["baseline_group"] = (
            task if obj in ("unknown", "未分类对象", "")
            else f"{task}|{obj}")
        n.attrs["search_text"] = (
            f"{name}. 任务类型：{n.attrs['task_type_label']}. "
            f"能解决的问题：{' '.join(n.attrs.get('problems_solved') or [])}. "
            f"机理：{n.attrs.get('mechanism','')}. "
            f"为什么有效：{n.attrs.get('why_it_works','')}.")
        rep["n_algorithms"] += 1
        rep["by_family"][fam] = rep["by_family"].get(fam, 0) + 1
        rep["by_task_type"][task] = rep["by_task_type"].get(task, 0) + 1
    if persist:
        graph.save("storage_cf/sciforge/batch10_final_graph.json")
        rep["index"] = build_index(graph)
        report = Path("storage_cf/sciforge/algorithm_reclassify_report.json")
        report.write_text(json.dumps(rep, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    return rep


# 结合「18 族机制分类 + 12 任务类型 + 问题/机理核心」设计的抽取步骤
EXTRACTION_PLAN = [
    {"step": 1, "name": "算法提及识别", "input": "论文 Markdown 全文",
     "method": "规则：正文章节、表格列头、参考文献里的模型名/基线名；"
               "候选去重并排除宿主论文方法名自引用",
     "output": "algorithm_candidates[{name, contexts[], tables[], ref_hints[]}]",
     "current_gap": "当前只从已有图节点取算法，正文候选召回未接入 pipeline"},
    {"step": 2, "name": "算法族判定", "input": "算法名 + architecture + 局部上下文",
     "method": "18 族别名投票 + 特异性优先级；未中才让 qwen 从封闭词表选并标 needs_review",
     "output": "family_id + confidence",
     "current_gap": "geometric_gnn 曾因别名重叠抢走 inverse_folding，已修但需别名冲突单测"},
    {"step": 3, "name": "原论文反查", "input": "算法名 + 全文 + References",
     "method": "名称附近 ±160 字符找 [n]，多位置投票；名称在标题里 → host_paper",
     "output": "source_paper{ref_no,title,arxiv_id,doi,year,votes}",
     "current_gap": "PDF 引用编号与 References 编号偏移，需人工复核 votes"},
    {"step": 4, "name": "按族模板抽机制属性", "input": "族 schema（专属字段）+ 局部上下文",
     "method": "按 family_id 动态生成 prompt，枚举字段封闭校验；局部上下文 ≤5000 字符",
     "output": "族专属字段（等变群/噪声调度/势函数形式/碱模型…）",
     "current_gap": "v2 精简时删掉了族专属字段，族信息目前只用于分类，未用于抽取"},
    {"step": 5, "name": "问题与机理分析填充", "input": "算法名 + 族 + 局部上下文",
     "method": "qwen 分析推断 problems_solved/mechanism/why_it_works；"
               "即使原文没谈也填，标 inference_basis 与 filled_by=llm_inference",
     "output": "问题/机理/为什么有效/适用场景/局限",
     "current_gap": "inference_basis 由 LLM 自报，未做逐字证据校验"},
    {"step": 6, "name": "任务类型与基线分组", "input": "族 + LLM 输出 + 白名单",
     "method": "族默认任务为强先验；通用 LM/机器学习势/逆折叠白名单纠正宿主论文污染；"
               "冲突记录并以族为准",
     "output": "task_type + baseline_group（同任务优先）",
     "current_gap": "族默认任务原不准，已依据全量推断结果校准"},
    {"step": 7, "name": "证据校验与入库", "input": "以上全部",
     "method": "枚举/列表/类型/族冲突/evidence 逐字校验；写图节点 + 重建 bge-m3 索引 + 报告",
     "output": "算法卡片 + 可检索索引 + 抽取报告",
     "current_gap": "全量推断是离线脚本，尚未挂进 run_pipeline"},
]

OPTIMIZATION_ADVICE = [
    {"priority": "P0", "issue": "抽取步骤 1/4/7 未进主流程",
     "advice": "把 algorithm_candidates 识别挂到 Stage2 之后，"
               "按族模板与问题推断作为 Stage2 的子模块，最后重建索引；"
               "与已挂载的 stage3_leaderboard 对称"},
    {"priority": "P0", "issue": "族专属字段被 v2 精简删除",
     "advice": "族信息应驱动抽取而非只驱动分类：恢复「族专属字段」为可选二级卡片，"
               "核心卡片仍只保留问题/机理，避免属性膨胀"},
    {"priority": "P1", "issue": "LLM 推断来源不可核验",
     "advice": "inference_basis 不能自报；对每条 problems/mechanism 要求 evidence 逐字短句，"
               "无逐字证据即强制标「由算法族推断」并降低检索权重"},
    {"priority": "P1", "issue": "关键词回退会选错论文",
     "advice": "引用式名称（Huang et al. RNN）改用「作者+年份」或参考文献条目匹配，"
               "不要用 RNN 这类通用词；已用族默认兜底"},
    {"priority": "P1", "issue": "引用编号偏移",
     "advice": "对 parse_references 结果做标题-算法名相似度校验，"
               "votes 相近时输出多候选让人工选 added_paper_id"},
    {"priority": "P2", "issue": "算法代码符号未回填",
     "advice": "Stage2 已有 REALIZED_BY/CodeFunction，把 code_symbols 作为"
               "「机理可验证证据」写回卡片，便于核对机制描述"},
    {"priority": "P2", "issue": "检索只有文本相似度",
     "advice": "检索结果按 task_type 与族做重排；同族/同任务加权，"
               "并把 comparable_baselines 直接作为对比实验候选输出"},
]
