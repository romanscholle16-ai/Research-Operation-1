from app.research.discovery import DiscoveryCandidate, ManualSourceDiscoveryProvider, MockSourceDiscoveryProvider


def test_manual_discovery_returns_configured_candidates() -> None:
    provider = ManualSourceDiscoveryProvider(
        {"ema strategy": [DiscoveryCandidate(url="https://example.com/a", title="A")]}
    )
    result = provider.discover("ema strategy")
    assert result.query == "ema strategy"
    assert len(result.candidates) == 1
    assert result.candidates[0].url == "https://example.com/a"
    assert result.provider_name == "manual"
    assert result.discovered_at


def test_manual_discovery_empty_for_unknown_query() -> None:
    provider = ManualSourceDiscoveryProvider({})
    result = provider.discover("nothing configured")
    assert result.candidates == ()


def test_discovery_candidate_domain_property() -> None:
    candidate = DiscoveryCandidate(url="https://Sub.Example.COM/path")
    assert candidate.domain == "sub.example.com"


def test_discovery_does_not_assert_reputability() -> None:
    """DiscoveryResult/DiscoveryCandidate carry only objective facts -
    there is no 'trust'/'reputable' field anywhere on them (brief
    section 11: never claim a source is reputable merely because
    something says so)."""
    import dataclasses

    candidate_fields = {f.name for f in dataclasses.fields(DiscoveryCandidate)}
    assert "trust" not in candidate_fields
    assert "reputable" not in candidate_fields
    assert "trust_score" not in candidate_fields


def test_mock_discovery_is_deterministic_and_scripted() -> None:
    provider = MockSourceDiscoveryProvider({"q": [DiscoveryCandidate(url="https://x.com")]})
    r1 = provider.discover("q")
    r2 = provider.discover("q")
    assert [c.url for c in r1.candidates] == [c.url for c in r2.candidates]
    assert provider.call_count == 2


def test_mock_discovery_unscripted_query_returns_empty() -> None:
    provider = MockSourceDiscoveryProvider({})
    result = provider.discover("unscripted")
    assert result.candidates == ()
