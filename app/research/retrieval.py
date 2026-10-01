"""Controlled source retrieval (Phase 6 brief sections 8-9/25-26).

`HttpSourceRetriever` is the only implementation - plain HTTP(S) GET via
stdlib `urllib`, nothing more. It does not: solve CAPTCHAs, authenticate,
bypass paywalls, evade anti-bot protection, or ignore `robots.txt`. If a
site blocks a plain, polite GET, that is recorded as `ACCESS_DENIED` or
`FAILED` and the session moves on - never worked around.

The network call itself is factored into a small, injectable `transport`
callable (same pattern as Phase 5's `_http_post_json`) so every test in
this project mocks it instead of touching a real network.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol

from app.research.limits import RetrievalLimits

ALLOWED_SCHEMES = frozenset({"http", "https"})

TransportResult = tuple[int, dict[str, str], bytes, str]  # status, headers, body, final_url
Transport = Callable[[str, str, RetrievalLimits], TransportResult]


class OversizedResponseError(Exception):
    pass


class RetrievalOutcome(str, Enum):
    SUCCESS = "success"
    ACCESS_DENIED = "access_denied"
    TIMEOUT = "timeout"
    HTTP_ERROR = "http_error"
    OVERSIZED = "oversized"
    NETWORK_ERROR = "network_error"
    UNSUPPORTED_SCHEME = "unsupported_scheme"


@dataclass(frozen=True)
class RetrievalResult:
    url: str
    outcome: RetrievalOutcome
    content: bytes | None = None
    content_type: str | None = None
    http_status: int | None = None
    byte_size: int | None = None
    final_url: str | None = None
    reason: str | None = None
    retrieved_at: str | None = None

    @property
    def success(self) -> bool:
        return self.outcome is RetrievalOutcome.SUCCESS


class SourceRetriever(Protocol):
    def retrieve(self, url: str) -> RetrievalResult: ...


class _BoundedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, max_redirects: int) -> None:
        self.max_redirections = max_redirects


def default_transport(url: str, user_agent: str, limits: RetrievalLimits) -> TransportResult:
    """The real network transport - stdlib `urllib` only, no dependency."""
    opener = urllib.request.build_opener(_BoundedRedirectHandler(limits.max_redirects))
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with opener.open(request, timeout=limits.request_timeout_seconds) as response:  # noqa: S310
        body = response.read(limits.max_response_bytes + 1)
        if len(body) > limits.max_response_bytes:
            raise OversizedResponseError(f"response exceeded max_response_bytes ({limits.max_response_bytes})")
        return response.status, dict(response.headers), body, response.geturl()


class HttpSourceRetriever:
    """Plain HTTP(S) retrieval, robots.txt-respecting, bounded by
    `RetrievalLimits`. No authentication, no cookies beyond what a single
    anonymous GET implies, no JavaScript execution - a page that requires
    any of those simply comes back however it comes back to any basic
    client, which is not "bypassing" anything.
    """

    def __init__(
        self,
        limits: RetrievalLimits,
        *,
        user_agent: str = "StrategyResearchLab-ResearchBot/1.0 (+local research tool)",
        respect_robots: bool = True,
        transport: Transport = default_transport,
    ) -> None:
        self._limits = limits
        self._user_agent = user_agent
        self._respect_robots = respect_robots
        self._transport = transport
        self._robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last_request_at: float | None = None

    def retrieve(self, url: str) -> RetrievalResult:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in ALLOWED_SCHEMES:
            return RetrievalResult(
                url=url, outcome=RetrievalOutcome.UNSUPPORTED_SCHEME, reason=f"unsupported scheme {parsed.scheme!r}"
            )

        if self._respect_robots and not self._can_fetch(url, parsed):
            return RetrievalResult(url=url, outcome=RetrievalOutcome.ACCESS_DENIED, reason="robots.txt disallows this URL")

        self._apply_politeness_delay()

        try:
            status, headers, body, final_url = self._transport(url, self._user_agent, self._limits)
        except OversizedResponseError as exc:
            return RetrievalResult(url=url, outcome=RetrievalOutcome.OVERSIZED, reason=str(exc))
        except TimeoutError as exc:
            return RetrievalResult(url=url, outcome=RetrievalOutcome.TIMEOUT, reason=str(exc) or "request timed out")
        except urllib.error.HTTPError as exc:
            return RetrievalResult(url=url, outcome=RetrievalOutcome.HTTP_ERROR, http_status=exc.code, reason=str(exc))
        except urllib.error.URLError as exc:
            return RetrievalResult(url=url, outcome=RetrievalOutcome.NETWORK_ERROR, reason=str(exc.reason))

        content_type = next((v for k, v in headers.items() if k.lower() == "content-type"), None)
        return RetrievalResult(
            url=url,
            outcome=RetrievalOutcome.SUCCESS,
            content=body,
            content_type=content_type,
            http_status=status,
            byte_size=len(body),
            final_url=final_url,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
        )

    def _apply_politeness_delay(self) -> None:
        if self._limits.request_delay_seconds <= 0:
            return
        if self._last_request_at is not None:
            elapsed = time.monotonic() - self._last_request_at
            remaining = self._limits.request_delay_seconds - elapsed
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_at = time.monotonic()

    def _can_fetch(self, url: str, parsed: urllib.parse.SplitResult) -> bool:
        root = f"{parsed.scheme}://{parsed.netloc}"
        parser = self._robots_cache.get(root)
        if parser is None:
            parser = urllib.robotparser.RobotFileParser()
            robots_url = root + "/robots.txt"
            try:
                _status, _headers, body, _final = self._transport(robots_url, self._user_agent, self._limits)
                parser.parse(body.decode("utf-8", errors="replace").splitlines())
            except Exception:
                # No readable robots.txt (404, network error, ...) - standard
                # web convention is to allow, not to assume disallowed.
                parser.allow_all = True
            self._robots_cache[root] = parser
        return parser.can_fetch(self._user_agent, url)
