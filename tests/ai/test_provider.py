import pytest

from app.ai.decision import ResearchDecision
from app.ai.limits import StoppingReason
from app.ai.provider import AIInvocationRequest, AIProviderError
from app.ai.providers.mock import AlwaysFailingAIProvider, MockAIProvider
from tests.ai.conftest import make_catalog


class _FakeContext:
    objective = "test objective"

    def summary(self, max_chars: int = 2000) -> str:
        return "fake context"


def _request(iteration: int = 0) -> AIInvocationRequest:
    return AIInvocationRequest(session_id="s1", iteration=iteration, purpose="propose_experiments", context=_FakeContext())


def test_mock_provider_returns_scripted_decision() -> None:
    decision = ResearchDecision(objective="o", hypothesis="h", reasoning_summary="r")
    provider = MockAIProvider({0: decision})
    response = provider.invoke(_request(0))
    assert response.decision is decision
    assert response.provider_name == "mock"
    assert response.model_name == "mock-deterministic-v1"


def test_mock_provider_tracks_invocation_count() -> None:
    provider = MockAIProvider({0: ResearchDecision(objective="o", hypothesis="h", reasoning_summary="r")})
    provider.invoke(_request(0))
    provider.invoke(_request(0))
    assert provider.invocation_count == 2


def test_mock_provider_unscripted_iteration_returns_stop_decision() -> None:
    provider = MockAIProvider({})
    response = provider.invoke(_request(5))
    assert response.decision.stopping_reason == StoppingReason.AI_REQUESTED_STOP.value
    assert response.decision.requested_experiments == ()


def test_mock_provider_is_deterministic() -> None:
    decision = ResearchDecision(objective="o", hypothesis="h", reasoning_summary="r")
    provider = MockAIProvider({3: decision})
    r1 = provider.invoke(_request(3))
    r2 = provider.invoke(_request(3))
    assert r1.decision is r2.decision is decision


def test_always_failing_provider_raises_provider_error() -> None:
    provider = AlwaysFailingAIProvider()
    with pytest.raises(AIProviderError):
        provider.invoke(_request(0))


def test_custom_provider_and_model_names() -> None:
    provider = MockAIProvider({}, provider_name="custom", model_name="custom-v2")
    response = provider.invoke(_request(0))
    assert response.provider_name == "custom"
    assert response.model_name == "custom-v2"
