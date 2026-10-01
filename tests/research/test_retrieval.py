import socket
import urllib.error

import pytest

from app.research.limits import RetrievalLimits
from app.research.retrieval import HttpSourceRetriever, OversizedResponseError, RetrievalOutcome
from tests.research.conftest import SAMPLE_HTML, allow_all_robots_transport_wrapping


def _retriever(transport, **limit_overrides) -> HttpSourceRetriever:
    limits = RetrievalLimits(request_delay_seconds=0, **limit_overrides)
    return HttpSourceRetriever(limits, transport=allow_all_robots_transport_wrapping(transport))


def test_successful_retrieval() -> None:
    def transport(url, user_agent, limits):
        return 200, {"Content-Type": "text/html; charset=utf-8"}, SAMPLE_HTML, url

    result = _retriever(transport).retrieve("https://example.com/page")
    assert result.success
    assert result.outcome is RetrievalOutcome.SUCCESS
    assert result.content == SAMPLE_HTML
    assert result.content_type == "text/html; charset=utf-8"
    assert result.http_status == 200
    assert result.byte_size == len(SAMPLE_HTML)
    assert result.retrieved_at is not None


def test_timeout_is_reported_not_raised() -> None:
    def transport(url, user_agent, limits):
        raise TimeoutError("timed out")

    result = _retriever(transport).retrieve("https://example.com/slow")
    assert not result.success
    assert result.outcome is RetrievalOutcome.TIMEOUT


def test_http_error_is_reported() -> None:
    def transport(url, user_agent, limits):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    result = _retriever(transport).retrieve("https://example.com/missing")
    assert result.outcome is RetrievalOutcome.HTTP_ERROR
    assert result.http_status == 404


def test_network_error_is_reported() -> None:
    def transport(url, user_agent, limits):
        raise urllib.error.URLError(socket.gaierror("name resolution failed"))

    result = _retriever(transport).retrieve("https://nonexistent.invalid/page")
    assert result.outcome is RetrievalOutcome.NETWORK_ERROR


def test_oversized_response_is_reported_not_a_crash() -> None:
    def transport(url, user_agent, limits):
        raise OversizedResponseError("response exceeded max_response_bytes (10)")

    result = _retriever(transport, max_response_bytes=10).retrieve("https://example.com/huge")
    assert result.outcome is RetrievalOutcome.OVERSIZED


def test_unsupported_scheme_is_rejected_without_a_network_call() -> None:
    called = {"count": 0}

    def transport(url, user_agent, limits):
        called["count"] += 1
        return 200, {}, b"", url

    result = _retriever(transport).retrieve("file:///etc/passwd")
    assert result.outcome is RetrievalOutcome.UNSUPPORTED_SCHEME
    assert called["count"] == 0  # never even attempted a transport call


def test_ftp_scheme_is_also_rejected() -> None:
    result = _retriever(lambda *a: (200, {}, b"", "")).retrieve("ftp://example.com/file")
    assert result.outcome is RetrievalOutcome.UNSUPPORTED_SCHEME


def test_robots_txt_disallow_blocks_retrieval() -> None:
    def transport(url, user_agent, limits):
        if url.endswith("/robots.txt"):
            return 200, {}, b"User-agent: *\nDisallow: /private\n", url
        return 200, {"Content-Type": "text/html"}, SAMPLE_HTML, url

    limits = RetrievalLimits(request_delay_seconds=0)
    retriever = HttpSourceRetriever(limits, transport=transport)
    result = retriever.retrieve("https://example.com/private/page")
    assert result.outcome is RetrievalOutcome.ACCESS_DENIED
    assert "robots" in (result.reason or "").lower()


def test_robots_txt_allows_unblocked_paths() -> None:
    def transport(url, user_agent, limits):
        if url.endswith("/robots.txt"):
            return 200, {}, b"User-agent: *\nDisallow: /private\n", url
        return 200, {"Content-Type": "text/html"}, SAMPLE_HTML, url

    limits = RetrievalLimits(request_delay_seconds=0)
    retriever = HttpSourceRetriever(limits, transport=transport)
    result = retriever.retrieve("https://example.com/public/page")
    assert result.success


def test_missing_robots_txt_defaults_to_allowed() -> None:
    def transport(url, user_agent, limits):
        if url.endswith("/robots.txt"):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return 200, {"Content-Type": "text/html"}, SAMPLE_HTML, url

    limits = RetrievalLimits(request_delay_seconds=0)
    retriever = HttpSourceRetriever(limits, transport=transport)
    result = retriever.retrieve("https://example.com/page")
    assert result.success


def test_robots_txt_fetched_once_per_domain() -> None:
    robots_fetch_count = {"n": 0}

    def transport(url, user_agent, limits):
        if url.endswith("/robots.txt"):
            robots_fetch_count["n"] += 1
            return 200, {}, b"User-agent: *\nAllow: /\n", url
        return 200, {"Content-Type": "text/html"}, SAMPLE_HTML, url

    limits = RetrievalLimits(request_delay_seconds=0)
    retriever = HttpSourceRetriever(limits, transport=transport)
    retriever.retrieve("https://example.com/a")
    retriever.retrieve("https://example.com/b")
    assert robots_fetch_count["n"] == 1


def test_respect_robots_can_be_disabled() -> None:
    def transport(url, user_agent, limits):
        if url.endswith("/robots.txt"):
            return 200, {}, b"User-agent: *\nDisallow: /\n", url
        return 200, {"Content-Type": "text/html"}, SAMPLE_HTML, url

    limits = RetrievalLimits(request_delay_seconds=0)
    retriever = HttpSourceRetriever(limits, respect_robots=False, transport=transport)
    result = retriever.retrieve("https://example.com/anything")
    assert result.success


@pytest.mark.parametrize(
    "field,value",
    [("request_timeout_seconds", 0), ("max_response_bytes", 0), ("max_redirects", -1), ("request_delay_seconds", -1)],
)
def test_retrieval_limits_reject_invalid_values(field, value) -> None:
    with pytest.raises(ValueError):
        RetrievalLimits(**{field: value})
