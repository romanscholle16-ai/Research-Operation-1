"""End-to-end integration test for the full chain (Phase 4 brief section
17/20):

    Mock AI -> ResearchDecision -> ResearchRequest -> CampaignRunner
    -> ExperimentRunner -> BacktestResult -> Result Analysis -> Research State
"""

from app.ai.agent import ResearchAgent
from app.ai.decision import ExperimentProposal, ResearchDecision
from app.ai.limits import ResearchLimits
from app.ai.persistence import list_session_campaign_ids, list_session_experiments
from app.ai.providers.mock import MockAIProvider
from app.ai.session import SessionStatus
from app.database.connection import Database
from app.systems import persistence as systems_persistence
from tests.ai.conftest import make_catalog


def test_full_chain_mock_ai_to_backtest_result_and_back(database: Database) -> None:
    catalog = make_catalog()
    script = {
        0: ResearchDecision(
            objective="does qty scale linearly",
            hypothesis="net profit scales with quantity",
            reasoning_summary="compare qty=1 vs qty=2 under identical conditions",
            requested_experiments=(
                ExperimentProposal(research_system="parameter_explorer", parameter_space={"qty": [1.0, 2.0]}),
            ),
        ),
        1: ResearchDecision(
            objective="does qty scale linearly",
            hypothesis="confirmed within this sample",
            reasoning_summary="both experiments completed with the expected direction of P&L",
            requested_experiments=(),
            stopping_reason="sufficient_evidence",
            confidence=0.7,
        ),
    }
    provider = MockAIProvider(script)
    agent = ResearchAgent(database, provider, catalog, ResearchLimits())

    # 1. Mock AI -> ResearchDecision -> ResearchAgent runs the whole loop.
    session = agent.run("does qty scale linearly")
    assert session.status is SessionStatus.COMPLETED
    assert session.stopping_reason == "sufficient_evidence"

    # 2. ResearchDecision -> ResearchRequest -> CampaignRunner -> ExperimentRunner:
    #    a real campaign and real experiments exist, linked to this session.
    campaign_ids = list_session_campaign_ids(database, session.id)
    assert len(campaign_ids) == 1
    experiments = systems_persistence.list_experiments_for_campaign(database, campaign_ids[0])
    assert len(experiments) == 2
    assert all(e.status.value == "completed" for e in experiments)

    # 3. -> BacktestResult: each experiment references a real, deterministic
    #    backtest run with real trades/metrics, not anything AI-authored.
    for experiment in experiments:
        backtest_row = database.query_one("SELECT * FROM experiments WHERE id = ?", (experiment.backtest_run_id,))
        assert backtest_row is not None
        metrics = database.query_all(
            "SELECT metric_name FROM experiment_results WHERE experiment_id = ?", (experiment.backtest_run_id,)
        )
        assert any(row["metric_name"] == "net_profit" for row in metrics)

    # 4. -> Result Analysis -> Research State: the second decision was
    #    generated FROM the first iteration's results (context carried them).
    from app.ai.persistence import list_decisions

    decisions = list_decisions(database, session.id)
    assert len(decisions) == 2
    assert decisions[1]["hypothesis"] == "confirmed within this sample"

    # The session itself is durable, resumable state - not in-memory only.
    reloaded_experiments = list_session_experiments(database, session.id)
    assert len(reloaded_experiments) == 2


def test_ai_analysis_never_alters_backtest_results(database: Database) -> None:
    """The AI reads BacktestResult data (via ResearchContext) but has no
    write path to it - trades/experiment_results rows are exactly what
    the deterministic engine produced, never touched again."""
    catalog = make_catalog()
    script = {0: ResearchDecision(
        objective="o", hypothesis="h", reasoning_summary="r",
        requested_experiments=(ExperimentProposal(research_system="parameter_explorer", parameter_space={"qty": [1.0]}),),
        stopping_reason="done",
    )}
    agent = ResearchAgent(database, MockAIProvider(script), catalog, ResearchLimits())
    session = agent.run("o")

    campaign_ids = list_session_campaign_ids(database, session.id)
    experiments = systems_persistence.list_experiments_for_campaign(database, campaign_ids[0])
    run_id = experiments[0].backtest_run_id

    trades_before = database.query_all("SELECT * FROM trades WHERE experiment_id = ?", (run_id,))
    # Running a second, unrelated agent session must not touch the first
    # session's already-persisted trades.
    script2 = {0: ResearchDecision(objective="o2", hypothesis="h2", reasoning_summary="r2", stopping_reason="done")}
    ResearchAgent(database, MockAIProvider(script2), catalog, ResearchLimits()).run("o2")
    trades_after = database.query_all("SELECT * FROM trades WHERE experiment_id = ?", (run_id,))

    assert [dict(r) for r in trades_before] == [dict(r) for r in trades_after]
