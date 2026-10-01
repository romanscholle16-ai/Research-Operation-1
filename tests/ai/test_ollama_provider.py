"""Ollama adapter tests. The "unreachable server" tests make a REAL call
to the default localhost:11434 - this project confirmed no Ollama server
runs in this environment (see PHASE_HISTORY.md "Phase 5"), so that is a
genuine, reproducible failure path, not something that needs mocking.
Success-path tests mock `_http_post_json` since there is no real server
to return a canned response."""

import json
import urllib.error

import pytest

import app.ai.providers.ollama as ollama_mod
from app.ai.providers.ollama import OllamaAIProvider
from app.ai.provider import AIInvocationRequest, AIProviderResponseError, AIProviderTimeoutError, AIProviderUnavailableError


class _FakeContext:
    objective = "o"

    def summary(self, max_chars: int = 4000) -> str:
        return "ctx"


def _request() -> AIInvocationRequest:
    return AIInvocationRequest(session_id="s", iteration=0, purpose="propose_experiments", context=_FakeContext())


def test_capabilities_declared() -> None:
    provider = OllamaAIProvider()
    assert provider.capabilities.local_offline
    assert provider.capabilities.structured_output
    assert not provider.capabilities.tool_calling
    assert provider.is_mock is False


def test_real_unreachable_server_raises_unavailable() -> None:
    """No mocking - this is the actual, confirmed-unreachable default
    endpoint for this environment."""
    provider = OllamaAIProvider(base_url="http://localhost:11434", timeout=2.0)
    with pytest.raises(AIProviderUnavailableError):
        provider.invoke(_request())


def test_successful_invocation_parses_decision_and_token_counts(monkeypatch) -> None:
    canned = {
        "message": {
            "content": json.dumps(
                {"objective": "o", "hypothesis": "h", "reasoning_summary": "r", "requested_experiments": []}
            )
        },
        "done": True,
        "prompt_eval_count": 200,
        "eval_count": 40,
    }
    monkeypatch.setattr(ollama_mod, "_http_post_json", lambda *a, **k: canned)

    provider = OllamaAIProvider()
    response = provider.invoke(_request())

    assert response.decision.hypothesis == "h"
    assert response.input_tokens == 200
    assert response.output_tokens == 40
    assert response.total_tokens == 240
    assert response.provider_name == "ollama"


def test_requests_json_format(monkeypatch) -> None:
    captured = {}

    def fake_post(url, payload, timeout):
        captured["payload"] = payload
        return {"message": {"content": json.dumps({"objective": "o", "hypothesis": "h", "reasoning_summary": "r"})}}

    monkeypatch.setattr(ollama_mod, "_http_post_json", fake_post)
    OllamaAIProvider().invoke(_request())
    assert captured["payload"]["format"] == "json"


def test_non_json_content_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        ollama_mod, "_http_post_json", lambda *a, **k: {"message": {"content": "not json at all"}}
    )
    with pytest.raises(AIProviderResponseError):
        OllamaAIProvider().invoke(_request())


def test_missing_message_content_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(ollama_mod, "_http_post_json", lambda *a, **k: {"message": {}})
    with pytest.raises(AIProviderResponseError):
        OllamaAIProvider().invoke(_request())


def test_timeout_is_mapped(monkeypatch) -> None:
    def fake_post(*a, **k):
        raise TimeoutError("timed out")

    monkeypatch.setattr(ollama_mod, "_http_post_json", fake_post)
    with pytest.raises(AIProviderTimeoutError):
        OllamaAIProvider().invoke(_request())


def test_connection_refused_is_mapped_to_unavailable(monkeypatch) -> None:
    def fake_post(*a, **k):
        raise urllib.error.URLError(ConnectionRefusedError())

    monkeypatch.setattr(ollama_mod, "_http_post_json", fake_post)
    with pytest.raises(AIProviderUnavailableError):
        OllamaAIProvider().invoke(_request())
