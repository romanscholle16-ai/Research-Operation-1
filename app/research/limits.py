"""Human-controlled limits for a web research session (Phase 6 brief
sections 9/18/25). Same pattern as `app/ai/limits.py::ResearchLimits`:
a frozen dataclass constructed once by the caller, read-only from the
AI's perspective - there is no code path anywhere in `app/research/`
that builds one of these from AI output, so "the AI cannot increase
max sources/requests/timeouts/response size" is true by construction,
not by convention.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class WebStoppingReason(str, Enum):
    MAX_ITERATIONS = "max_iterations"
    MAX_SOURCES = "max_sources"
    MAX_REQUESTS = "max_requests"
    AI_REQUESTED_STOP = "ai_requested_stop"
    PROVIDER_ERROR = "provider_error"


@dataclass(frozen=True)
class RetrievalLimits:
    request_timeout_seconds: float = 15.0
    max_response_bytes: int = 2_000_000  # 2 MB
    max_redirects: int = 5
    request_delay_seconds: float = 0.0  # politeness delay between requests

    def __post_init__(self) -> None:
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be > 0")
        if self.max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be > 0")
        if self.max_redirects < 0:
            raise ValueError("max_redirects must be >= 0")
        if self.request_delay_seconds < 0:
            raise ValueError("request_delay_seconds must be >= 0")


@dataclass(frozen=True)
class WebResearchLimits:
    max_iterations: int = 10
    max_sources_per_session: int = 20
    max_requests_per_session: int = 30
    retrieval: RetrievalLimits = RetrievalLimits()
    max_cache_entries: int = 500
    max_cache_bytes: int = 50_000_000  # 50 MB

    def __post_init__(self) -> None:
        for name in ("max_iterations", "max_sources_per_session", "max_requests_per_session", "max_cache_entries"):
            if getattr(self, name) < 1:
                raise ValueError(f"WebResearchLimits.{name} must be >= 1")
        if self.max_cache_bytes <= 0:
            raise ValueError("max_cache_bytes must be > 0")
