from app.research.source import (
    Source,
    SourceStatus,
    SourceType,
    compute_content_hash,
    extract_domain,
    normalize_url,
)


def test_normalize_url_lowercases_scheme_and_host() -> None:
    # Path case is deliberately preserved - paths ARE case-sensitive on
    # most servers, unlike scheme/host, so lowercasing one would risk
    # treating two genuinely different documents as the same source.
    assert normalize_url("HTTPS://Example.COM/Path") == "https://example.com/Path"


def test_normalize_url_drops_trailing_slash() -> None:
    assert normalize_url("https://example.com/path/") == normalize_url("https://example.com/path")


def test_normalize_url_drops_fragment_but_keeps_query() -> None:
    normalized = normalize_url("https://example.com/path?x=1#section")
    assert "#" not in normalized
    assert "x=1" in normalized


def test_normalize_url_treats_different_queries_as_different() -> None:
    assert normalize_url("https://example.com/p?x=1") != normalize_url("https://example.com/p?x=2")


def test_extract_domain() -> None:
    assert extract_domain("https://Example.com/path") == "example.com"


def test_compute_content_hash_is_deterministic() -> None:
    assert compute_content_hash(b"hello") == compute_content_hash(b"hello")
    assert compute_content_hash(b"hello") != compute_content_hash(b"world")


def test_source_normalized_url_property() -> None:
    source = Source(url="HTTPS://Example.com/A/")
    assert source.normalized_url == "https://example.com/A"


def test_source_defaults_do_not_invent_metadata() -> None:
    source = Source(url="https://example.com")
    assert source.title is None
    assert source.author is None
    assert source.published_at is None
    assert source.status is SourceStatus.DISCOVERED
    assert source.source_type is SourceType.UNKNOWN
