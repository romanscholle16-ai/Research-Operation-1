"""Freebuff provider - STRUCTURAL PLACEHOLDER ONLY, not a working
integration (Phase 5 brief section 7).

Section 7 is explicit: "If Freebuff requires a specific external
installation or configuration that cannot be completed project-locally:
DO NOT improvise... Do not pretend a provider is implemented if it is
only a placeholder." No verified, stable Freebuff API contract (base
URL, authentication scheme, request/response shape) was available while
building this phase - inventing one would risk silently calling the
wrong endpoint in the wrong shape and failing in a confusing way, or
worse, "succeeding" against nothing real. Rather than guess, this class
exists only so:

- the provider registry/router has a consistent menu of all four names
  the Phase 5 brief lists (claude, freebuff, ollama, mock), and
- `FreebuffAIProvider` genuinely IS-A `AIProvider` (same constructor
  shape, same `invoke()` signature), proving the interface itself
  doesn't need to change to add a real Freebuff backend later.

`invoke()` always raises `AIProviderUnavailableError`. To make this real:
replace the body of `invoke()` with an actual HTTP call once Freebuff's
API documentation (base URL, auth header format, request/response JSON
shape) is available - follow `claude.py`'s structure (a mockable
`_http_post_json`-style wrapper, a shared-parser call via
`research_decision_from_dict()`, and vendor-error-code -> AIProviderError
mapping) rather than inventing a new pattern.
"""

from __future__ import annotations

from app.ai.provider import (
    AIInvocationRequest,
    AIInvocationResponse,
    AIProvider,
    AIProviderUnavailableError,
    ProviderCapabilities,
)


class FreebuffAIProvider(AIProvider):
    is_mock = False
    capabilities = ProviderCapabilities()  # unknown until a real API contract exists

    def __init__(self, *, api_key: str | None = None, base_url: str | None = None) -> None:
        self.provider_name = "freebuff"
        self.model_name = "unknown"
        self._api_key = api_key
        self._base_url = base_url

    def invoke(self, request: AIInvocationRequest) -> AIInvocationResponse:
        raise AIProviderUnavailableError(
            "FreebuffAIProvider is a structural placeholder only - no verified Freebuff API "
            "contract (base URL / auth scheme / request-response shape) was available to implement "
            "against during Phase 5. See app/ai/providers/freebuff.py's module docstring and "
            "PHASE_HISTORY.md 'Phase 5' for exactly what is needed to complete this."
        )
