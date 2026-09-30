import json

from app.ai import persistence as ai_persistence
from app.ai.decision import ExperimentProposal, ResearchDecision
from app.ai.limits import ResearchLimits
from app.ai.session import SessionStatus, new_session_id
from app.database.connection import Database
from app.database.schema import CURRENT_SCHEMA_VERSION


def test_migration_4_creates_ai_research_tables(database: Database) -> None:
    assert CURRENT_SCHEMA_VERSION >= 4
    versions = {row["version"] for row in database.query_all("SELECT version FROM schema_migrations")}
    assert 4 in versions

    tables = {row["name"] for row in database.query_all("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"ai_research_sessions", "ai_research_decisions", "ai_research_session_campaigns"}.issubset(tables)


def test_create_and_load_session(database: Database) -> None:
    session_id = new_session_id()
    limits = ResearchLimits(max_iterations=7, max_experiments=42, max_failed_experiments=4, max_consecutive_no_progress=2)
    ai_persistence.create_session(
        database, session_id=session_id, objective="find edge", limits=limits, provider_name="mock", model_name="mock-v1"
    )
    record = ai_persistence.load_session(database, session_id)
    assert record is not None
    assert record.status is SessionStatus.CREATED
    assert record.objective == "find edge"
    assert record.max_iterations == 7
    assert record.max_experiments == 42
    assert record.provider_name == "mock"
    assert record.model_name == "mock-v1"


def test_set_session_status_records_timestamps(database: Database) -> None:
    session_id = new_session_id()
    ai_persistence.create_session(
        database, session_id=session_id, objective="o", limits=ResearchLimits(), provider_name="mock", model_name="mock"
    )
    ai_persistence.set_session_status(database, session_id, SessionStatus.RUNNING, started=True)
    record = ai_persistence.load_session(database, session_id)
    assert record.status is SessionStatus.RUNNING
    assert record.started_at is not None
    assert record.completed_at is None

    ai_persistence.set_session_status(
        database, session_id, SessionStatus.COMPLETED, completed=True, stopping_reason="max_iterations"
    )
    record = ai_persistence.load_session(database, session_id)
    assert record.status is SessionStatus.COMPLETED
    assert record.completed_at is not None
    assert record.stopping_reason == "max_iterations"


def test_completed_and_failed_sessions_are_distinguishable(database: Database) -> None:
    completed_id, failed_id = new_session_id(), new_session_id()
    for sid in (completed_id, failed_id):
        ai_persistence.create_session(
            database, session_id=sid, objective="o", limits=ResearchLimits(), provider_name="mock", model_name="mock"
        )
    ai_persistence.set_session_status(database, completed_id, SessionStatus.COMPLETED, completed=True, stopping_reason="max_iterations")
    ai_persistence.set_session_status(database, failed_id, SessionStatus.FAILED, completed=True, stopping_reason="provider_error")

    assert ai_persistence.load_session(database, completed_id).status is SessionStatus.COMPLETED
    assert ai_persistence.load_session(database, failed_id).status is SessionStatus.FAILED


def test_update_session_progress(database: Database) -> None:
    session_id = new_session_id()
    ai_persistence.create_session(
        database, session_id=session_id, objective="o", limits=ResearchLimits(), provider_name="mock", model_name="mock"
    )
    ai_persistence.update_session_progress(
        database, session_id, iteration=3, experiments_run=12, experiments_failed=2, consecutive_no_progress=1
    )
    record = ai_persistence.load_session(database, session_id)
    assert record.iteration == 3
    assert record.experiments_run == 12
    assert record.experiments_failed == 2
    assert record.consecutive_no_progress == 1


def test_record_and_list_decisions(database: Database) -> None:
    session_id = new_session_id()
    ai_persistence.create_session(
        database, session_id=session_id, objective="o", limits=ResearchLimits(), provider_name="mock", model_name="mock"
    )
    decision = ResearchDecision(
        objective="o", hypothesis="qty matters", reasoning_summary="testing",
        requested_experiments=(ExperimentProposal(research_system="parameter_explorer", parameter_space={"qty": [1, 2]}),),
        confidence=0.6,
    )
    ai_persistence.record_decision(database, session_id=session_id, iteration=0, decision=decision)

    rows = ai_persistence.list_decisions(database, session_id)
    assert len(rows) == 1
    assert rows[0]["hypothesis"] == "qty matters"
    assert rows[0]["confidence"] == 0.6
    parsed = json.loads(rows[0]["requested_experiments"])
    assert parsed[0]["research_system"] == "parameter_explorer"
    assert parsed[0]["parameter_space"] == {"qty": [1, 2]}


def test_link_and_list_session_campaigns(database: Database) -> None:
    session_id = new_session_id()
    ai_persistence.create_session(
        database, session_id=session_id, objective="o", limits=ResearchLimits(), provider_name="mock", model_name="mock"
    )
    database.execute(
        "INSERT INTO research_campaigns (id, research_system, purpose) VALUES ('camp-1', 'x', 'p')"
    )
    ai_persistence.link_campaign_to_session(database, session_id=session_id, campaign_id="camp-1", iteration=0)

    campaign_ids = ai_persistence.list_session_campaign_ids(database, session_id)
    assert campaign_ids == ["camp-1"]


def test_record_ai_action_reuses_phase1_table(database: Database) -> None:
    ai_persistence.record_ai_action(
        database, provider="mock", action_type="propose_experiments", related_id="session-1",
        prompt_summary="ctx", result_summary="ok", metadata={"model": "mock-v1"},
    )
    rows = database.query_all("SELECT * FROM ai_actions WHERE related_id = 'session-1'")
    assert len(rows) == 1
    assert rows[0]["provider"] == "mock"
    assert rows[0]["action_type"] == "propose_experiments"
    assert json.loads(rows[0]["metadata"]) == {"model": "mock-v1"}
