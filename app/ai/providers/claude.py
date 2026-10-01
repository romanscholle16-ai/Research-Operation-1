"""Claude provider adapter (Phase 5 brief section 6).

Calls the Anthropic Messages API directly over HTTPS via the standard
library (`urllib.request`) rather than adding the `anthropic` package as
a dependency - the Messages API is a documented, stable JSON-over-HTTPS
contract, well within what stdlib can do cleanly, and this project's
stated preference (Phase 1) is no unnecessary dependencies. A future
phase can swap this for the official SDK behind the same `AIProvider`
interface without changing anything else, if streaming or other
SDK-only features are ever needed.

Structured output is forced via Anthropic's tool-use mechanism: a single
tool (`submit_research_decision`) is offered with `tool_choice` pinned
to it, so the model's only possible response shape is that tool's
`input_schema` - which mirrors `ResearchDecision`/`ExperimentProposal`
field-for-field. The tool's `input` is handed to the shared
`research_decision_from_dict()` parser (structured_output.py), not a
second, Claude-specific schema.

UNTESTED against the real API in this environment - no `ANTHROPIC_API_KEY`
was available (see PHASE_HISTORY.md "Phase 5"). Covered by tests that
mock the HTTP layer (`_http_post_json`) instead.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any

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
from app.ai.providers.secrets import redact
from app.ai.providers.structured_output import research_decision_from_dict

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DECISION_TOOL_NAME = "submit_research_decision"

DECISION_TOOL_SCHEMA: dict[str, Any] = {
    "name": DECISION_TOOL_NAME,
    "description": "Submit the structured research decision for this iteration.",
    "input_schema": {
        "type": "object",
        "properties": {
            "objective": {"type": "string"},
            "hypothesis": {"type": "string"},
            "reasoning_summary": {"type": "string"},
            "requested_experiments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "research_system": {
                            "type": "string",
                            "enum": [
                                "parameter_explorer",
                                "rule_explorer",
                                "risk_execution",
                                "market_conditions",
                                "adversarial",
                            ],
                        },
                        "reason": {"type": "string"},
                        "base_parameters": {"type": "object"},
                        "parameter_space": {"type": "object"},
                        "rule_variant_names": {"type": "array", "items": {"type": "string"}},
                        "execution_variant_names": {"type": "array", "items": {"type": "string"}},
                        "segment_specs": {"type": "array", "items": {"type": "object"}},
                        "adversarial": {"type": "object"},
                    },
                    "required": ["research_system"],
                },
            },
            "analysis_tasks": {"type": "array", "items": {"type": "string"}},
            "stopping_reason": {"type": ["string", "null"]},
            "confidence": {"type": ["number", "null"]},
        },
        "required": ["objective", "hypothesis", "reasoning_summary", "requested_experiments"],
    },
}


def _http_post_json(
    url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float
) -> tuple[int, dict[str, Any]]:
    """Thin, deliberately mockable wrapper around urllib - tests patch
    this one function rather than the real network stack."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https URL, not user input
        return resp.status, json.loads(resp.read().decode("utf-8"))


class ClaudeAIProvider(AIProvider):
    is_mock = False
    capabilities = ProviderCapabilities(
        structured_output=True,
        tool_calling=True,
        token_usage_reporting=True,
        streaming=False,
        model_selection=True,
        configurable_temperature=True,
        local_offline=False,
    )

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "claude-sonnet-5",
        max_tokens: int = 4096,
        temperature: float = 0.0,
        timeout: float = 60.0,
    ) -> None:
        if not api_key:
            raise ValueError("ClaudeAIProvider requires a non-empty api_key")
        self._api_key = api_key
        self.provider_name = "claude"
        self.model_name = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._timeout = timeout

    def invoke(self, request: AIInvocationRequest) -> AIInvocationResponse:
        payload = {
            "model": self.model_name,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
            "system": RESEARCH_POLICY,
            "messages": [{"role": "user", "content": self._render_user_prompt(request)}],
            "tools": [DECISION_TOOL_SCHEMA],
            "tool_choice": {"type": "tool", "name": DECISION_TOOL_NAME},
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        try:
            _status, body = _http_post_json(ANTHROPIC_API_URL, headers, payload, self._timeout)
        except urllib.error.HTTPError as exc:
            raise self._map_http_error(exc) from None
        except (socket.timeout, TimeoutError) as exc:
            raise AIProviderTimeoutError(f"Claude API request timed out: {exc}") from None
        except urllib.error.URLError as exc:
            raise AIProviderUnavailableError(f"could not reach Claude API: {exc.reason}") from None
        except json.JSONDecodeError as exc:
            raise AIProviderResponseError(f"Claude API returned unparseable JSON: {exc}") from None

        tool_input = self._extract_tool_input(body)
        decision = research_decision_from_dict(tool_input)

        usage = body.get("usage") or {}
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        total_tokens = (input_tokens or 0) + (output_tokens or 0) if usage else None

        return AIInvocationResponse(
            decision=decision,
            provider_name=self.provider_name,
            model_name=self.model_name,
            raw_summary=f"claude response id={body.get('id')} stop_reason={body.get('stop_reason')}",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost=None,  # Anthropic's API does not return a $ cost figure
            response_id=body.get("id"),
        )

    def _render_user_prompt(self, request: AIInvocationRequest) -> str:
        return (
            f"Iteration {request.iteration}.\n\n"
            f"Research context:\n{request.context.summary(max_chars=4000)}\n\n"
            f"Call {DECISION_TOOL_NAME} with the next research decision."
        )

    def _extract_tool_input(self, body: dict[str, Any]) -> dict[str, Any]:
        for block in body.get("content", []):
            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == DECISION_TOOL_NAME:
                tool_input = block.get("input")
                if isinstance(tool_input, dict):
                    return tool_input
        raise AIProviderResponseError(
            f"Claude response did not include a {DECISION_TOOL_NAME} tool_use block: "
            f"{redact(json.dumps(body)[:500], self._api_key)}"
        )

    def _map_http_error(self, exc: urllib.error.HTTPError) -> AIProviderError:
        status = exc.code
        try:
            body_text = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body_text = ""
        safe_body = redact(body_text, self._api_key)[:300]
        if status == 401:
            return AIProviderAuthError(f"Claude API authentication failed (401): {safe_body}")
        if status == 429:
            return AIProviderRateLimitError(f"Claude API rate limited (429): {safe_body}")
        if status in (500, 502, 503, 504):
            return AIProviderUnavailableError(f"Claude API unavailable ({status}): {safe_body}")
        return AIProviderError(f"Claude API error ({status}): {safe_body}")
