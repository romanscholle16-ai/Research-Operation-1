"""Shared provider contract (Phase 5 brief section 21). Every provider
that can be instantiated in this test environment is run through the
same checks: valid invocation, structured response, provider metadata,
malformed response, provider failure, timeout/error normalization,
secret redaction (where applicable), and compatibility with
`ResearchAgent`. Real providers (Claude, Ollama) use mocked HTTP - no
network access or credentials are required for this suite.
"""

from __future__ import annotations

import json
import urllib.error

import pytest

import app.ai.providers.claude as claude_mod
import app.ai.providers.ollama as ollama_mod
from app.ai.decision import ResearchDecision
from app.ai.provider import AIInvocationRequest, AIProviderError, AIProviderResponseError
from app.ai.providers.claude import DECISION_TOOL_NAME, ClaudeAIProvider
from app.ai.providers.mock import MockAIProvider
from app.ai.providers.ollama import OllamaAIProvider

SECRET = "sk-ant-CONTRACT-TEST-SECRET"


class _FakeContext:
    objective = "contract test objective"

    def summary(self, max_chars: int = 4000) -> str:
        return "bounded contract-test context"


def _request() -> AIInvocationRequest:
    return AIInvocationRequest(session_id="s", iteration=0, purpose="propose_experiments", context=_FakeContext())


def _mock() -> MockAIProvider:
    return MockAIProvider({0: ResearchDecision(objective="o", hypothesis="h", reasoning_summary="r")})


def _claude_success(monkeypatch) -> ClaudeAIProvider:
    provider = ClaudeAIProvider(api_key=SECRET)
    body = {
        "id": "msg_1",
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "content": [
            {"type": "tool_use", "name": DECISION_TOOL_NAME, "input": {"objective": "o", "hypothesis": "h", "reasoning_summary": "r"}}
        ],
    }
    monkeypatch.setattr(claude_mod, "_http_post_json", lambda *a, **k: (200, body))
    return provider


def _claude_malformed(monkeypatch) -> ClaudeAIProvider:
    provider = ClaudeAIProvider(api_key=SECRET)
    monkeypatch.setattr(claude_mod, "_http_post_json", lambda *a, **k: (200, {"id": "x", "content": []}))
    return provider


def _claude_failure(monkeypatch) -> ClaudeAIProvider:
    provider = ClaudeAIProvider(api_key=SECRET)

    def fail(*a, **k):
        raise urllib.error.URLError("no network")

    monkeypatch.setattr(claude_mod, "_http_post_json", fail)
    return provider


def _ollama_success(monkeypatch) -> OllamaAIProvider:
    provider = OllamaAIProvider()
    canned = {"message": {"content": json.dumps({"objective": "o", "hypothesis": "h", "reasoning_summary": "r"})}}
    monkeypatch.setattr(ollama_mod, "_http_post_json", lambda *a, **k: canned)
    return provider


def _ollama_malformed(monkeypatch) -> OllamaAIProvider:
    provider = OllamaAIProvider()
    monkeypatch.setattr(ollama_mod, "_http_post_json", lambda *a, **k: {"message": {"content": "not json"}})
    return provider


def _ollama_failure(monkeypatch) -> OllamaAIProvider:
    provider = OllamaAIProvider()

    def fail(*a, **k):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(ollama_mod, "_http_post_json", fail)
    return provider


PROVIDERS = {
    "mock": {"success": lambda mp: _mock()},
    "claude": {"success": _claude_success, "malformed": _claude_malformed, "failure": _claude_failure},
    "ollama": {"success": _ollama_success, "malformed": _ollama_malformed, "failure": _ollama_failure},
}


@pytest.mark.parametrize("name", list(PROVIDERS.keys()))
def test_valid_invocation_returns_structured_response_with_metadata(monkeypatch, name: str) -> None:
    provider = PROVIDERS[name]["success"](monkeypatch)
    response = provider.invoke(_request())

    assert isinstance(response.decision, ResearchDecision)
    assert response.provider_name  # non-empty
    assert response.model_name  # non-empty


@pytest.mark.parametrize("name", ["claude", "ollama"])
def test_malformed_response_raises_response_error(monkeypatch, name: str) -> None:
    provider = PROVIDERS[name]["malformed"](monkeypatch)
    with pytest.raises(AIProviderResponseError):
        provider.invoke(_request())


@pytest.mark.parametrize("name", ["claude", "ollama"])
def test_provider_failure_is_normalized_to_an_ai_provider_error(monkeypatch, name: str) -> None:
    provider = PROVIDERS[name]["failure"](monkeypatch)
    with pytest.raises(AIProviderError):
        provider.invoke(_request())


def test_claude_secret_never_appears_in_a_failure_message(monkeypatch) -> None:
    provider = _claude_failure(monkeypatch)
    try:
        provider.invoke(_request())
        pytest.fail("expected an AIProviderError")
    except AIProviderError as exc:
        assert SECRET not in str(exc)


@pytest.mark.parametrize("name", list(PROVIDERS.keys()))
def test_provider_is_compatible_with_research_agent(monkeypatch, database, name: str) -> None:
    from app.ai.agent import ResearchAgent
    from app.ai.limits import ResearchLimits
    from tests.ai.conftest import make_catalog

    provider = PROVIDERS[name]["success"](monkeypatch)
    agent = ResearchAgent(database, provider, make_catalog(), ResearchLimits(max_iterations=1))

    record = agent.run("contract test objective")  # must not raise regardless of provider identity
    assert record.iteration >= 1
