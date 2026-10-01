"""Claude adapter tests - all against a mocked HTTP layer
(`app.ai.providers.claude._http_post_json`), never a real network call.
No ANTHROPIC_API_KEY is required or used."""

import urllib.error

import pytest

import app.ai.providers.claude as claude_mod
from app.ai.providers.claude import DECISION_TOOL_NAME, ClaudeAIProvider
from app.ai.provider import (
    AIInvocationRequest,
    AIProviderAuthError,
    AIProviderRateLimitError,
    AIProviderResponseError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)

FAKE_API_KEY = "sk-ant-TEST-SECRET-VALUE"


class _FakeContext:
    objective = "find edge"

    def summary(self, max_chars: int = 4000) -> str:
        return "bounded context"


def _request(iteration: int = 0) -> AIInvocationRequest:
    return AIInvocationRequest(session_id="s", iteration=iteration, purpose="propose_experiments", context=_FakeContext())


class _FakeHTTPError(urllib.error.HTTPError):
    def __init__(self, code: int, body: bytes) -> None:
        self.code = code
        self._body = body
        super().__init__("https://api.anthropic.com/v1/messages", code, "error", {}, None)

    def read(self) -> bytes:  # type: ignore[override]
        return self._body


def _tool_use_body(decision_input: dict, *, usage=None, message_id: str = "msg_1") -> dict:
    return {
        "id": message_id,
        "stop_reason": "tool_use",
        "usage": usage or {"input_tokens": 100, "output_tokens": 50},
        "content": [{"type": "tool_use", "name": DECISION_TOOL_NAME, "input": decision_input}],
    }


@pytest.fixture
def provider() -> ClaudeAIProvider:
    return ClaudeAIProvider(api_key=FAKE_API_KEY)


def test_requires_non_empty_api_key() -> None:
    with pytest.raises(ValueError):
        ClaudeAIProvider(api_key="")


def test_capabilities_declared() -> None:
    provider = ClaudeAIProvider(api_key=FAKE_API_KEY)
    assert provider.capabilities.structured_output
    assert provider.capabilities.tool_calling
    assert provider.capabilities.token_usage_reporting
    assert not provider.capabilities.local_offline
    assert provider.is_mock is False


def test_successful_invocation_parses_decision_and_usage(monkeypatch, provider: ClaudeAIProvider) -> None:
    body = _tool_use_body(
        {"objective": "find edge", "hypothesis": "qty matters", "reasoning_summary": "r",
         "requested_experiments": [{"research_system": "parameter_explorer", "parameter_space": {"qty": [1.0, 2.0]}}]},
    )
    monkeypatch.setattr(claude_mod, "_http_post_json", lambda *a, **k: (200, body))

    response = provider.invoke(_request())

    assert response.decision.hypothesis == "qty matters"
    assert response.decision.requested_experiments[0].research_system == "parameter_explorer"
    assert response.input_tokens == 100
    assert response.output_tokens == 50
    assert response.total_tokens == 150
    assert response.response_id == "msg_1"
    assert response.provider_name == "claude"


def test_forces_tool_choice_to_the_decision_tool(monkeypatch, provider: ClaudeAIProvider) -> None:
    captured = {}

    def fake_post(url, headers, payload, timeout):
        captured["payload"] = payload
        captured["headers"] = headers
        return 200, _tool_use_body({"objective": "o", "hypothesis": "h", "reasoning_summary": "r"})

    monkeypatch.setattr(claude_mod, "_http_post_json", fake_post)
    provider.invoke(_request())

    assert captured["payload"]["tool_choice"] == {"type": "tool", "name": DECISION_TOOL_NAME}
    assert captured["headers"]["x-api-key"] == FAKE_API_KEY


def test_auth_error_is_mapped_and_key_is_redacted(monkeypatch, provider: ClaudeAIProvider) -> None:
    def fake_post(*a, **k):
        raise _FakeHTTPError(401, f"invalid x-api-key {FAKE_API_KEY} provided".encode())

    monkeypatch.setattr(claude_mod, "_http_post_json", fake_post)
    with pytest.raises(AIProviderAuthError) as excinfo:
        provider.invoke(_request())
    assert FAKE_API_KEY not in str(excinfo.value)


def test_rate_limit_error_is_mapped(monkeypatch, provider: ClaudeAIProvider) -> None:
    def fake_post(*a, **k):
        raise _FakeHTTPError(429, b"rate limited")

    monkeypatch.setattr(claude_mod, "_http_post_json", fake_post)
    with pytest.raises(AIProviderRateLimitError):
        provider.invoke(_request())


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_server_errors_are_mapped_to_unavailable(monkeypatch, provider: ClaudeAIProvider, status: int) -> None:
    def fake_post(*a, **k):
        raise _FakeHTTPError(status, b"server error")

    monkeypatch.setattr(claude_mod, "_http_post_json", fake_post)
    with pytest.raises(AIProviderUnavailableError):
        provider.invoke(_request())


def test_network_error_is_mapped_to_unavailable(monkeypatch, provider: ClaudeAIProvider) -> None:
    def fake_post(*a, **k):
        raise urllib.error.URLError("name resolution failed")

    monkeypatch.setattr(claude_mod, "_http_post_json", fake_post)
    with pytest.raises(AIProviderUnavailableError):
        provider.invoke(_request())


def test_timeout_is_mapped(monkeypatch, provider: ClaudeAIProvider) -> None:
    def fake_post(*a, **k):
        raise TimeoutError("timed out")

    monkeypatch.setattr(claude_mod, "_http_post_json", fake_post)
    with pytest.raises(AIProviderTimeoutError):
        provider.invoke(_request())


def test_missing_tool_use_block_is_rejected(monkeypatch, provider: ClaudeAIProvider) -> None:
    def fake_post(*a, **k):
        return 200, {"id": "msg_2", "content": [{"type": "text", "text": "I decided not to use the tool"}]}

    monkeypatch.setattr(claude_mod, "_http_post_json", fake_post)
    with pytest.raises(AIProviderResponseError):
        provider.invoke(_request())


def test_malformed_tool_input_is_rejected_not_silently_fixed(monkeypatch, provider: ClaudeAIProvider) -> None:
    def fake_post(*a, **k):
        return 200, _tool_use_body({"hypothesis": "missing objective and reasoning_summary"})

    monkeypatch.setattr(claude_mod, "_http_post_json", fake_post)
    with pytest.raises(AIProviderResponseError):
        provider.invoke(_request())


def test_research_policy_is_sent_as_system_prompt(monkeypatch, provider: ClaudeAIProvider) -> None:
    from app.ai.policy import RESEARCH_POLICY

    captured = {}

    def fake_post(url, headers, payload, timeout):
        captured["system"] = payload["system"]
        return 200, _tool_use_body({"objective": "o", "hypothesis": "h", "reasoning_summary": "r"})

    monkeypatch.setattr(claude_mod, "_http_post_json", fake_post)
    provider.invoke(_request())
    assert captured["system"] == RESEARCH_POLICY
