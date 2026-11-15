"""D0–D10 领域与 A01–A18 算法族的关键词库（强/中/弱三级权重）.

设计要点：

* **三级权重**：``strong=1.0``（几乎决定性）、``medium=0.6``（语义相关）、
  ``weak=0.35``（弱共现，仅在同族其它词缺失时起作用）；
* **通用词与领域词分离**：``D0`` 的定义是「无生物/材料/化学关键词时的通用算法」，
  因此 D0 不靠关键词命中，而靠 **strong 领域得分为 0** 来判定（见 ``classify_domains``）；
* **可导出给 LLM**：``keyword_table()`` 输出结构化词表，可直接拼进抽取 prompt，
  让模型与规则共用同一套词面（避免「规则说 D5、模型说 D4」的漂移）；
* **冲突词允许跨类**：如 ``molecular dynamics`` 同时属 D10 与 A16、``agent`` 同属 D9 与 A14，
  分类是多标签而非互斥。
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Sequence, Tuple

WEIGHTS = {"strong": 1.0, "medium": 0.6, "weak": 0.35}
# 领域判定的下限：低于该分数视为「没有生物/材料/化学语境」，落 D0
DOMAIN_MIN_SCORE = 0.9

# ---------------------------------------------------------------------------
# 领域关键词（用户给定 + 同义词 / 缩写 / 方法名扩充）
# ---------------------------------------------------------------------------
DOMAIN_KEYWORDS: Dict[str, Dict[str, List[str]]] = {
    "D1": {
        "strong": ["de novo design", "de novo generation", "molecule generation",
                   "molecular generation", "molecular design", "chemical space",
                   "ligand generation", "generative chemistry", "virtual library",
                   "smiles generation", "graph generation", "hit generation"],
        "medium": ["generative design", "scaffold generation", "fragment growing",
                   "target-specific generation", "pocket2mol", "denovo"],
        "weak": ["from scratch", "novel molecules", "new chemical entities", "nce"],
    },
    "D2": {
        "strong": ["lead optimization", "multi-objective optimization", "molecular optimization",
                   "scaffold hopping", "hit-to-lead", "lead-like", "pareto front",
                   "activity cliff", "matched molecular pair", "mmp"],
        "medium": ["derivative design", "analog design", "potency optimization",
                   "admet optimization", "property optimization", "optimization campaign"],
        "weak": ["optimization", "campaign", "round of design", "iterative design"],
    },
    "D3": {
        "strong": ["structure-based drug design", "sbdd", "target-aware", "binding affinity",
                   "protein-ligand", "binding site", "pocket", "structure-based",
                   "pose prediction", "docking score"],
        "medium": ["docking", "pharmacophore", "interaction", "co-crystal", "apo", "holo",
                   "receptor", "molecular docking", "pose", "interface"],
        "weak": ["geometry", "complex", "ligand binding", "affinity"],
    },
    "D4": {
        "strong": ["admet", "property prediction", "toxicity prediction", "herg",
                   "drug-likeness", "blood-brain barrier", "cardiotoxicity",
                   "hepatotoxicity", "mutagenicity", "qsar", "qspr"],
        "medium": ["solubility", "permeability", "clearance", "half-life", "logp",
                   "lipinski", "bioavailability", "cyp", "dmpk", "safety", "toxicity",
                   "toxicophore", "pka", "bbb"],
        "weak": ["qed", "physicochemical", "property", "descriptor-based prediction"],
    },
    "D5": {
        "strong": ["peptide", "peptides", "antimicrobial peptide", "peptide design",
                   "peptide binder", "macrocyclic peptide", "cyclic peptide",
                   "stapled peptide", "cell-penetrating peptide", "amp", "amps",
                   "hemolytic", "haemolytic", "hemolysis", "haemolysis",
                   "host defense peptide", "minimum inhibitory concentration", "mic"],
        "medium": ["venom", "lipopeptide", "cpp", "defensin",
                   "bacteriocin", "lantibiotic", "conotoxin", "non-natural amino acid",
                   "nnaa", "protease stability", "serum stability", "immunogenicity",
                   "membrane selectivity", "epitope"],
        "weak": ["amino acid", "residue", "sequence-based", "peptidomimetic"],
    },
    "D6": {
        "strong": ["protein design", "antibody design", "inverse folding", "protein structure prediction",
                   "antibody", "nanobody", "vhh", "scfv", "sequence design",
                   "protein-protein interaction", "complex prediction"],
        "medium": ["protein", "rna", "folding", "epitope mapping", "tcr", "igg",
                   "enzyme design", "antigen", "paratope", "binder design",
                   "de novo protein"],
        "weak": ["residue-level", "backbone", "structure prediction"],
    },
    "D7": {
        "strong": ["retrosynthesis", "reaction prediction", "synthesizability",
                   "synthesis planning", "reaction condition", "forward reaction",
                   "yield prediction", "route design", "sascore"],
        "medium": ["reaction", "synthesis", "reagent", "catalyst", "protecting group",
                   "atom mapping", "reaction classification", "template-based",
                   "template-free", "reaction yield"],
        "weak": ["synthesize", "synthetic route", "chemistry route"],
    },
    "D8": {
        "strong": ["representation learning", "moleculenet", "benchmark suite",
                   "dataset curation", "molecular representation", "self-supervised pretraining",
                   "out-of-distribution benchmark", "data split"],
        "medium": ["benchmark", "dataset", "pretraining", "embedding", "evaluation protocol",
                   "negative sampling", "data augmentation", "molecular descriptor",
                   "leaderboard", "ablation"],
        "weak": ["representation", "feature", "corpus", "annotation"],
    },
    "D9": {
        "strong": ["ai for science", "ai4s", "llm agent", "autonomous lab",
                   "self-driving lab", "scientific discovery", "literature mining",
                   "hypothesis generation", "research agent", "closed-loop experiment"],
        "medium": ["agent", "autonomous", "hypothesis", "experiment planning",
                   "robot", "knowledge extraction", "paper mining", "copilot",
                   "scientific workflow", "multi-agent"],
        "weak": ["discovery", "automation", "tool use", "platform"],
    },
    "D10": {
        "strong": ["crystal structure prediction", "molecular dynamics", "force field",
                   "density functional theory", "dft", "material discovery",
                   "band gap", "phonon", "solid-state", "potential energy surface"],
        "medium": ["crystal", "material", "md", "conformation", "conformer",
                   "ensemble", "lattice", "polymer", "mof", "inorganic",
                   "catalyst surface", "thermodynamic", "free energy", "qm/mm",
                   "ab initio", "pes", "gcmc"],
        "weak": ["simulation", "physics", "energy", "atomistic"],
    },
}

# ---------------------------------------------------------------------------
# 算法族关键词
# ---------------------------------------------------------------------------
ALGO_KEYWORDS: Dict[str, Dict[str, List[str]]] = {
    "A01": {
        "strong": ["autoregressive", "language model", "llm", "gpt", "bert",
                   "decoder-only", "next-token", "instruction tuning", "in-context learning",
                   "chain-of-thought", "protein language model", "esm", "esm-2",
                   "molbert", "chemgpt", "molt5", "pairformer"],
        "medium": ["transformer", "prompt", "instruction", "token", "attention",
                   "sequence generation", "text generation", "few-shot", "masked language modeling",
                   "mlm", "foundation model"],
        "weak": ["language", "sequence model", "text"],
    },
    "A02": {
        "strong": ["variational autoencoder", "vae", "cvae", "bayesian flow network",
                   "beta-vae", "latent variable model", "elbo"],
        "medium": ["variational", "latent space", "latent", "autoencoder", "encoder-decoder",
                   "posterior collapse", "hierarchical vae", "vae-gan"],
        "weak": ["compression", "bottleneck"],
    },
    "A03": {
        "strong": ["generative adversarial", "gan", "wgan", "molgan", "discriminator"],
        "medium": ["adversarial", "adversarial training", "wasserstein"],
        "weak": ["generator", "critic"],
    },
    "A04": {
        "strong": ["diffusion model", "score-based", "ddpm", "ddim", "denoising diffusion",
                   "score matching", "latent diffusion", "consistency model",
                   "stochastic differential equation", "probability flow"],
        "medium": ["diffusion", "denoising", "denoiser", "noise schedule", "sde",
                   "rfdiffusion", "chroma", "diffsbdd", "diffdock", "targetdiff"],
        "weak": ["noise", "sampling steps", "reverse process"],
    },
    "A05": {
        "strong": ["flow matching", "normalizing flow", "stochastic interpolant",
                   "optimal transport", "continuous normalizing flow", "rectified flow",
                   "schrodinger bridge", "neural ode"],
        "medium": ["cnf", "ot-cfm", "flow-based", "flow model", "semla flow", "flowr"],
        "weak": ["transport", "interpolant", "ode solver"],
    },
    "A06": {
        "strong": ["gflownet", "generative flow network", "trajectory balance",
                   "detailed balance"],
        "medium": ["flow network", "gflow"],
        "weak": ["reward-proportional sampling"],
    },
    "A07": {
        "strong": ["reinforcement learning", "ppo", "dpo", "rlhf", "policy gradient",
                   "reward model", "preference optimization", "grpo", "actor-critic",
                   "inverse reinforcement learning"],
        "medium": ["reinforcement", "rl", "policy", "reward", "q-learning",
                   "reinforce", "exploration"],
        "weak": ["feedback loop", "agent policy"],
    },
    "A08": {
        "strong": ["bayesian optimization", "acquisition function", "gaussian process",
                   "active learning", "thompson sampling", "design of experiments",
                   "multi-fidelity optimization"],
        "medium": ["surrogate model", "acquisition", "bandit", "expected improvement",
                   "ucb", "hyperparameter optimization", "doe", "bayesopt"],
        "weak": ["search strategy", "query strategy"],
    },
    "A09": {
        "strong": ["graph neural network", "message passing", "graph transformer",
                   "gnn", "gcn", "gat", "mpnn", "gin", "graph attention"],
        "medium": ["graph convolution", "node embedding", "graph representation",
                   "relational learning", "neighborhood aggregation"],
        "weak": ["graph", "node", "edge feature"],
    },
    "A10": {
        "strong": ["equivariant", "se(3)", "e(3)", "geometric deep learning",
                   "e(3)-equivariant", "se(3)-equivariant", "invariant representation",
                   "tensor field network", "egnn", "schnet", "dimenet", "cormorant"],
        "medium": ["geometric", "equivariance", "invariant", "rotation equivariant",
                   "point cloud", "3d geometry", "atom-level"],
        "weak": ["symmetry", "coordinate", "spatial"],
    },
    "A11": {
        "strong": ["genetic algorithm", "evolutionary algorithm", "monte carlo tree search",
                   "mcts", "estimation of distribution", "island model", "nsga-ii",
                   "simulated annealing", "cma-es", "particle swarm"],
        "medium": ["evolutionary", "genetic", "tree search", "monte carlo", "beam search",
                   "fragment-based", "swarm", "differential evolution", "tabu search"],
        "weak": ["search", "mutation", "crossover", "population"],
    },
    "A12": {
        "strong": ["contrastive learning", "self-supervised", "masked autoencoder",
                   "simclr", "moco", "byol", "infonce", "masked language modeling",
                   "self-supervised pretraining"],
        "medium": ["contrastive", "pretraining", "pretrain", "masked", "self-supervision",
                   "mae", "cpc", "pretext task"],
        "weak": ["augmentation", "positive pair"],
    },
    "A13": {
        "strong": ["multimodal", "vision-language", "molecule-text", "cross-modal",
                   "image-text", "text-image", "clip", "multi-view"],
        "medium": ["multi-modal", "vision transformer", "vit", "text-image alignment",
                   "molecule caption", "image encoder"],
        "weak": ["image", "text pair", "modality fusion"],
    },
    "A14": {
        "strong": ["rag", "retrieval-augmented", "tool calling", "function calling",
                   "multi-agent", "react", "llm agent", "mcp", "autonomous agent"],
        "medium": ["agent", "tool use", "retrieval", "planner", "memory module",
                   "orchestration", "workflow engine", "pipeline orchestration"],
        "weak": ["tool", "workflow", "pipeline"],
    },
    "A15": {
        "strong": ["knowledge graph", "ontology", "symbolic reasoning", "rule-based reasoning",
                   "sparql", "owl", "rdf", "cypher", "triple store", "entity linking",
                   "relation extraction"],
        "medium": ["knowledge base", "symbolic", "semantic web", "graph database",
                   "logic rule", "expert system", "taxonomy", "schema"],
        "weak": ["rule", "triple", "knowledge"],
    },
    "A16": {
        "strong": ["physics-informed", "neural operator", "fourier neural operator",
                   "pinn", "fno", "deeponet", "molecular dynamics", "density functional theory",
                   "ab initio", "free energy perturbation"],
        "medium": ["simulation", "pde", "finite element", "fem", "cfd", "quantum chemistry",
                   "force field", "thermodynamic integration", "fep", "potential energy"],
        "weak": ["physics", "numerical solver", "equation"],
    },
    "A17": {
        "strong": ["uncertainty estimation", "calibration", "out-of-distribution",
                   "conformal prediction", "bayesian neural network", "deep ensemble",
                   "epistemic uncertainty", "aleatoric uncertainty", "expected calibration error"],
        "medium": ["uncertainty", "calibrated", "ood", "confidence", "abstention",
                   "reliability", "mc dropout", "ece"],
        "weak": ["error bar", "risk", "trust"],
    },
    "A18": {
        "strong": ["random forest", "support vector machine", "svm", "xgboost", "lightgbm",
                   "catboost", "extra trees", "gradient boosting", "logistic regression",
                   "decision tree", "molecular fingerprint", "ecfp", "maccs", "morgan",
                   "rdkit descriptor"],
        "medium": ["descriptor", "fingerprint", "classical machine learning", "knn",
                   "naive bayes", "ridge", "lasso", "elasticnet", "pls", "pca",
                   "feature selection", "rfe", "stacking", "ensemble learning"],
        "weak": ["baseline", "statistical model", "regression", "classifier"],
    },
}


def _pattern(word: str) -> str:
    """普通词 → 带词边界与可选复数的正则；``re:`` 前缀原样使用。"""
    if word.startswith("re:"):
        return word[3:]
    esc = re.escape(word)
    # 仅对纯字母结尾加复数容忍，避免 SE(3) / QM/MM 等被破坏
    tail = r"(?:s|es)?" if re.search(r"[a-z]$", word) else ""
    return rf"(?<![a-z0-9]){esc}{tail}(?![a-z])"


def compile_rules(keywords: Dict[str, Dict[str, List[str]]]) -> Tuple[Tuple[str, str, float], ...]:
    """把强/中/弱三级词表编译为 ``(code, pattern, weight)`` 规则序列。"""
    rules: List[Tuple[str, str, float]] = []
    for level in ("strong", "medium", "weak"):
        weight = WEIGHTS[level]
        for code, groups in keywords.items():
            words = groups.get(level) or []
            if not words:
                continue
            rules.append((code, "|".join(_pattern(w) for w in words), weight))
    return tuple(rules)


# A09 的「可微分图指纹」家族：Paper 里 self-attention 式图指纹很常见，
# 单列关键词避免被 A18 的 fingerprint 抢走
ALGO_KEYWORDS["A09"]["strong"] = list(dict.fromkeys(
    ALGO_KEYWORDS["A09"]["strong"] + [
        "graph fingerprint", "neural fingerprint", "differentiable fingerprint",
        "graph embedding", "weisfeiler", "graph convolution", "graph network"]))

DOMAIN_RULES = compile_rules(DOMAIN_KEYWORDS)
ALGO_RULES = compile_rules(ALGO_KEYWORDS)


def keyword_table() -> Dict[str, Dict[str, Dict[str, List[str]]]]:
    """结构化关键词表，供 LLM prompt 与前端展示。"""
    return {"domains": DOMAIN_KEYWORDS, "algorithms": ALGO_KEYWORDS}


def keyword_stats() -> Dict[str, Dict[str, int]]:
    def count(kw: Dict[str, Dict[str, List[str]]]) -> Dict[str, int]:
        return {level: sum(len(g.get(level) or []) for g in kw.values())
                for level in ("strong", "medium", "weak")}
    return {"domains": count(DOMAIN_KEYWORDS), "algorithms": count(ALGO_KEYWORDS)}


def all_domain_keywords() -> List[str]:
    out: List[str] = []
    for groups in DOMAIN_KEYWORDS.values():
        for words in groups.values():
            out.extend(words)
    return out
