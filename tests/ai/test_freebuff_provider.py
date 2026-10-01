"""FreebuffAIProvider is a structural placeholder only (see its module
docstring) - these tests verify it is HONEST about that, not that it
works."""

import pytest

from app.ai.providers.freebuff import FreebuffAIProvider
from app.ai.provider import AIInvocationRequest, AIProviderUnavailableError


class _FakeContext:
    objective = "o"

    def summary(self, max_chars: int = 2000) -> str:
        return "ctx"


def test_freebuff_is_registered_as_a_real_ai_provider_subclass() -> None:
    from app.ai.provider import AIProvider

    assert issubclass(FreebuffAIProvider, AIProvider)


def test_freebuff_is_not_marked_as_mock() -> None:
    # It is a stub, not a fake-but-functional test double - is_mock
    # gates router fallback behavior and must not misrepresent this.
    assert FreebuffAIProvider().is_mock is False


def test_freebuff_invoke_always_raises_and_says_why() -> None:
    provider = FreebuffAIProvider(api_key="whatever")
    request = AIInvocationRequest(session_id="s", iteration=0, purpose="propose_experiments", context=_FakeContext())
    with pytest.raises(AIProviderUnavailableError, match="placeholder"):
        provider.invoke(request)


def test_freebuff_claims_no_capabilities_it_has_not_verified() -> None:
    caps = FreebuffAIProvider().capabilities
    assert caps.structured_output is False
    assert caps.tool_calling is False
    assert caps.token_usage_reporting is False


def test_freebuff_is_compatible_with_research_agent_even_though_it_always_fails(database) -> None:
    from app.ai.agent import ResearchAgent
    from app.ai.limits import ResearchLimits, StoppingReason
    from app.ai.session import SessionStatus
    from tests.ai.conftest import make_catalog

    agent = ResearchAgent(database, FreebuffAIProvider(), make_catalog(), ResearchLimits())
    record = agent.run("o")  # must not raise

    assert record.status is SessionStatus.FAILED
    assert record.stopping_reason == StoppingReason.PROVIDER_ERROR.value
