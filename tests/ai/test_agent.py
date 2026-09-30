from app.ai.agent import ResearchAgent
from app.ai.decision import ExperimentProposal, ResearchDecision
from app.ai.limits import ResearchLimits, StoppingReason
from app.ai.providers.mock import AlwaysFailingAIProvider, MockAIProvider
from app.ai.session import SessionStatus
from app.core.events import EventType
from app.database.connection import Database
from app.systems import persistence as systems_persistence
from tests.ai.conftest import make_catalog


def _qty_decision(qtys, *, stopping_reason=None, hypothesis="h") -> ResearchDecision:
    return ResearchDecision(
        objective="find qty",
        hypothesis=hypothesis,
        reasoning_summary="testing qty values",
        requested_experiments=(
            ExperimentProposal(research_system="parameter_explorer", parameter_space={"qty": qtys}),
        ),
        stopping_reason=stopping_reason,
    )


def _events(database: Database, session_id: str) -> list[str]:
    rows = database.query_all(
        "SELECT event_type FROM events WHERE related_id = ? ORDER BY created_at, rowid", (session_id,)
    )
    return [row["event_type"] for row in rows]


def test_agent_runs_one_iteration_and_stops_on_ai_request(database: Database) -> None:
    catalog = make_catalog()
    script = {0: _qty_decision([1.0, 2.0], stopping_reason="sufficient_evidence")}
    agent = ResearchAgent(database, MockAIProvider(script), catalog, ResearchLimits())

    record = agent.run("find qty")

    assert record.status is SessionStatus.COMPLETED
    assert record.stopping_reason == "sufficient_evidence"
    assert record.iteration == 1
    assert record.experiments_run == 2
    assert record.experiments_failed == 0


def test_agent_experiment_submitted_and_results_returned(database: Database) -> None:
    catalog = make_catalog()
    script = {0: _qty_decision([1.0], stopping_reason="done")}
    agent = ResearchAgent(database, MockAIProvider(script), catalog, ResearchLimits())
    record = agent.run("obj")

    from app.ai.persistence import list_session_experiments

    experiments = list_session_experiments(database, record.id)
    assert len(experiments) == 1
    assert experiments[0]["status"] == "completed"
    assert experiments[0]["backtest_run_id"] is not None

    backtest_row = database.query_one("SELECT * FROM experiments WHERE id = ?", (experiments[0]["backtest_run_id"],))
    assert backtest_row is not None  # the deterministic BacktestResult actually exists


def test_agent_generates_next_decision_from_previous_results(database: Database) -> None:
    catalog = make_catalog()
    script = {
        0: _qty_decision([1.0]),
        1: _qty_decision([2.0], stopping_reason="done"),
    }
    agent = ResearchAgent(database, MockAIProvider(script), catalog, ResearchLimits())
    record = agent.run("obj")
    assert record.iteration == 2
    assert record.experiments_run == 2


def test_agent_stops_at_max_iterations(database: Database) -> None:
    catalog = make_catalog()
    script = {i: _qty_decision([float(i + 1)]) for i in range(10)}  # never requests a stop itself
    limits = ResearchLimits(max_iterations=3, max_experiments=100, max_failed_experiments=100, max_consecutive_no_progress=100)
    provider = MockAIProvider(script)
    agent = ResearchAgent(database, provider, catalog, limits)

    record = agent.run("obj")

    assert record.stopping_reason == StoppingReason.MAX_ITERATIONS.value
    assert record.iteration == 3
    assert provider.invocation_count == 3  # never invoked a 4th time


def test_agent_stops_at_max_experiments(database: Database) -> None:
    catalog = make_catalog()
    script = {i: _qty_decision([1.0, 2.0, 3.0]) for i in range(10)}  # 3 experiments/iteration
    limits = ResearchLimits(max_iterations=100, max_experiments=5, max_failed_experiments=100, max_consecutive_no_progress=100)
    agent = ResearchAgent(database, MockAIProvider(script), catalog, limits)

    record = agent.run("obj")

    assert record.stopping_reason == StoppingReason.MAX_EXPERIMENTS.value
    assert record.experiments_run <= 5


def test_agent_stops_at_max_failed_experiments(database: Database) -> None:
    catalog = make_catalog()
    # Every proposal references a rule variant that doesn't exist -> always invalid -> always "failed".
    bad_decision = ResearchDecision(
        objective="obj", hypothesis="h", reasoning_summary="r",
        requested_experiments=(ExperimentProposal(research_system="rule_explorer", rule_variant_names=("nope",)),),
    )
    script = {i: bad_decision for i in range(20)}
    limits = ResearchLimits(max_iterations=100, max_experiments=100, max_failed_experiments=3, max_consecutive_no_progress=100)
    agent = ResearchAgent(database, MockAIProvider(script), catalog, limits)

    record = agent.run("obj")

    assert record.stopping_reason == StoppingReason.MAX_FAILED_EXPERIMENTS.value
    assert record.experiments_failed >= 3


