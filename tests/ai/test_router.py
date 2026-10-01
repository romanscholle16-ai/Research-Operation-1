import pytest

from app.ai.decision import ResearchDecision
from app.ai.provider import AIInvocationRequest, AIInvocationResponse, AIProvider, AIProviderError
from app.ai.providers.mock import AlwaysFailingAIProvider, MockAIProvider
from app.ai.router import AIProviderRouter, ProviderConfigurationError, build_provider


class _FakeRealProvider(AIProvider):
    """A non-mock AIProvider test double - distinct from MockAIProvider
    specifically so fallback tests can exercise "real provider A fails,
    real provider B serves it" without the mock-fallback gate kicking in."""

    is_mock = False

    def __init__(self, hypothesis: str, *, name: str = "fake_real") -> None:
        self.provider_name = name
        self.model_name = "fake-real-v1"
        self._hypothesis = hypothesis

    def invoke(self, request: AIInvocationRequest) -> AIInvocationResponse:
        return AIInvocationResponse(
            decision=ResearchDecision(objective="o", hypothesis=self._hypothesis, reasoning_summary="r"),
            provider_name=self.provider_name,
            model_name=self.model_name,
        )


class _FakeContext:
    objective = "o"

    def summary(self, max_chars: int = 2000) -> str:
        return "ctx"


def _request() -> AIInvocationRequest:
    return AIInvocationRequest(session_id="s", iteration=0, purpose="propose_experiments", context=_FakeContext())


def _decision_provider(hypothesis: str = "h") -> MockAIProvider:
    return MockAIProvider({0: ResearchDecision(objective="o", hypothesis=hypothesis, reasoning_summary="r")})


def test_router_requires_at_least_one_provider() -> None:
    with pytest.raises(ProviderConfigurationError):
        AIProviderRouter([])


def test_router_serves_from_primary_without_touching_fallback() -> None:
    primary = _decision_provider("from primary")
    fallback_invoked = {"called": False}

    class SpyFallback(MockAIProvider):
        def invoke(self, request):
            fallback_invoked["called"] = True
            return super().invoke(request)

    router = AIProviderRouter([primary, SpyFallback({})])
    response = router.invoke(_request())

    assert response.decision.hypothesis == "from primary"
    assert fallback_invoked["called"] is False
    assert response.fallback_chain == ()


def test_router_falls_back_to_a_second_real_provider_on_failure() -> None:
    router = AIProviderRouter(
        [AlwaysFailingAIProvider(), _FakeRealProvider("from fallback", name="fake_real_2")]
    )
    response = router.invoke(_request())
    assert response.decision.hypothesis == "from fallback"
    assert response.fallback_chain == ("always_failing_mock", "fake_real_2")


def test_router_does_not_silently_fall_back_to_mock_by_default() -> None:
    router = AIProviderRouter([AlwaysFailingAIProvider(), MockAIProvider({})], allow_mock_fallback=False)
    with pytest.raises(AIProviderError):
        router.invoke(_request())


def test_router_falls_back_to_mock_only_when_explicitly_allowed() -> None:
    router = AIProviderRouter([AlwaysFailingAIProvider(), MockAIProvider({0: ResearchDecision(objective="o", hypothesis="mock saved it", reasoning_summary="r")})], allow_mock_fallback=True)
    response = router.invoke(_request())
    assert response.decision.hypothesis == "mock saved it"
    assert response.fallback_chain == ("always_failing_mock", "mock")


def test_mock_as_primary_is_never_gated_by_allow_mock_fallback() -> None:
    # Explicitly choosing mock as your ONLY/primary provider is fine even
    # with allow_mock_fallback=False - that gate only applies to FALLBACK
    # positions, not an intentional primary selection.
    router = AIProviderRouter([_decision_provider("primary mock")], allow_mock_fallback=False)
    response = router.invoke(_request())
    assert response.decision.hypothesis == "primary mock"


def test_router_raises_when_every_provider_fails() -> None:
    router = AIProviderRouter([AlwaysFailingAIProvider(), AlwaysFailingAIProvider()])
    with pytest.raises(AIProviderError):
        router.invoke(_request())


def test_router_provider_name_reflects_the_chain() -> None:
    router = AIProviderRouter([_decision_provider(), AlwaysFailingAIProvider()])
    assert router.provider_name == "router(mock->always_failing_mock)"


def test_build_provider_rejects_unknown_name() -> None:
    with pytest.raises(ProviderConfigurationError):
        build_provider("totally-not-a-provider", settings=None)


def test_build_provider_mock_does_not_require_settings() -> None:
    provider = build_provider("mock", settings=None)
    assert isinstance(provider, MockAIProvider)
