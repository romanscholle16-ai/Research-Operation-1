"""AI research layer.

The AI is responsible for reasoning -> experiment proposal -> result
interpretation -> next experiment proposal. It never computes financial
results and never calls `app.backtesting.run_backtest()` directly -
every proposed experiment goes through Phase 3's `CampaignRunner`/
`ExperimentRunner`, unchanged. Which actual AI backend serves a session
(a real Claude/Ollama/Freebuff call, or the deterministic mock) is a
`router.py`-level configuration concern - `ResearchAgent` only ever
depends on the `AIProvider` interface. See ARCHITECTURE.md "Phase 4 - AI
Research Layer" and "Phase 5 - Real AI Providers + Provider Portability"
for the full design.
"""

from app.ai.agent import ResearchAgent
from app.ai.catalog import ResearchCatalog
from app.ai.context import ResearchContext, build_research_context
from app.ai.decision import ExperimentProposal, ResearchDecision
from app.ai.limits import ResearchLimits, StoppingReason
from app.ai.policy import RESEARCH_POLICY
from app.ai.provider import (
    AIInvocationRequest,
    AIInvocationResponse,
    AIProvider,
    AIProviderAuthError,
    AIProviderError,
    AIProviderRateLimitError,
    AIProviderResponseError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
    ProviderCapabilities,
)
from app.ai.router import AIProviderRouter, ProviderConfigurationError, build_provider, build_router_from_settings
from app.ai.session import ResearchSessionRecord, SessionStatus
from app.ai.validation import ProposalValidationError, validate_proposal

__all__ = [
    "AIInvocationRequest",
    "AIInvocationResponse",
    "AIProvider",
    "AIProviderAuthError",
    "AIProviderError",
    "AIProviderRateLimitError",
    "AIProviderResponseError",
    "AIProviderRouter",
    "AIProviderTimeoutError",
    "AIProviderUnavailableError",
    "ExperimentProposal",
    "ProposalValidationError",
    "ProviderCapabilities",
    "ProviderConfigurationError",
    "RESEARCH_POLICY",
    "ResearchAgent",
    "ResearchCatalog",
    "ResearchContext",
    "ResearchDecision",
    "ResearchLimits",
    "ResearchSessionRecord",
    "SessionStatus",
    "StoppingReason",
    "build_provider",
    "build_research_context",
    "build_router_from_settings",
    "validate_proposal",
]
