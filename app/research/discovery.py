"""Source discovery (Phase 6 brief section 11).

No real search-engine-backed discovery provider is implemented in this
phase - a legitimate one (Bing/Google/etc. search API) needs its own API
key, which was not available (same situation, and same honest-placeholder
treatment, as Phase 5's `FreebuffAIProvider`). `ManualSourceDiscoveryProvider`
is the real, usable implementation: it structures a human/config-supplied
candidate URL list into the same typed `DiscoveryResult` shape a search-
API-backed provider would eventually produce, so the rest of the pipeline
(retrieval, evidence, specification) never needs to know which kind of
discovery produced its input. `MockSourceDiscoveryProvider` is the
deterministic, scripted-by-query test double (same pattern as
`MockAIProvider`).

Per brief section 11/12: a discovered source's "reputability" is never
asserted here - `DiscoveryResult` carries only objective facts (query,
URL, title if supplied, domain, discovery timestamp). Nothing computes a
trust verdict at discovery time; that stays with `TrustSignals`
(source.py), filled in only once a source is actually retrieved.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import urlsplit


def new_discovery_id() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True)
class DiscoveryCandidate:
    url: str
    title: str | None = None

    @property
    def domain(self) -> str:
        return urlsplit(self.url).netloc.lower()


@dataclass(frozen=True)
class DiscoveryResult:
    id: str
    query: str
    candidates: tuple[DiscoveryCandidate, ...]
    discovered_at: str
    provider_name: str


class SourceDiscoveryProvider(Protocol):
    provider_name: str

    def discover(self, query: str) -> DiscoveryResult: ...


class ManualSourceDiscoveryProvider:
    """Structures a pre-supplied, human/config-curated URL list. This is
    the only discovery provider in this phase that is actually connected
    to real URLs - it does not search the internet itself, it organizes
    URLs someone already chose."""

    provider_name = "manual"

    def __init__(self, candidates_by_query: dict[str, list[DiscoveryCandidate]]) -> None:
        self._candidates_by_query = candidates_by_query

    def discover(self, query: str) -> DiscoveryResult:
        candidates = tuple(self._candidates_by_query.get(query, ()))
        return DiscoveryResult(
            id=new_discovery_id(),
            query=query,
            candidates=candidates,
            discovered_at=datetime.now(timezone.utc).isoformat(),
            provider_name=self.provider_name,
        )


class MockSourceDiscoveryProvider:
    """Deterministic, scripted-by-query test double - no network access,
    same role `MockAIProvider` plays for `app.ai`."""

    provider_name = "mock_discovery"

    def __init__(self, script: dict[str, list[DiscoveryCandidate]]) -> None:
        self._script = script
        self.call_count = 0

    def discover(self, query: str) -> DiscoveryResult:
        self.call_count += 1
        candidates = tuple(self._script.get(query, ()))
        return DiscoveryResult(
            id=new_discovery_id(),
            query=query,
            candidates=candidates,
            discovered_at=datetime.now(timezone.utc).isoformat(),
            provider_name=self.provider_name,
        )
