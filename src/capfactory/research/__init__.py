"""研究分析层：覆盖度、缺口、方向建议。"""

from .advisor import ResearchAdvisor  # noqa: F401
from .gaps import CoverageAnalyzer, NeedCoverage  # noqa: F401

__all__ = ["ResearchAdvisor", "CoverageAnalyzer", "NeedCoverage"]
