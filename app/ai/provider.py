"""AI-provider abstraction (Phase 4 brief section 5). Nothing in this
package or `app/ai/agent.py` hardcodes Claude, Anthropic, or any other
specific vendor - an `AIProvider` is just something that turns a
`ResearchContext` into a `ResearchDecision`. Phase 5+ can add
Claude/Freebuff/Ollama-backed providers without touching this interface
or the agent; this phase ships the abstraction plus `MockAIProvider`
(providers/mock.py) as the only implementation, so the whole research
layer is testable without any real AI provider, API key, or network
access.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ai.context import ResearchContext
    from app.ai.decision import ResearchDecision


class AIProviderError(Exception):
    """Base class for provider failures. Callers (ResearchAgent) catch
    this specifically - never a bare Exception - so a provider bug can't
    be mistaken for, e.g., an experiment failure."""


class AIProviderTimeoutError(AIProviderError):
    pass


class AIProviderResponseError(AIProviderError):
    """The provider returned something that isn't a usable ResearchDecision."""


@dataclass(frozen=True)
class AIInvocationRequest:
    session_id: str
    iteration: int
    purpose: str  # e.g. "propose_experiments"
    context: "ResearchContext"


@dataclass(frozen=True)
class AIInvocationResponse:
    decision: "ResearchDecision"
    provider_name: str
    model_name: str
    raw_summary: str = ""  # bounded, human-readable - never the full raw prompt/response


class AIProvider(ABC):
    provider_name: str = "unnamed_provider"
    model_name: str = "unnamed_model"

    @abstractmethod
    def invoke(self, request: AIInvocationRequest) -> AIInvocationResponse:
        """Return a decision for this request, or raise an `AIProviderError`
        subclass. Must never raise anything else on a handled failure -
        ResearchAgent only catches AIProviderError."""
        raise NotImplementedError
