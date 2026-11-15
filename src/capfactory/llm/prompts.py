"""LLM 提示词模板.

所有提示词都要求模型输出 **纯 JSON**，便于程序化解析与校验。
提示词控制在必要信息内，避免超长上下文导致免费模型截断。
"""

from __future__ import annotations

SYSTEM_ANALYST = (
    "You are a senior AI researcher and algorithm engineer in computational biology and "
    "drug discovery. You read papers precisely and never invent details that are not "
    "supported by the provided text. You always answer with strict JSON only."
)

SYSTEM_CRITIC = (
    "You are a rigorous reviewer. You verify whether each claimed algorithm capability is "
    "actually supported by the given text and is implementable standalone. "
    "Answer with strict JSON only."
)

SYSTEM_PLANNER = (
    "You are a machine-learning solution architect. You design faithful, minimal, runnable "
    "implementations of published algorithms. Answer with strict JSON only."
)

SYSTEM_CODER = (
    "You are an expert Python engineer. You write clean, self-contained, deterministic code "
    "with type hints and docstrings. You never add network calls, never hard-code absolute "
    "paths, and you follow the required function contract exactly."
)

SYSTEM_ADVISOR = (
    "You are a research strategy advisor for a peptide-drug company. You identify genuine "
    "research gaps from the evidence and propose feasible, high-impact directions. "
    "Answer with strict JSON only."
)


# ---------------------------------------------------------------------------
# 1. 论文理解 + 能力抽取
# ---------------------------------------------------------------------------
PAPER_EXTRACTION = """# Task
Read the paper material below and extract (a) its research context and (b) every
*algorithmic capability* that is concrete enough to be re-implemented in code.

# Paper
Title: {title}
Year: {year}
Abstract: {abstract}

Sections (truncated):
{sections}

{code_hint}

# Definitions
- research_object: what entity/system the paper studies (be specific, e.g. "antimicrobial peptides").
- background: the problem context and why it matters (1-3 sentences).
- progress: where this work sits in the field's progress (1-3 sentences).
- capability: a self-contained, implementable algorithm / representation / training strategy /
  screening procedure / evaluation protocol. NOT a vague idea, NOT a pure engineering detail.
  Each capability must be implementable as one standalone Python module.

# Output JSON schema (strict, no markdown)
{{
  "research_object": "...",
  "background": "...",
  "progress": "...",
  "contributions": ["..."],
  "limitations": ["..."],
  "datasets": [{{"name": "...", "size": "...", "labels": "..."}}],
  "metrics": ["..."],
  "capabilities": [
    {{
      "name": "concise standardized name",
      "category": "data|representation|model|training|screening|evaluation|pipeline",
      "task": "snake_case task id, e.g. peptide_toxicity_prediction",
      "summary": "one sentence",
      "method": "step-by-step algorithm: features, model, training, decision rule, key hyper-parameters",
      "inputs": [{{"name": "...", "dtype": "...", "shape": "...", "description": "..."}}],
      "outputs": [{{"name": "...", "dtype": "...", "shape": "...", "description": "..."}}],
      "metrics": [{{"name": "accuracy", "reported": 0.0, "dataset": "..."}}],
      "conditions": ["when this capability is applicable"],
      "constraints": ["limitations, failure modes, data requirements"],
      "dependencies": ["numpy", "scikit-learn", "..."],
      "evidence": [{{"quote": "verbatim sentence from the text", "locator": "Sec/Table"}}],
      "confidence": 0.0,
      "tags": ["..."]
    }}
  ]
}}

# Rules
1. 2-5 capabilities. Prefer fewer, higher-quality ones.
2. `evidence.quote` must be copied verbatim from the provided text; if you cannot quote it,
   do not claim it.
3. `method` must contain enough detail (feature formula, model type, hyper-parameters,
   threshold) that another engineer can re-implement without the paper.
4. Only report numbers that literally appear in the text.
5. Return JSON only."""


# ---------------------------------------------------------------------------
# 2. 批评者：证据核验
# ---------------------------------------------------------------------------
CRITIQUE = """# Task
For each candidate capability, judge whether it is (i) supported by the paper text and
(ii) implementable as a standalone Python module.

# Paper text (excerpt)
{text}

# Candidate capabilities
{candidates}

# Output JSON (strict)
{{"reviews": [{{"name": "...", "supported": true, "implementable": true,
  "confidence": 0.0, "issues": ["..."], "fix": "how to make it implementable"}}],
  "verdict": "accept|revise|reject"}}

Return JSON only."""


