"""兼容 shim（已归档）：实现见 ``capfactory.legacy.po_mapper``。"""
from ..legacy.po_mapper import *  # noqa: F401,F403
from ..legacy.po_mapper import capability_to_po, metric_profile_to_po, po_to_capability  # noqa: F401

__all__ = ["capability_to_po", "metric_profile_to_po", "po_to_capability"]
