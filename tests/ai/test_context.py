from app.ai.context import build_research_context
from app.ai.limits import ResearchLimits
from app.ai.persistence import create_session, link_campaign_to_session
from app.ai.session import new_session_id
from app.database.connection import Database
from app.systems.experiment import ExperimentDefinition
from app.systems.runner import CampaignRunner
from tests.ai.conftest import make_catalog


def _context(database: Database, *, previous_hypotheses=None, **overrides):
    catalog = make_catalog()
    limits = ResearchLimits()
    session_id = new_session_id()
    create_session(
        database, session_id=session_id, objective="test", limits=limits, provider_name="mock", model_name="mock"
    )
    defaults = dict(
        session_id=session_id,
        objective="test objective",
        iteration=0,
        catalog=catalog,
        limits=limits,
        previous_hypotheses=previous_hypotheses or [],
        experiments_run=0,
        experiments_failed=0,
        consecutive_no_progress=0,
    )
    defaults.update(overrides)
    return build_research_context(database, **defaults)


def test_context_exposes_strategy_and_catalog_identity(database: Database) -> None:
    context = _context(database)
    assert context.strategy_name == "fixed_trade"
    assert context.strategy_version == "1"
    assert context.timeframe == "1m"
    assert context.data_identity


def test_context_exposes_available_systems_and_catalog_names(database: Database) -> None:
    context = _context(database)
    assert set(context.available_research_systems) == {
        "parameter_explorer", "rule_explorer", "risk_execution", "market_conditions", "adversarial",
    }
    assert set(context.available_rule_variant_names) == {"long_only", "short_only"}
    assert set(context.available_execution_variant_names) == {"baseline"}


def test_context_carries_limits_as_plain_values(database: Database) -> None:
    context = _context(database, limits=ResearchLimits(max_iterations=7))
    assert context.limits["max_iterations"] == 7


def test_context_no_previous_experiments_on_first_iteration(database: Database) -> None:
    context = _context(database)
    assert context.previous_experiments == ()


def test_context_summary_is_bounded(database: Database) -> None:
    context = _context(database, previous_hypotheses=["h" * 5000])
    summary = context.summary(max_chars=200)
    assert len(summary) <= 200


def test_context_summary_never_dumps_full_trade_data(database: Database) -> None:
    context = _context(database)
    summary = context.summary()
    assert "entry_price" not in summary
    assert "exit_price" not in summary


def test_context_includes_bounded_metrics_from_completed_experiments(database: Database) -> None:
    catalog = make_catalog()
    limits = ResearchLimits()
    session_id = new_session_id()
    create_session(database, session_id=session_id, objective="t", limits=limits, provider_name="mock", model_name="mock")

    definition = ExperimentDefinition(
        research_system="parameter_explorer",
        strategy_name=catalog.strategy_name,
        strategy_version=catalog.strategy_version,
        strategy_factory=catalog.strategy_factory,
        parameters={"qty": 1.0},
        candles=catalog.candles,
        execution_config=catalog.execution_config,
    )
    campaign = CampaignRunner(database).run(
        [definition], research_system="parameter_explorer", strategy_name=catalog.strategy_name, purpose="p"
    )
    link_campaign_to_session(database, session_id=session_id, campaign_id=campaign.id, iteration=0)

    context = build_research_context(
        database, session_id=session_id, objective="t", iteration=1, catalog=catalog, limits=limits,
        previous_hypotheses=["h0"], experiments_run=1, experiments_failed=0, consecutive_no_progress=0,
    )
    assert len(context.previous_experiments) == 1
    summary = context.previous_experiments[0]
    assert summary.research_system == "parameter_explorer"
    assert summary.status == "completed"
    assert summary.net_profit is not None  # a real metric pulled via Phase 2's load_experiment_metrics
    assert summary.parameters == {"qty": 1.0}
