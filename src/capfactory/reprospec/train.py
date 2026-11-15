"""原论文模型训练复现（``effort="full"``）的可行性探测与训练计划生成。

**与 lite 的本质区别**：现有 ``REPRO_SCRIPT.py`` 复现的是「评测协议重算」
（从论文表格原始行重算榜单），不是训练模型。原论文训练复现需要
数据、依赖、权重、GPU 与原始训练入口，缺任何一项都不能声称复现成功。

本模块**不执行训练**，只做三件可验证的事：

1. 探测环境（GPU / torch / numpy / rdkit / 数据目录），明确列出阻塞项；
2. 从 ``ReproSpec`` 编译 ``TRAIN_PLAN.json``（数据布局、镜像、阶段阶梯、
   seed、checkpoint、配置字段、验收口径）；
3. 写 ``TRAIN_FEASIBILITY.json``，给出 ``executable`` 判断与修复步骤。

完整设计见 ``capfactory/md/FULL_TRAIN_REPRODUCTION_DESIGN.md``。

    from capfactory.reprospec.train import write_train_feasibility
    rep = write_train_feasibility(spec, graph, "storage_cf/repro_runs/2411.06608",
                                  data_root="/home/zengshuxin/data")
    rep["executable"], rep["blocking"]
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_DATA_ROOT = "/home/zengshuxin/data"

# 训练必须从原仓库/论文里确定的字段，缺一项就不得启动 full
REQUIRED_CONFIG_FIELDS = (
    "repo_url", "commit", "entrypoint", "config_path", "seed",
    "batch_size", "epochs", "optimizer", "learning_rate", "scheduler",
    "amp", "split", "checkpoint_path", "metric_names",
)

# 数据集镜像（只作为建议，本模块不发起下载）
DATA_MIRRORS = (
    {"name": "HuggingFace 官方", "hint": "huggingface-cli download --repo-type dataset"},
    {"name": "HF 镜像站", "hint": "HF_ENDPOINT=https://hf-mirror.com"},
    {"name": "官方原始源", "hint": "论文/仓库 README 给出的原始下载地址"},
    {"name": "本地缓存", "hint": "放到 DATA_ROOT/<arxiv>/<benchmark>/ 并登记 sha256"},
)


def _gpu_info() -> List[Dict[str, str]]:
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.total,memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10, check=False)
    except Exception:  # noqa: BLE001
        return []
    if r.returncode != 0:
        return []
    out: List[Dict[str, str]] = []
    for line in (r.stdout or "").splitlines():
        parts = [x.strip() for x in line.split(",")]
        if len(parts) >= 4:
            out.append({"index": parts[0], "name": parts[1],
                        "memory_total_mib": parts[2],
                        "memory_used_mib": parts[3]})
    return out


def _torch_info() -> Dict[str, Any]:
    """在子进程里试 import torch：动态库不兼容时不能污染主进程。"""
    code = ("import json\n"
            "try:\n"
            "    import torch\n"
            "    print(json.dumps({'ok': True, 'version': torch.__version__, "
            "'cuda': bool(torch.cuda.is_available())}))\n"
            "except Exception as e:\n"
            "    print(json.dumps({'ok': False, "
            "'error': type(e).__name__ + ': ' + str(e)[:300]}))\n")
    try:
        r = subprocess.run([sys.executable, "-c", code],
                           capture_output=True, text=True, timeout=60,
                           check=False)
        return json.loads((r.stdout or "").strip().splitlines()[-1])
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _py_modules() -> Dict[str, bool]:
    import importlib.util
    return {m: importlib.util.find_spec(m) is not None
            for m in ("numpy", "pandas", "scipy", "rdkit", "torch",
                      "torch_geometric", "transformers")}


def _data_root_info(root: str | Path) -> Dict[str, Any]:
    p = Path(root)
    if not p.exists():
        return {"path": str(p), "exists": False, "n_files": 0, "bytes": 0,
                "top_level": []}
    n, size = 0, 0
    try:
        for f in p.rglob("*"):
            if f.is_file():
                n += 1
                size += f.stat().st_size
                if n >= 50000:
                    break
    except OSError:
        pass
    top = [x.name for x in sorted(p.iterdir())[:20]] if p.is_dir() else []
    return {"path": str(p), "exists": True, "n_files": n, "bytes": size,
            "top_level": top}


def probe_environment(data_root: str | Path = DEFAULT_DATA_ROOT) -> Dict[str, Any]:
    """只读环境探测；不做任何安装、下载或删除。"""
    gpus = _gpu_info()
    torch = _torch_info()
    mods = _py_modules()
    data = _data_root_info(data_root)
    return {
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "gpus": gpus, "n_gpus": len(gpus),
        "gpu_free": [g for g in gpus
                     if int(g["memory_used_mib"] or 0) < 4096],
        "torch": torch, "modules": mods, "data_root": data,
    }


def build_train_plan(spec: Any, graph: Any, *,
                     data_root: str | Path = DEFAULT_DATA_ROOT,
                     env: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """编译训练计划：数据来源、阶段阶梯、必填配置、验收口径。"""
    env = env or probe_environment(data_root)
    aid = spec.arxiv_id or str(spec.paper_id).split(":")[-1]
    root = Path(data_root) / aid
    datasets: List[Dict[str, Any]] = []
    for dc in (spec.data_contract or []):
        slug = str(dc.get("benchmark") or "").split(":")[-1].replace("/", "_")
        datasets.append({
            "benchmark": dc.get("benchmark"), "label": dc.get("label"),
            "declared_n_samples": dc.get("n_samples"),
            "declared_scale": dc.get("scale"),
            "input_form": dc.get("input_form"),
            "output_form": dc.get("output_form"),
            "target_dir": str(root / slug),
            "sha256": "",
            "status": "not_downloaded",
        })
    code_plan = spec.code_plan or {}
    blocking: List[str] = []
    if not env["torch"].get("ok"):
        blocking.append("torch 不可用：" + str(env["torch"].get("error", ""))[:180])
    if not env["gpus"]:
        blocking.append("未检测到可用 GPU")
    if not env["modules"].get("rdkit"):
        blocking.append("缺 rdkit（分子生成类论文必需）")
    if not code_plan.get("has_repo"):
        blocking.append("图中无 CodeRepository，缺原仓库与训练入口")
    if not any(d["status"] == "verified" for d in datasets):
        blocking.append("数据集尚未下载并校验 sha256")
    for f in REQUIRED_CONFIG_FIELDS:
        if not code_plan.get(f):
            blocking.append(f"训练配置未确认：{f}")
            break
    return {
        "paper_id": spec.paper_id, "arxiv_id": aid,
        "spec_hash": spec.spec_hash, "effort": "full",
        "executable": not blocking,
        "blocking": blocking,
        "repositories": code_plan.get("repositories") or [],
        "code_plan_strategy": code_plan.get("strategy") or "",
        "data_root": str(root), "datasets": datasets,
        "mirrors": [dict(x) for x in DATA_MIRRORS],
        "stages": [
            {"name": "smoke", "goal": "1 个 mini-batch 前向+反向，验证依赖/shape/显存",
             "samples": 8, "epochs": 1, "max_minutes": 10,
             "accept": "无 OOM / 无 shape 错误 / loss 有限"},
            {"name": "subset", "goal": "小子集完整训练 + 一次评测，验证收敛方向",
             "samples": 1000, "epochs": 1, "max_minutes": 120,
             "accept": "指标方向正确、日志与 seed 可复现"},
            {"name": "full", "goal": "论文设定全量训练",
             "samples": "论文设定", "epochs": "论文设定", "max_minutes": None,
             "accept": "主指标相对偏差 ≤ 5%，checkpoint sha 与双跑一致"},
        ],
        "required_config_fields": list(REQUIRED_CONFIG_FIELDS),
        "config": {},
        "reproducibility": {
            "seed": None, "deterministic": True, "cudnn_benchmark": False,
            "double_run": True,
            "artifacts": ["config.yaml", "train.log", "metrics.json",
                          "checkpoint.sha256", "env.lock"],
        },
        "acceptance": {
            "metric_tolerance": 0.05,
            "require_checkpoint_hash": True,
            "require_double_run_equal": True,
            "compare_against": "论文表格原始行 model_results（不是 LeaderboardEntry 期望值）",
        },
        "relation_to_ggr": (
            "full 是 R5 的真实训练执行器，替换 lite 的 REPRO_SCRIPT.py；"
            "R0–R4 规格编译、R6 逐 SAU 语义门与三哈希锚保持不变，"
            "新增 dataset_sha / ckpt_sha / seed 三项作为 ClaimAnchor 的第 4–6 个哈希。"),
        "note": "本计划不执行训练；blocking 清空并由人确认 config 后才可启动。",
    }


def write_train_feasibility(spec: Any, graph: Any,
                            out_dir: str | Path, *,
                            data_root: str | Path = DEFAULT_DATA_ROOT
                            ) -> Dict[str, Any]:
    """写 ``TRAIN_FEASIBILITY.json`` / ``TRAIN_PLAN.json``，返回可行性汇总。"""
    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)
    env = probe_environment(data_root)
    plan = build_train_plan(spec, graph, data_root=data_root, env=env)
    feasibility = {
        "paper_id": spec.paper_id, "arxiv_id": spec.arxiv_id,
        "spec_hash": spec.spec_hash, "effort": "full",
        "executable": plan["executable"], "blocking": plan["blocking"],
        "n_gpus": env["n_gpus"], "gpu_free": env["gpu_free"],
        "torch": env["torch"], "modules": env["modules"],
        "data_root": env["data_root"],
        "n_datasets": len(plan["datasets"]),
        "next_actions": [
            "新建隔离 venv/conda 并安装与 CUDA 驱动匹配的 PyTorch（修复 NCCL 符号）",
            "安装 rdkit / torch_geometric 等论文依赖并冻结 env.lock",
            "确认原仓库 commit 与训练入口，补全 TRAIN_PLAN.config 全部字段",
            "通过镜像下载数据集到 data_root/<arxiv>/<benchmark>/，登记 sha256",
            "先跑 smoke，再 subset，最后 full；每阶段写事件与三哈希",
        ],
        "files": ["TRAIN_FEASIBILITY.json", "TRAIN_PLAN.json"],
    }
    (p / "TRAIN_FEASIBILITY.json").write_text(
        json.dumps(feasibility, ensure_ascii=False, indent=2), encoding="utf-8")
    (p / "TRAIN_PLAN.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return feasibility
