"""Deterministic mock AI provider for the web-research workflow - same
role and same "scripted by iteration index" pattern as
`app.ai.providers.mock.MockAIProvider`, just producing `WebResearchDecision`
instead of `ResearchDecision`. Reuses the generic `AIProvider`/
`AIInvocationRequest`/`AIInvocationResponse` plumbing from `app.ai.provider`
unchanged - that interface was always generic ("turn a context into a
decision"), so no new provider abstraction was needed for this phase.
"""

from __future__ import annotations

from app.ai.provider import AIInvocationRequest, AIInvocationResponse, AIProvider, ProviderCapabilities
from app.research.decision import ResearchAction, WebResearchDecision


class MockWebResearchProvider(AIProvider):
    is_mock = True
    capabilities = ProviderCapabilities(structured_output=True, local_offline=True)

    def __init__(
        self,
        script: dict[int, WebResearchDecision],
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
            decision = WebResearchDecision(
                objective=request.context.objective,
                reasoning_summary="mock provider's script has no entry for this iteration",
                action=ResearchAction.STOP,
                stopping_reason="script_exhausted",
            )
        return AIInvocationResponse(
            decision=decision,
            provider_name=self.provider_name,
            model_name=self.model_name,
            raw_summary=f"mock web-research decision for iteration {request.iteration}: {decision.action.value}",
        )
