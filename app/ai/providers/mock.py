"""Deterministic mock AI provider (Phase 4 brief section 17). Lets the
whole research layer - agent, validation, translation, CampaignRunner,
the deterministic engine, persistence - be tested end to end without
Claude, Freebuff, Ollama, internet, or an API key.

Follows the same "scripted by iteration index" pattern as
`ScriptedStrategy` (Phase 2) and `ExperimentProposal` catalogs (Phase 3):
predictable, auditable, and immediately familiar to anyone who has read
the rest of this codebase.
"""

from __future__ import annotations

from app.ai.decision import ResearchDecision
from app.ai.limits import StoppingReason
from app.ai.provider import AIInvocationRequest, AIInvocationResponse, AIProvider, AIProviderError


class MockAIProvider(AIProvider):
    def __init__(
        self,
        script: dict[int, ResearchDecision],
        *,
        provider_name: str = "mock",
        model_name: str = "mock-deterministic-v1",
    ) -> None:
        self.script = script
        self.provider_name = provider_name
        self.model_name = model_name
        self.invocation_count = 0

    def invoke(self, request: AIInvocationRequest) -> AIInvocationResponse:
        self.invocation_count += 1
        decision = self.script.get(request.iteration)
        if decision is None:
            decision = ResearchDecision(
                objective=request.context.objective,
                hypothesis="no more scripted decisions",
                reasoning_summary="mock provider's script has no entry for this iteration",
                requested_experiments=(),
                stopping_reason=StoppingReason.AI_REQUESTED_STOP.value,
            )
        return AIInvocationResponse(
            decision=decision,
            provider_name=self.provider_name,
            model_name=self.model_name,
            raw_summary=f"mock decision for iteration {request.iteration}: {decision.hypothesis!r}",
        )


class AlwaysFailingAIProvider(AIProvider):
    """Deterministically fails every invocation - for testing
    AIProviderError handling in ResearchAgent."""

    provider_name = "always_failing_mock"
    model_name = "n/a"

    def invoke(self, request: AIInvocationRequest) -> AIInvocationResponse:
        raise AIProviderError("mock provider configured to always fail")
