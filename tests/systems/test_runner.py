from app.backtesting.engine import BacktestConfig
from app.backtesting.market_data import Timeframe
from app.core.events import EventType
from app.database.connection import Database
from app.systems import persistence
from app.systems.campaign import CampaignStatus, new_campaign_id
from app.systems.experiment import ExperimentDefinition, ExperimentStatus
from app.systems.runner import ExperimentRunner
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
        parameters={"qty": 2.0},
        candles=build_series(ROWS),
        execution_config=BacktestConfig(symbol="TEST/USDT", timeframe=Timeframe.M1, starting_capital=10_000.0),
    )
    defaults.update(overrides)
    return ExperimentDefinition(**defaults)


def _events(database: Database, experiment_id: str) -> list[str]:
    rows = database.query_all(
        "SELECT event_type FROM events WHERE related_id = ? ORDER BY created_at, rowid", (experiment_id,)
    )
    return [row["event_type"] for row in rows]


def test_execute_happy_path(database: Database) -> None:
    definition = _definition()
    record = ExperimentRunner(database).execute(definition)

    assert record.status is ExperimentStatus.COMPLETED
    assert record.backtest_run_id is not None
    assert record.fingerprint

    backtest_row = database.query_one("SELECT * FROM experiments WHERE id = ?", (record.backtest_run_id,))
    assert backtest_row is not None

    trade_rows = database.query_all("SELECT quantity FROM trades WHERE experiment_id = ?", (record.backtest_run_id,))
    assert len(trade_rows) == 1
    assert trade_rows[0]["quantity"] == 2.0  # confirms definition.parameters reached the strategy AND the engine

    assert _events(database, definition.id) == [
        EventType.EXPERIMENT_CREATED.value,
        EventType.EXPERIMENT_STARTED.value,
        EventType.EXPERIMENT_COMPLETED.value,
    ]


def test_execute_second_identical_experiment_is_deduplicated(database: Database) -> None:
    runner = ExperimentRunner(database)
    first = runner.execute(_definition())
    second = runner.execute(_definition())  # fresh id, same everything else

    assert second.status is ExperimentStatus.COMPLETED
    assert second.duplicate_of_experiment_id == first.id
    assert second.backtest_run_id == first.backtest_run_id

    backtest_rows = database.query_all("SELECT id FROM experiments")
    assert len(backtest_rows) == 1  # the engine was NOT invoked a second time

    assert _events(database, second.id) == [
        EventType.EXPERIMENT_CREATED.value,
        EventType.EXPERIMENT_SKIPPED_DUPLICATE.value,
    ]


def test_execute_different_parameters_are_not_deduplicated(database: Database) -> None:
    runner = ExperimentRunner(database)
    first = runner.execute(_definition(parameters={"qty": 1.0}))
    second = runner.execute(_definition(parameters={"qty": 2.0}))

    assert second.duplicate_of_experiment_id is None
    assert second.backtest_run_id != first.backtest_run_id
    assert database.query_all("SELECT id FROM experiments") and len(database.query_all("SELECT id FROM experiments")) == 2


def test_execute_records_failure_without_raising(database: Database) -> None:
    definition = _definition(strategy_factory=lambda p: AlwaysFailsStrategy(p), strategy_name="always_fails")
    record = ExperimentRunner(database).execute(definition)  # must not raise

    assert record.status is ExperimentStatus.FAILED
    assert record.backtest_run_id is None
    assert "intentional failure for testing" in record.failure_info

    assert _events(database, definition.id) == [
        EventType.EXPERIMENT_CREATED.value,
        EventType.EXPERIMENT_STARTED.value,
        EventType.EXPERIMENT_FAILED.value,
    ]


def test_execute_refreshes_campaign_counts(database: Database) -> None:
    campaign_id = new_campaign_id()
    persistence.create_campaign(
        database, campaign_id=campaign_id, strategy_name="fixed_trade", research_system="parameter_explorer",
        purpose="test", configuration={},
    )
    ExperimentRunner(database).execute(_definition(), campaign_id=campaign_id)

    campaign = persistence.load_campaign(database, campaign_id)
    assert campaign.experiment_count == 1
    assert campaign.completed_count == 1
    assert campaign.failed_count == 0
