import dataclasses

from app.backtesting.costs import PercentageFeeModel
from app.backtesting.engine import BacktestConfig
from app.backtesting.market_data import Timeframe
from app.backtesting.result import compute_data_identity
from app.systems.experiment import ExperimentDefinition
from app.systems.fingerprint import compute_experiment_fingerprint
from tests.fixtures.mock_strategies import FixedTradeStrategy
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
        rule_configuration={},
    )
    defaults.update(overrides)
    return ExperimentDefinition(**defaults)


def test_fingerprint_ignores_experiment_id() -> None:
    fp1, _ = compute_experiment_fingerprint(_definition())
    fp2, _ = compute_experiment_fingerprint(_definition())  # fresh id each time (default_factory)
    assert fp1 == fp2


def test_fingerprint_changes_with_parameters() -> None:
    fp1, _ = compute_experiment_fingerprint(_definition(parameters={"qty": 1.0}))
    fp2, _ = compute_experiment_fingerprint(_definition(parameters={"qty": 2.0}))
    assert fp1 != fp2


def test_fingerprint_changes_with_rule_configuration() -> None:
    fp1, _ = compute_experiment_fingerprint(_definition(rule_configuration={}))
    fp2, _ = compute_experiment_fingerprint(_definition(rule_configuration={"variant_name": "b"}))
    assert fp1 != fp2


def test_fingerprint_changes_with_execution_assumptions() -> None:
    base_config = BacktestConfig(symbol="TEST/USDT", timeframe=Timeframe.M1, starting_capital=10_000.0)
    fee_config = dataclasses.replace(base_config, fee_model=PercentageFeeModel(rate=0.001))
    fp1, _ = compute_experiment_fingerprint(_definition(execution_config=base_config))
    fp2, _ = compute_experiment_fingerprint(_definition(execution_config=fee_config))
    assert fp1 != fp2


def test_fingerprint_changes_with_data() -> None:
    series_a = build_series(ROWS)
    series_b = build_series(ROWS[:-1] + [(108, 120, 107, 115, 1000)])
    fp1, _ = compute_experiment_fingerprint(_definition(candles=series_a))
    fp2, _ = compute_experiment_fingerprint(_definition(candles=series_b))
    assert fp1 != fp2


def test_fingerprint_changes_with_research_system() -> None:
    fp1, _ = compute_experiment_fingerprint(_definition(research_system="parameter_explorer"))
    fp2, _ = compute_experiment_fingerprint(_definition(research_system="adversarial"))
    assert fp1 != fp2


def test_data_identity_matches_backtesting_engine() -> None:
    series = build_series(ROWS)
    _, data_identity = compute_experiment_fingerprint(_definition(candles=series))
    assert data_identity == compute_data_identity(series)
