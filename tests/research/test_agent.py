from app.ai.provider import AIProviderError
from app.ai.provider import AIProvider, AIInvocationResponse
from app.core.events import EventType
from app.database.connection import Database
from app.research import persistence as rp
from app.research.agent import WebResearchAgent
from app.research.decision import ProposedRule, ResearchAction, SpecificationUpdate, WebResearchDecision
from app.research.discovery import DiscoveryCandidate, ManualSourceDiscoveryProvider
from app.research.limits import RetrievalLimits, WebResearchLimits, WebStoppingReason
from app.research.mock_provider import MockWebResearchProvider
from app.research.retrieval import HttpSourceRetriever
from app.research.session import WebResearchSessionStatus
from app.research.specification import Condition, FieldRef, IndicatorSpec
from tests.research.conftest import SAMPLE_HTML, allow_all_robots_transport_wrapping

URL = "https://example.com/strategy"


def _html_transport(url, user_agent, limits):
    return 200, {"Content-Type": "text/html; charset=utf-8"}, SAMPLE_HTML, url


def _retriever() -> HttpSourceRetriever:
    return HttpSourceRetriever(RetrievalLimits(request_delay_seconds=0), transport=allow_all_robots_transport_wrapping(_html_transport))


def _agent(database: Database, provider, *, discovery=None, limits=None, cache_dir) -> WebResearchAgent:
    discovery = discovery or ManualSourceDiscoveryProvider({"q": [DiscoveryCandidate(url=URL, title="t")]})
    limits = limits or WebResearchLimits(max_iterations=10, max_sources_per_session=10, max_requests_per_session=10)
    return WebResearchAgent(database, provider, discovery=discovery, retriever=_retriever(), limits=limits, cache_dir=cache_dir)


def _events(database: Database, session_id: str) -> list[str]:
    rows = database.query_all("SELECT event_type FROM events WHERE related_id = ? ORDER BY created_at, rowid", (session_id,))
    return [row["event_type"] for row in rows]


def test_discover_then_retrieve_then_stop(database: Database, tmp_path) -> None:
    script = {
        0: WebResearchDecision(objective="o", reasoning_summary="discover", action=ResearchAction.DISCOVER_SOURCES, query="q"),
        1: WebResearchDecision(objective="o", reasoning_summary="retrieve", action=ResearchAction.RETRIEVE_SOURCE, url=URL, stopping_reason="done"),
    }
    agent = _agent(database, MockWebResearchProvider(script), cache_dir=tmp_path / "cache")
    record = agent.run("o")

    assert record.status is WebResearchSessionStatus.COMPLETED
    assert record.stopping_reason == "done"
    assert record.sources_discovered == 1
    assert record.sources_retrieved == 1
    assert record.evidence_count > 0

    sources = rp.list_sources(database, record.id)
    assert len(sources) == 1  # discovered + retrieved = ONE source identity, not two
    assert sources[0]["status"] == "retrieved"


def test_cache_hit_on_second_retrieval_of_same_url(database: Database, tmp_path) -> None:
    script = {
        0: WebResearchDecision(objective="o", reasoning_summary="retrieve", action=ResearchAction.RETRIEVE_SOURCE, url=URL),
        1: WebResearchDecision(objective="o", reasoning_summary="retrieve again", action=ResearchAction.RETRIEVE_SOURCE, url=URL, stopping_reason="done"),
    }
    agent = _agent(database, MockWebResearchProvider(script), cache_dir=tmp_path / "cache")
    record = agent.run("o")

    assert record.requests_made == 1  # second retrieval was a cache hit, not a new request
    event_types = _events(database, record.id)
    assert EventType.SOURCE_CACHE_HIT.value in event_types


def test_update_and_validate_specification(database: Database, tmp_path) -> None:
    update = SpecificationUpdate(
        name="ema strat", timeframe="1h",
        indicators=(IndicatorSpec(type="EMA", params={"period": 50}),),
        rules=(ProposedRule(rule_kind="entry", description="enter long", side="long",
                              condition=Condition(op="crosses_above", left=FieldRef(name="close"), right=FieldRef(name="EMA", params={"period": 50}))),),
    )
    script = {
        0: WebResearchDecision(objective="o", reasoning_summary="build", action=ResearchAction.UPDATE_SPECIFICATION, specification_update=update),
        1: WebResearchDecision(objective="o", reasoning_summary="validate", action=ResearchAction.VALIDATE_SPECIFICATION, stopping_reason="done"),
    }
    agent = _agent(database, MockWebResearchProvider(script), cache_dir=tmp_path / "cache")
    record = agent.run("o")

    assert record.final_specification_status == "valid"
    specs = rp.list_specifications(database, record.id)
    assert len(specs) == 2
    assert specs[-1]["status"] == "valid"


def test_ai_proposed_rule_is_always_interpreted_never_explicit(database: Database, tmp_path) -> None:
    import json

    update = SpecificationUpdate(
        name="s",
        rules=(ProposedRule(rule_kind="entry", description="enter long", side="long",
                              condition=Condition(op=">", left=FieldRef(name="close"), right=100)),),
    )
    script = {0: WebResearchDecision(objective="o", reasoning_summary="build", action=ResearchAction.UPDATE_SPECIFICATION, specification_update=update, stopping_reason="done")}
    agent = _agent(database, MockWebResearchProvider(script), cache_dir=tmp_path / "cache")
    record = agent.run("o")

    specs = rp.list_specifications(database, record.id)
    spec_dict = json.loads(specs[-1]["specification"])
    assert spec_dict["entry_rules"][0]["status"] == "interpreted"


