import json

from app.database.connection import Database
from app.database.schema import CURRENT_SCHEMA_VERSION
from app.research import persistence as rp
from app.research.evidence import EvidenceItem, EvidenceStatus
from app.research.limits import WebResearchLimits
from app.research.session import WebResearchSessionStatus, new_web_session_id
from app.research.source import Source, SourceStatus
from app.research.specification import StrategySpecification


def test_migration_5_creates_web_research_tables(database: Database) -> None:
    assert CURRENT_SCHEMA_VERSION >= 5
    versions = {row["version"] for row in database.query_all("SELECT version FROM schema_migrations")}
    assert 5 in versions
    tables = {row["name"] for row in database.query_all("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "web_research_sessions", "web_sources", "web_evidence",
        "web_strategy_specifications", "web_research_decisions",
    }.issubset(tables)


def test_create_and_load_session(database: Database) -> None:
    session_id = new_web_session_id()
    limits = WebResearchLimits(max_iterations=5, max_sources_per_session=10, max_requests_per_session=15)
    rp.create_session(database, session_id=session_id, objective="find strategies", limits=limits, provider_name="mock", model_name="mock-v1")
    record = rp.load_session(database, session_id)
    assert record is not None
    assert record.status is WebResearchSessionStatus.CREATED
    assert record.objective == "find strategies"


def test_set_session_status_and_progress(database: Database) -> None:
    session_id = new_web_session_id()
    rp.create_session(database, session_id=session_id, objective="o", limits=WebResearchLimits(), provider_name="mock", model_name="mock")
    rp.set_session_status(database, session_id, WebResearchSessionStatus.RUNNING, started=True)
    rp.update_session_progress(database, session_id, iteration=2, sources_discovered=3, sources_retrieved=1, evidence_count=5, specification_count=1, requests_made=2)

    record = rp.load_session(database, session_id)
    assert record.status is WebResearchSessionStatus.RUNNING
    assert record.started_at is not None
    assert record.iteration == 2
    assert record.sources_discovered == 3
    assert record.requests_made == 2

    rp.set_session_status(database, session_id, WebResearchSessionStatus.COMPLETED, completed=True, stopping_reason="max_iterations", final_specification_status="incomplete")
    record = rp.load_session(database, session_id)
    assert record.status is WebResearchSessionStatus.COMPLETED
    assert record.stopping_reason == "max_iterations"
    assert record.final_specification_status == "incomplete"


def test_save_and_upsert_source_by_id(database: Database) -> None:
    session_id = new_web_session_id()
    rp.create_session(database, session_id=session_id, objective="o", limits=WebResearchLimits(), provider_name="mock", model_name="mock")

    source = Source(url="https://example.com/a", status=SourceStatus.DISCOVERED)
    rp.save_source(database, session_id, source)

    import dataclasses
    updated = dataclasses.replace(source, status=SourceStatus.RETRIEVED, content_hash="abc123")
    rp.save_source(database, session_id, updated)  # same id - must update, not insert a second row

    rows = rp.list_sources(database, session_id)
    assert len(rows) == 1
    assert rows[0]["status"] == "retrieved"
    assert rows[0]["content_hash"] == "abc123"


def test_save_and_list_evidence(database: Database) -> None:
    session_id = new_web_session_id()
    rp.create_session(database, session_id=session_id, objective="o", limits=WebResearchLimits(), provider_name="mock", model_name="mock")
    source = Source(url="https://example.com/a")
    rp.save_source(database, session_id, source)

    item = EvidenceItem(source_id=source.id, claim="entry", status=EvidenceStatus.EXPLICIT, quoted_text="Entry on breakout.")
    rp.save_evidence(database, session_id, item)

    rows = rp.list_evidence(database, session_id)
    assert len(rows) == 1
    assert rows[0]["claim"] == "entry"
    assert rows[0]["quoted_text"] == "Entry on breakout."

    by_source = rp.list_evidence(database, session_id, source_id=source.id)
    assert len(by_source) == 1


def test_save_specification_is_append_only_history(database: Database) -> None:
    session_id = new_web_session_id()
    rp.create_session(database, session_id=session_id, objective="o", limits=WebResearchLimits(), provider_name="mock", model_name="mock")

    spec_v1 = StrategySpecification(name="s")
    rp.save_specification(database, session_id, spec_v1)

    import dataclasses
    spec_v2 = dataclasses.replace(spec_v1, timeframe="1h")
    rp.save_specification(database, session_id, spec_v2)

    rows = rp.list_specifications(database, session_id)
    assert len(rows) == 2  # both revisions kept
    latest = json.loads(rows[-1]["specification"])
    assert latest["timeframe"] == "1h"


def test_record_and_list_decisions(database: Database) -> None:
    session_id = new_web_session_id()
    rp.create_session(database, session_id=session_id, objective="o", limits=WebResearchLimits(), provider_name="mock", model_name="mock")
    rp.record_decision(database, session_id=session_id, iteration=0, action="discover_sources", reasoning_summary="looking", details={"query": "q"}, stopping_reason=None)

    rows = rp.list_decisions(database, session_id)
    assert len(rows) == 1
    assert rows[0]["action"] == "discover_sources"
    assert json.loads(rows[0]["details"]) == {"query": "q"}
