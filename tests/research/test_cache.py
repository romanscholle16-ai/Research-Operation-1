from app.research.cache import SourceCache


def test_cache_miss_returns_none(tmp_path) -> None:
    cache = SourceCache(tmp_path, max_entries=10, max_bytes=10_000)
    assert cache.get("https://example.com/a") is None


def test_cache_put_then_get_round_trips(tmp_path) -> None:
    cache = SourceCache(tmp_path, max_entries=10, max_bytes=10_000)
    cache.put("https://example.com/a", b"hello world", content_type="text/plain", content_hash="abc123", retrieved_at="2024-01-01T00:00:00Z")

    cached = cache.get("https://example.com/a")
    assert cached is not None
    assert cached.content == b"hello world"
    assert cached.content_type == "text/plain"
    assert cached.content_hash == "abc123"


def test_cache_is_bounded_by_entry_count(tmp_path) -> None:
    cache = SourceCache(tmp_path, max_entries=2, max_bytes=1_000_000)
    cache.put("https://example.com/1", b"a", content_type=None, content_hash="h1", retrieved_at="t1")
    cache.put("https://example.com/2", b"b", content_type=None, content_hash="h2", retrieved_at="t2")
    cache.put("https://example.com/3", b"c", content_type=None, content_hash="h3", retrieved_at="t3")

    count, _ = cache.stats()
    assert count == 2
    assert cache.get("https://example.com/1") is None  # oldest evicted
    assert cache.get("https://example.com/3") is not None


def test_cache_is_bounded_by_total_bytes(tmp_path) -> None:
    cache = SourceCache(tmp_path, max_entries=100, max_bytes=15)
    cache.put("https://example.com/1", b"x" * 10, content_type=None, content_hash="h1", retrieved_at="t1")
    cache.put("https://example.com/2", b"y" * 10, content_type=None, content_hash="h2", retrieved_at="t2")

    count, total_bytes = cache.stats()
    assert total_bytes <= 15
    assert cache.get("https://example.com/1") is None


def test_cache_key_is_based_on_normalized_url() -> None:
    from app.research.source import normalize_url

    # Scheme/host casing and a trailing slash are formatting differences
    # (deduplicated); a different PATH casing is a different URL, since
    # paths are case-sensitive on most servers.
    assert normalize_url("https://Example.com/A") == normalize_url("HTTPS://example.com/A/")
    assert normalize_url("https://example.com/A") != normalize_url("https://example.com/a")
