"""Provider registry + router (Phase 5 brief sections 9-10).

`AIProviderRouter` itself implements the `AIProvider` interface
(`invoke()`), so `ResearchAgent` needs ZERO changes to use it - a router
is, from the agent's point of view, just another provider. That is the
concrete mechanism behind "ResearchAgent must not need to know which
provider is being used" / "provider can be changed without rewriting
ResearchAgent."
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from app.ai.provider import AIInvocationRequest, AIInvocationResponse, AIProvider, AIProviderError
from app.ai.providers.claude import ClaudeAIProvider
from app.ai.providers.freebuff import FreebuffAIProvider
from app.ai.providers.mock import MockAIProvider
from app.ai.providers.ollama import OllamaAIProvider

if TYPE_CHECKING:
    from app.config.settings import Settings

KNOWN_PROVIDER_NAMES = ("claude", "anthropic", "freebuff", "ollama", "mock")


class ProviderConfigurationError(ValueError):
    """Provider configuration is invalid or incomplete. Raised
    immediately and clearly (brief section 9's "invalid provider
    configuration fails clearly") - never silently defaulted to mock or
    to any other provider."""


def build_provider(name: str, settings: "Settings") -> AIProvider:
    """Construct one named provider from `settings.ai_provider`.
    `"claude"` and `"anthropic"` are the same provider - the brief's
    router example uses "claude"; this project's Phase 1 config
    (`AI_ACTIVE_PROVIDER`) already used "anthropic" for the same vendor,
    so both spellings are accepted rather than picking one and silently
    breaking the other.
    """
    key = (name or "").strip().lower()
    if key == "mock":
        return MockAIProvider({})
    if key in ("claude", "anthropic"):
        api_key = settings.ai_provider.anthropic_api_key
        if not api_key:
            raise ProviderConfigurationError(
                "provider 'claude'/'anthropic' selected but ANTHROPIC_API_KEY is not set (see .env.example)"
            )
        return ClaudeAIProvider(api_key=api_key, model=settings.ai_provider.anthropic_model)
    if key == "freebuff":
        return FreebuffAIProvider(api_key=settings.ai_provider.freebuff_api_key)
    if key == "ollama":
        return OllamaAIProvider(base_url=settings.ai_provider.ollama_base_url)
    raise ProviderConfigurationError(f"unknown AI provider {name!r}; must be one of {KNOWN_PROVIDER_NAMES}")


class AIProviderRouter(AIProvider):
    """Tries each provider in `chain` in order; the first to succeed
    serves the request. A fallback entry that is a mock provider is
    skipped unless `allow_mock_fallback=True` - a real research session
    must never silently end up running on fake data just because its
    real provider failed (brief section 10). The chain's FIRST entry is
    never subject to this gate: explicitly configuring mock as your
    primary provider is exactly the "explicit test/development
    configuration" the brief allows.
    """

    is_mock = False

    def __init__(self, chain: list[AIProvider], *, allow_mock_fallback: bool = False) -> None:
        if not chain:
            raise ProviderConfigurationError("AIProviderRouter requires at least one provider in its chain")
        self._chain = chain
        self._allow_mock_fallback = allow_mock_fallback
        self.provider_name = "router(" + "->".join(p.provider_name for p in chain) + ")"
        self.model_name = chain[0].model_name

    @property
    def primary(self) -> AIProvider:
        return self._chain[0]

    def invoke(self, request: AIInvocationRequest) -> AIInvocationResponse:
        errors: list[str] = []
        tried: list[str] = []
        for index, provider in enumerate(self._chain):
            if index > 0 and provider.is_mock and not self._allow_mock_fallback:
                errors.append(f"{provider.provider_name}: skipped (mock fallback not explicitly allowed)")
                continue
            tried.append(provider.provider_name)
            try:
                response = provider.invoke(request)
            except AIProviderError as exc:
                errors.append(f"{provider.provider_name}: {exc}")
                continue
            if len(tried) > 1:
                response = dataclasses.replace(response, fallback_chain=tuple(tried))
            return response
        raise AIProviderError("all providers in the chain failed or were skipped: " + "; ".join(errors))


def build_router_from_settings(settings: "Settings") -> AIProviderRouter:
    """The configuration-driven entry point (brief section 9): reads
    `AI_ACTIVE_PROVIDER` as the primary and `AI_PROVIDER_FALLBACK_CHAIN`
    (comma-separated) as fallbacks, gated by `AI_ALLOW_MOCK_FALLBACK`."""
    primary_name = settings.ai_provider.active_provider
    fallback_names = [n.strip() for n in settings.ai_provider.fallback_chain.split(",") if n.strip()]
    chain = [build_provider(primary_name, settings)] + [build_provider(n, settings) for n in fallback_names]
    return AIProviderRouter(chain, allow_mock_fallback=settings.ai_provider.allow_mock_fallback)
