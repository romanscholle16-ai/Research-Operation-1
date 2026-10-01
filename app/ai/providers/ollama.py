"""Local-model provider adapter (Phase 5 brief section 8), targeting a
locally-running Ollama server's HTTP API (`/api/chat`), reached over
stdlib `urllib` the same way `claude.py` reaches Anthropic's API - no
new dependency.

Ollama itself is NOT installed by this phase and is not installed by
this project at all - it is normal desktop software with its own
installer, which would mean installing something outside this project's
self-contained `.venv` without being asked to (Phase 5 brief section 4/
30). This adapter is therefore the "interface/configuration path" the
brief explicitly allows building ahead of the runtime dependency
(section 8): the code exists and is unit-tested against a mocked HTTP
layer, but it has never been run against a real Ollama server in this
environment, and `OllamaAIProvider.invoke()` will raise
`AIProviderUnavailableError` if no server is listening at `base_url`
(the default, `http://localhost:11434`, confirmed unreachable here - see
PHASE_HISTORY.md "Phase 5").

Ollama does not support forced tool-calling uniformly across every model
it can serve, so structured output here uses its `format: "json"` option
plus an explicit schema description in the prompt, parsed by the same
shared `research_decision_from_dict()` every other JSON-returning
provider uses.
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
    AIProviderError,
    AIProviderResponseError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
    ProviderCapabilities,
)
from app.ai.providers.structured_output import research_decision_from_dict

_DECISION_SCHEMA_HINT = """\
Respond with ONLY a single JSON object (no prose, no markdown fences) \
with exactly these fields:
{
  "objective": string,
  "hypothesis": string,
  "reasoning_summary": string,
  "requested_experiments": [
    {
      "research_system": one of "parameter_explorer" | "rule_explorer" | \
"risk_execution" | "market_conditions" | "adversarial",
      "reason": string (optional),
      "base_parameters": object (optional),
      "parameter_space": object (optional, parameter_explorer only),
      "rule_variant_names": array of string (optional, rule_explorer only),
      "execution_variant_names": array of string (optional, risk_execution only),
      "segment_specs": array of object (optional, market_conditions only),
      "adversarial": object (optional, adversarial only)
    }
  ],
  "analysis_tasks": array of string (optional),
  "stopping_reason": string or null,
  "confidence": number or null
}
"""


def _http_post_json(
    url: str, payload: dict[str, Any], timeout: float
) -> dict[str, Any]:
    """Thin, deliberately mockable wrapper around urllib."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - local server, not user input
        return json.loads(resp.read().decode("utf-8"))


class OllamaAIProvider(AIProvider):
    is_mock = False
    capabilities = ProviderCapabilities(
        structured_output=True,
        tool_calling=False,
        token_usage_reporting=True,
        streaming=False,
        model_selection=True,
        configurable_temperature=True,
        local_offline=True,
    )

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:11434",
        model: str = "llama3",
        temperature: float = 0.0,
        timeout: float = 60.0,
    ) -> None:
        self.provider_name = "ollama"
        self.model_name = model
        self._base_url = base_url.rstrip("/")
        self._temperature = temperature
        self._timeout = timeout

    def invoke(self, request: AIInvocationRequest) -> AIInvocationResponse:
        payload = {
            "model": self.model_name,
            "format": "json",
            "stream": False,
            "options": {"temperature": self._temperature},
            "messages": [
                {"role": "system", "content": RESEARCH_POLICY + "\n\n" + _DECISION_SCHEMA_HINT},
                {"role": "user", "content": self._render_user_prompt(request)},
            ],
        }
        url = f"{self._base_url}/api/chat"

        try:
            body = _http_post_json(url, payload, self._timeout)
        except (socket.timeout, TimeoutError) as exc:
            raise AIProviderTimeoutError(f"Ollama request timed out: {exc}") from None
        except urllib.error.URLError as exc:
            raise AIProviderUnavailableError(
                f"could not reach local Ollama server at {self._base_url} ({exc.reason}) - "
                "is it running? Ollama is not installed/managed by this project."
            ) from None
        except json.JSONDecodeError as exc:
            raise AIProviderResponseError(f"Ollama returned unparseable JSON: {exc}") from None

        message = body.get("message") or {}
        content = message.get("content")
        if not isinstance(content, str):
            raise AIProviderResponseError("Ollama response missing message.content")
        try:
            decision_dict = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AIProviderResponseError(f"Ollama message.content was not valid JSON: {exc}") from None

        decision = research_decision_from_dict(decision_dict)

        input_tokens = body.get("prompt_eval_count")
        output_tokens = body.get("eval_count")
        total_tokens = (input_tokens or 0) + (output_tokens or 0) if (input_tokens or output_tokens) else None

        return AIInvocationResponse(
            decision=decision,
            provider_name=self.provider_name,
            model_name=self.model_name,
            raw_summary=f"ollama model={self.model_name} done={body.get('done')}",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost=None,  # local inference has no per-call provider cost
        )

    def _render_user_prompt(self, request: AIInvocationRequest) -> str:
        return f"Iteration {request.iteration}.\n\nResearch context:\n{request.context.summary(max_chars=4000)}"