def test_agent_stops_at_max_consecutive_no_progress(database: Database) -> None:
    catalog = make_catalog()
    # An empty requested_experiments list every iteration -> never progresses.
    empty_decision = ResearchDecision(objective="obj", hypothesis="h", reasoning_summary="r", requested_experiments=())
    script = {i: empty_decision for i in range(20)}
    limits = ResearchLimits(max_iterations=100, max_experiments=100, max_failed_experiments=100, max_consecutive_no_progress=2)
    agent = ResearchAgent(database, MockAIProvider(script), catalog, limits)

    record = agent.run("obj")

    assert record.stopping_reason == StoppingReason.MAX_CONSECUTIVE_NO_PROGRESS.value
    assert record.consecutive_no_progress >= 2


def test_agent_handles_provider_failure_without_corrupting_state(database: Database) -> None:
    catalog = make_catalog()
    agent = ResearchAgent(database, AlwaysFailingAIProvider(), catalog, ResearchLimits())

    record = agent.run("obj")  # must not raise

    assert record.status is SessionStatus.FAILED
    assert record.stopping_reason == StoppingReason.PROVIDER_ERROR.value
    assert record.iteration == 0


def test_agent_deduplicates_identical_experiments_across_iterations(database: Database) -> None:
    catalog = make_catalog()
    script = {
        0: _qty_decision([1.0]),
        1: _qty_decision([1.0], stopping_reason="done"),  # identical proposal
    }
    agent = ResearchAgent(database, MockAIProvider(script), catalog, ResearchLimits())
    record = agent.run("obj")

    backtest_rows = database.query_all("SELECT id FROM experiments")
    assert len(backtest_rows) == 1  # engine only ran once despite two proposed experiments


def test_agent_invalid_proposal_does_not_crash_and_counts_as_failed(database: Database) -> None:
    catalog = make_catalog()
    bad_decision = ResearchDecision(
        objective="obj", hypothesis="h", reasoning_summary="r",
        requested_experiments=(ExperimentProposal(research_system="not_real"),),
        stopping_reason="done",
    )
    agent = ResearchAgent(database, MockAIProvider({0: bad_decision}), catalog, ResearchLimits())

    record = agent.run("obj")  # must not raise

    assert record.experiments_failed == 1
    assert record.experiments_run == 0


def test_agent_emits_full_lifecycle_events(database: Database) -> None:
    catalog = make_catalog()
    script = {0: _qty_decision([1.0], stopping_reason="done")}
    agent = ResearchAgent(database, MockAIProvider(script), catalog, ResearchLimits())
    record = agent.run("obj")

    event_types = _events(database, record.id)
    assert event_types[0] == EventType.AI_RESEARCH_STARTED.value
    assert event_types[-1] == EventType.AI_RESEARCH_STOPPED.value
    for expected in (
        EventType.AI_INVOCATION_STARTED.value,
        EventType.AI_INVOCATION_COMPLETED.value,
        EventType.RESEARCH_DECISION_CREATED.value,
        EventType.RESEARCH_EXPERIMENT_REQUESTED.value,
        EventType.RESEARCH_ANALYSIS_COMPLETED.value,
    ):
        assert expected in event_types


def test_agent_records_ai_actions_for_audit(database: Database) -> None:
    catalog = make_catalog()
    script = {0: _qty_decision([1.0], stopping_reason="done")}
    agent = ResearchAgent(database, MockAIProvider(script), catalog, ResearchLimits())
    record = agent.run("obj")

    rows = database.query_all("SELECT * FROM ai_actions WHERE related_id = ?", (record.id,))
    assert len(rows) == 1
    assert rows[0]["provider"] == "mock"
    assert rows[0]["action_type"] == "propose_experiments"


def test_agent_links_campaigns_to_session(database: Database) -> None:
    catalog = make_catalog()
    script = {0: _qty_decision([1.0], stopping_reason="done")}
    agent = ResearchAgent(database, MockAIProvider(script), catalog, ResearchLimits())
    record = agent.run("obj")

    from app.ai.persistence import list_session_campaign_ids

    campaign_ids = list_session_campaign_ids(database, record.id)
    assert len(campaign_ids) == 1
    campaign_experiments = systems_persistence.list_experiments_for_campaign(database, campaign_ids[0])
    assert len(campaign_experiments) == 1
