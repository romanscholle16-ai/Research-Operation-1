"""AI research layer.

The AI is responsible for reasoning -> experiment proposal -> result
interpretation -> next experiment proposal. It never computes financial
results and never calls `app.backtesting.run_backtest()` directly -
every proposed experiment goes through Phase 3's `CampaignRunner`/
`ExperimentRunner`, unchanged. See ARCHITECTURE.md "Phase 4 - AI
Research Layer" for the full design.
"""

from app.ai.agent import ResearchAgent
from app.ai.catalog import ResearchCatalog
from app.ai.context import ResearchContext, build_research_context
from app.ai.decision import ExperimentProposal, ResearchDecision
from app.ai.limits import ResearchLimits, StoppingReason
from app.ai.provider import (
    AIInvocationRequest,
    AIInvocationResponse,
    AIProvider,
    AIProviderError,
    AIProviderResponseError,
    AIProviderTimeoutError,
)
from app.ai.session import ResearchSessionRecord, SessionStatus
from app.ai.validation import ProposalValidationError, validate_proposal

__all__ = [
    "AIInvocationRequest",
    "AIInvocationResponse",
    "AIProvider",
    "AIProviderError",
    "AIProviderResponseError",
    "AIProviderTimeoutError",
    "ExperimentProposal",
    "ProposalValidationError",
    "ResearchAgent",
    "ResearchCatalog",
    "ResearchContext",
    "ResearchDecision",
    "ResearchLimits",
    "ResearchSessionRecord",
    "SessionStatus",
    "StoppingReason",
    "build_research_context",
    "validate_proposal",
]