# ---------------------------------------------------------------------------
# 3. 方案规划（多候选）
# ---------------------------------------------------------------------------
PLANNING = """# Task
Design candidate implementation plans for the target capability. The generated code must
satisfy the interface contract below and must run offline on CPU with limited data.

# Target capability
{capability}

# Reference capabilities retrieved from the knowledge graph
{references}

# Interface contract (must be satisfied)
{contract}

# Available runtime
Python 3.11+, numpy, pandas, scikit-learn. NO network. NO GPU. Deterministic (fixed seed).

# Output JSON (strict)
{{"plans": [
  {{"name": "...", "approach": "...",
    "steps": ["..."], "libraries": ["numpy"],
    "rationale": "why this design is faithful to the paper",
    "risks": ["..."],
    "expected_metrics": {{"accuracy": 0.8}},
    "scores": {{"fidelity": 0.0, "feasibility": 0.0, "robustness": 0.0, "cost": 0.0}}}}
]}}

3 plans, from most faithful to most pragmatic. Scores in [0,1]. Return JSON only."""


# ---------------------------------------------------------------------------
# 4. 代码生成
# ---------------------------------------------------------------------------
CODE_GEN = """# Task
Write ONE self-contained Python module that implements the capability below and
satisfies the interface contract.

# Capability
{capability}

# Chosen plan
{plan}

# Interface contract (MANDATORY)
{contract}

# Reference code fragments from open-source implementations (for API/detail reference only,
# do NOT copy verbatim, do NOT import these repositories)
{code_refs}

# Hard requirements
1. Standard library + numpy + pandas + scikit-learn only. No network, no file writes outside
   the given paths, no `os.system`/`subprocess`/`eval`/`exec`.
2. Deterministic: fix all random seeds.
3. Must define exactly the functions in the contract, with matching signatures and return types.
4. Must not print anything at import time; `if __name__ == "__main__":` smoke test is allowed.
5. Handle edge cases: empty input, unknown characters, single sample, ties, single-class labels.
6. Docstrings for every public function; type hints everywhere.
7. Keep it under 250 lines.

# Output format
```python
<the full module code>
```"""


# ---------------------------------------------------------------------------
# 5. 代码修复
# ---------------------------------------------------------------------------
CODE_REPAIR = """# Task
The generated module failed. Fix it. Return the FULL corrected module.

# Capability
{capability}

# Interface contract
{contract}

# Current code
```python
{code}
```

# Failure information
Stage: {stage}
Error:
```
{error}
```

# Previously observed failure patterns for this capability
{lessons}

# Rules
- Keep the same public function signatures.
- Fix the root cause; do not weaken the required checks (do not stub outputs, do not return
  constant predictions).
- Standard library + numpy + pandas + scikit-learn only.
- Return the full module in a single ```python block."""


# ---------------------------------------------------------------------------
# 6. 研究方向建议
# ---------------------------------------------------------------------------
RESEARCH_ADVICE = """# Task
Act as a research strategy advisor for a company working on natural peptide therapeutics
(venom-derived peptides; anti-infective, analgesic, metabolic indications). Based on the
mined capability landscape and the company needs, propose concrete research directions that
lead to publishable AI papers AND usable drug-discovery capability.

# Company needs
{needs}

# Mined capability landscape (capability: maturity, task, constraints)
{landscape}

# Evidence: papers and their key findings
{papers}

# Output JSON (strict)
{{"directions": [
  {{"title": "...",
    "gap": "the specific unmet capability/evidence gap",
    "rationale": "why it matters scientifically and for the company",
    "supporting_capabilities": ["existing capability names"],
    "required_capabilities": ["capabilities that must be built"],
    "experiments": ["concrete experiment 1", "..."],
    "expected_impact": "...",
    "difficulty": "low|medium|high",
    "priority": 0.0,
    "references": ["paper titles"]}}
]}}

4-6 directions, ordered by priority (0-1). Ground every claim in the provided evidence.
Return JSON only."""