def test_stops_at_max_iterations(database: Database, tmp_path) -> None:
    script = {i: WebResearchDecision(objective="o", reasoning_summary=f"noop {i}", action=ResearchAction.DISCOVER_SOURCES, query="unscripted") for i in range(10)}
    limits = WebResearchLimits(max_iterations=3, max_sources_per_session=100, max_requests_per_session=100)
    provider = MockWebResearchProvider(script)
    agent = _agent(database, provider, limits=limits, cache_dir=tmp_path / "cache")
    record = agent.run("o")

    assert record.stopping_reason == WebStoppingReason.MAX_ITERATIONS.value
    assert record.iteration == 3
    assert provider.invocation_count == 3


def test_stops_at_max_sources(database: Database, tmp_path) -> None:
    many_candidates = [DiscoveryCandidate(url=f"https://example.com/{i}") for i in range(20)]
    discovery = ManualSourceDiscoveryProvider({"q": many_candidates})
    script = {i: WebResearchDecision(objective="o", reasoning_summary="discover", action=ResearchAction.DISCOVER_SOURCES, query="q") for i in range(10)}
    limits = WebResearchLimits(max_iterations=100, max_sources_per_session=5, max_requests_per_session=100)
    agent = _agent(database, MockWebResearchProvider(script), discovery=discovery, limits=limits, cache_dir=tmp_path / "cache")
    record = agent.run("o")

    assert record.stopping_reason == WebStoppingReason.MAX_SOURCES.value
    assert record.sources_discovered <= 5


def test_stops_at_max_requests(database: Database, tmp_path) -> None:
    urls = [f"https://example.com/{i}" for i in range(10)]
    script = {i: WebResearchDecision(objective="o", reasoning_summary="retrieve", action=ResearchAction.RETRIEVE_SOURCE, url=urls[i]) for i in range(10)}
    limits = WebResearchLimits(max_iterations=100, max_sources_per_session=100, max_requests_per_session=3)
    agent = _agent(database, MockWebResearchProvider(script), limits=limits, cache_dir=tmp_path / "cache")
    record = agent.run("o")

    assert record.stopping_reason == WebStoppingReason.MAX_REQUESTS.value
    assert record.requests_made <= 3


def test_provider_failure_does_not_crash_and_marks_session_failed(database: Database, tmp_path) -> None:
    class AlwaysFails(AIProvider):
        provider_name = "always_fails"
        model_name = "n/a"

        def invoke(self, request):
            raise AIProviderError("boom")

    agent = _agent(database, AlwaysFails(), cache_dir=tmp_path / "cache")
    record = agent.run("o")  # must not raise

    assert record.status is WebResearchSessionStatus.FAILED
    assert record.stopping_reason == WebStoppingReason.PROVIDER_ERROR.value
    assert record.iteration == 0


def test_retrieval_failure_is_recorded_not_fatal(database: Database, tmp_path) -> None:
    import urllib.error

    def failing_transport(url, user_agent, limits):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    discovery = ManualSourceDiscoveryProvider({})
    retriever = HttpSourceRetriever(RetrievalLimits(request_delay_seconds=0), transport=allow_all_robots_transport_wrapping(failing_transport))
    script = {0: WebResearchDecision(objective="o", reasoning_summary="retrieve", action=ResearchAction.RETRIEVE_SOURCE, url=URL, stopping_reason="done")}
    limits = WebResearchLimits(max_iterations=10, max_sources_per_session=10, max_requests_per_session=10)
    agent = WebResearchAgent(database, MockWebResearchProvider(script), discovery=discovery, retriever=retriever, limits=limits, cache_dir=tmp_path / "cache")

    record = agent.run("o")  # must not raise
    assert record.status is WebResearchSessionStatus.COMPLETED
    sources = rp.list_sources(database, record.id)
    assert sources[0]["status"] == "failed"
    assert "404" in (sources[0]["failure_reason"] or "")


def test_emits_full_lifecycle_events(database: Database, tmp_path) -> None:
    script = {
        0: WebResearchDecision(objective="o", reasoning_summary="discover", action=ResearchAction.DISCOVER_SOURCES, query="q"),
        1: WebResearchDecision(objective="o", reasoning_summary="retrieve", action=ResearchAction.RETRIEVE_SOURCE, url=URL, stopping_reason="done"),
    }
    agent = _agent(database, MockWebResearchProvider(script), cache_dir=tmp_path / "cache")
    record = agent.run("o")

    event_types = _events(database, record.id)
    assert event_types[0] == EventType.RESEARCH_SESSION_STARTED.value
    assert event_types[-1] == EventType.RESEARCH_SESSION_STOPPED.value
    for expected in (
        EventType.SOURCE_DISCOVERY_STARTED.value,
        EventType.SOURCE_DISCOVERY_COMPLETED.value,
        EventType.SOURCE_RETRIEVAL_STARTED.value,
        EventType.SOURCE_RETRIEVED.value,
        EventType.EVIDENCE_EXTRACTED.value,
    ):
        assert expected in event_types
