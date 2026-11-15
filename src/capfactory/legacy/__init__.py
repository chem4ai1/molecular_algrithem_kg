"""旧实现归档层（V1 / 迭代期模块）。

目的：把「后续改造不再使用、但现有测试与 Web 仍依赖」的旧实现集中到一个
专门目录，新代码统一走 ``capfactory.ontology`` / ``capfactory.llm.backends``
/ ``capfactory.utils.parse_llm_json``，避免同名与职责冲突。

物理移动的文件在原位置保留**兼容 shim**（转发导入），所以 359 个测试与
45 项 Web 冒烟不会因归档而中断。
"""
from __future__ import annotations

LEGACY_MODULES = {
    "eval_extraction": {
        "was": "capfactory/kbpipe/eval.py",
        "why": "free/schema 对照评估脚本，非生产抽取链路",
        "shim": "capfactory/kbpipe/eval.py",
        "replacement": "capfactory/ontology/prompts.py + kbpipe/extractor.py",
    },
    "po_mapper": {
        "was": "capfactory/po/mapper.py",
        "why": "V1 Capability ⇄ PO 双向映射，V2 不再需要",
        "shim": "capfactory/po/mapper.py",
        "replacement": "capfactory/ontology/instantiate.py",
    },
}

# 仅登记、尚未物理移动（有更多依赖，需按迁移表逐个确认）
PENDING = (
    "capfactory/vector/indexer.py",
    "capfactory/po/semantics.py",
    "capfactory/po/keywords.py + po/taxonomy.py",
    "capfactory/ingest/pdf.py（PyMuPDF 单栏解析，仍被双栏分流使用）",
)


def legacy_report() -> dict:
    return {"archived": LEGACY_MODULES, "pending": list(PENDING),
            "policy": "收敛+shim，不做破坏性删除；删除前必须全量测试+冒烟通过"}
