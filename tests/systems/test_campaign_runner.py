from app.backtesting.engine import BacktestConfig
from app.backtesting.market_data import Timeframe
from app.core.events import EventType
from app.database.connection import Database
from app.systems import persistence
from app.systems.campaign import CampaignStatus
from app.systems.experiment import ExperimentDefinition, ExperimentStatus
from app.systems.runner import CampaignRunner
from tests.fixtures.mock_strategies import AlwaysFailsStrategy, FixedTradeStrategy
from tests.fixtures.synthetic_data import build_series

ROWS = [
    (100, 101, 99, 100, 1000),
    (100, 105, 100, 104, 1000),
    (104, 110, 103, 108, 1000),
    (108, 109, 107, 108, 1000),
]


def _definition(**overrides) -> ExperimentDefinition:
    defaults = dict(
        research_system="parameter_explorer",
        strategy_name="fixed_trade",
        strategy_version="1",
        strategy_factory=lambda p: FixedTradeStrategy(p),
        parameters={"qty": 1.0},
        candles=build_series(ROWS),
        execution_config=BacktestConfig(symbol="TEST/USDT", timeframe=Timeframe.M1, starting_capital=10_000.0),
    )
    defaults.update(overrides)
    return ExperimentDefinition(**defaults)


def test_campaign_run_with_all_successful_experiments(database: Database) -> None:
    definitions = [_definition(parameters={"qty": q}) for q in (1.0, 2.0, 3.0)]
    record = CampaignRunner(database).run(
        definitions, research_system="parameter_explorer", strategy_name="fixed_trade", purpose="sweep qty"
    )

    assert record.status is CampaignStatus.COMPLETED
    assert record.experiment_count == 3
    assert record.completed_count == 3
    assert record.failed_count == 0
    assert record.started_at is not None
    assert record.completed_at is not None

    experiments = persistence.list_experiments_for_campaign(database, record.id)
    assert len(experiments) == 3
    assert all(e.status is ExperimentStatus.COMPLETED for e in experiments)
    assert all(e.campaign_id == record.id for e in experiments)


def test_campaign_run_with_mixed_success_and_failure(database: Database) -> None:
    definitions = [
        _definition(parameters={"qty": 1.0}),
        _definition(strategy_factory=lambda p: AlwaysFailsStrategy(p), strategy_name="always_fails"),
        _definition(parameters={"qty": 3.0}),
    ]
    record = CampaignRunner(database).run(
        definitions, research_system="parameter_explorer", strategy_name="fixed_trade", purpose="mixed"
    )
    assert record.experiment_count == 3
    assert record.completed_count == 2
    assert record.failed_count == 1


def test_campaign_emits_lifecycle_events(database: Database) -> None:
    definitions = [_definition()]
    record = CampaignRunner(database).run(
        definitions, research_system="parameter_explorer", strategy_name="fixed_trade", purpose="events"
    )
    rows = database.query_all(
        "SELECT event_type FROM events WHERE related_id = ? ORDER BY created_at, rowid", (record.id,)
    )
    event_types = [row["event_type"] for row in rows]
    assert event_types == [
        EventType.CAMPAIGN_CREATED.value,
        EventType.CAMPAIGN_STARTED.value,
        EventType.CAMPAIGN_COMPLETED.value,
    ]


def test_campaign_deduplicates_across_experiments_in_the_same_campaign(database: Database) -> None:
    # Two definitions with identical configuration (e.g. an accidental
    # duplicate parameter combination) should only invoke the engine once.
    definitions = [_definition(parameters={"qty": 1.0}), _definition(parameters={"qty": 1.0})]
    record = CampaignRunner(database).run(
        definitions, research_system="parameter_explorer", strategy_name="fixed_trade", purpose="dup"
    )
    assert record.completed_count == 2  # both experiments still complete...
    backtest_rows = database.query_all("SELECT id FROM experiments")
    assert len(backtest_rows) == 1  # ...but only one actual backtest ran

    experiments = persistence.list_experiments_for_campaign(database, record.id)
    duplicate_flags = sorted(e.duplicate_of_experiment_id is not None for e in experiments)
    assert duplicate_flags == [False, True]
