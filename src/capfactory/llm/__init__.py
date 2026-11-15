"""LLM 层：客户端与多智能体。"""

from .agents import (  # noqa: F401
    AdvisorAgent,
    BaseAgent,
    CoderAgent,
    CriticAgent,
    PlannerAgent,
    ReaderAgent,
    RepairAgent,
    template_solution,
)
from .client import (  # noqa: F401
    LLMClient,
    LLMError,
    LLMResponse,
    MockLLMClient,
    OfflineError,
    get_client,
    set_client,
)

__all__ = [
    "AdvisorAgent",
    "BaseAgent",
    "CoderAgent",
    "CriticAgent",
    "LLMClient",
    "LLMError",
    "LLMResponse",
    "MockLLMClient",
    "OfflineError",
    "PlannerAgent",
    "ReaderAgent",
    "RepairAgent",
    "get_client",
    "set_client",
    "template_solution",
]
