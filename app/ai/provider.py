"""AI-provider abstraction (Phase 4 brief section 5; extended Phase 5
sections 9-11/17). Nothing in this package or `app/ai/agent.py`
hardcodes Claude, Anthropic, or any other specific vendor - an
`AIProvider` is just something that turns a `ResearchContext` into a
`ResearchDecision`. `app/ai/router.py`'s `AIProviderRouter` itself
implements this same interface, so `ResearchAgent` never needs to know
whether it's talking to one provider or a router trying several -
that's the concrete mechanism behind "ResearchAgent is unaware of
provider identity."

Error taxonomy: every provider adapter must translate its own
vendor-specific failures (HTTP status codes, SDK exceptions, timeouts)
into one of these, never let a raw exception escape `invoke()`.
`ResearchAgent` and `AIProviderRouter` only ever catch `AIProviderError`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ai.context import ResearchContext
    from app.ai.decision import ResearchDecision


class AIProviderError(Exception):
    """Base class for provider failures. Callers (ResearchAgent,
    AIProviderRouter) catch this specifically - never a bare Exception -
    so a provider bug can't be mistaken for, e.g., an experiment failure.
    """


class AIProviderTimeoutError(AIProviderError):
    pass


class AIProviderResponseError(AIProviderError):
    """The provider returned something that isn't a usable ResearchDecision -
    malformed JSON, a missing required field, or a type mismatch. Raised
    by the shared parser (providers/structured_output.py) as well as by
    individual adapters."""


class AIProviderAuthError(AIProviderError):
    """Authentication/authorization failure (bad or missing API key)."""


class AIProviderRateLimitError(AIProviderError):
    """The provider rejected the request due to rate limiting or quota."""


class AIProviderUnavailableError(AIProviderError):
    """The provider could not be reached at all (network error, DNS
    failure, connection refused, 5xx) - as opposed to reaching it and
    getting a well-formed rejection."""


@dataclass(frozen=True)
class ProviderCapabilities:
    """What a provider can actually do (Phase 5 brief section 17). No
    capability here is mandatory for a provider to be usable - a
    provider that lacks `token_usage_reporting`, for instance, simply
    leaves those `AIInvocationResponse` fields `None`."""

    structured_output: bool = False
    tool_calling: bool = False
    token_usage_reporting: bool = False
    streaming: bool = False
    model_selection: bool = False
    configurable_temperature: bool = False
    local_offline: bool = False


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

    # Usage/cost (Phase 5 brief section 16) - None where the provider
    # doesn't expose a figure; never estimated/invented.
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost: float | None = None

    # Diagnostics (Phase 5 brief section 15).
    request_id: str | None = None
    response_id: str | None = None

    # Populated by AIProviderRouter when a fallback actually occurred -
    # the ordered list of provider names tried before this one succeeded.
    # Empty tuple means "served directly, no fallback happened".
    fallback_chain: tuple[str, ...] = field(default_factory=tuple)


class AIProvider(ABC):
    provider_name: str = "unnamed_provider"
    model_name: str = "unnamed_model"

    # True only for providers that don't call a real model (MockAIProvider
    # and test doubles). AIProviderRouter uses this to refuse a silent
    # fallback onto a mock unless explicitly configured to allow it.
    is_mock: bool = False

    capabilities: ProviderCapabilities = ProviderCapabilities()

    @abstractmethod
    def invoke(self, request: AIInvocationRequest) -> AIInvocationResponse:
        """Return a decision for this request, or raise an `AIProviderError`
        subclass. Must never raise anything else on a handled failure -
        ResearchAgent only catches AIProviderError. Must never include a
        secret (API key, token) in any exception message it raises."""
        raise NotImplementedError
