import pytest

from app.backtesting.costs import FixedBpsSlippageModel, PercentageFeeModel, ZeroFeeModel
from app.backtesting.engine import BacktestConfig
from app.backtesting.intrabar import IntrabarPolicy
from app.backtesting.market_data import Timeframe
from app.systems.risk_execution import ExecutionVariant, RiskExecutionOptimizer, RiskExecutionRequest
from tests.fixtures.mock_strategies import FixedTradeStrategy
from tests.fixtures.synthetic_data import build_series

ROWS = [
    (100, 101, 99, 100, 1000),
    (100, 105, 100, 104, 1000),
    (104, 110, 103, 108, 1000),
    (108, 109, 107, 108, 1000),
]


def _base_config() -> BacktestConfig:
    return BacktestConfig(
        symbol="TEST/USDT", timeframe=Timeframe.M1, starting_capital=10_000.0, fee_model=ZeroFeeModel()
    )


def _request(variants, **overrides) -> RiskExecutionRequest:
    defaults = dict(
        strategy_name="fixed_trade",
        strategy_version="1",
        strategy_factory=lambda p: FixedTradeStrategy(p),
        candles=build_series(ROWS),
        execution_config=_base_config(),
        variants=variants,
    )
    defaults.update(overrides)
    return RiskExecutionRequest(**defaults)


def test_one_experiment_per_variant() -> None:
    variants = (
        ExecutionVariant(name="realistic_fees", fee_model=PercentageFeeModel(rate=0.001)),
        ExecutionVariant(name="worse_slippage", slippage_model=FixedBpsSlippageModel(bps=20)),
    )
    experiments = RiskExecutionOptimizer().generate_experiments(_request(variants))
    assert len(experiments) == 2


def test_variant_overrides_only_the_fields_it_specifies() -> None:
    variant = ExecutionVariant(name="realistic_fees", fee_model=PercentageFeeModel(rate=0.001))
    experiments = RiskExecutionOptimizer().generate_experiments(_request((variant,)))
    config = experiments[0].execution_config
    assert isinstance(config.fee_model, PercentageFeeModel)
    assert config.fee_model.rate == 0.001
    # everything else inherited from the base config, untouched
    assert config.starting_capital == 10_000.0
    assert config.intrabar_policy is IntrabarPolicy.STOP_FIRST
    assert config.symbol == "TEST/USDT"


def test_variant_can_override_multiple_fields() -> None:
    variant = ExecutionVariant(
        name="stress",
        fee_model=PercentageFeeModel(rate=0.002),
        slippage_model=FixedBpsSlippageModel(bps=50),
        intrabar_policy=IntrabarPolicy.TARGET_FIRST,
        starting_capital=5_000.0,
    )
    experiments = RiskExecutionOptimizer().generate_experiments(_request((variant,)))
    config = experiments[0].execution_config
    assert config.fee_model.rate == 0.002
    assert config.slippage_model.bps == 50
    assert config.intrabar_policy is IntrabarPolicy.TARGET_FIRST
    assert config.starting_capital == 5_000.0


def test_rule_configuration_records_variant_name() -> None:
    variant = ExecutionVariant(name="realistic_fees", description="binance-like taker fee")
    experiments = RiskExecutionOptimizer().generate_experiments(_request((variant,)))
    assert experiments[0].rule_configuration == {
        "execution_variant": "realistic_fees",
        "description": "binance-like taker fee",
    }


def test_requires_at_least_one_variant() -> None:
    with pytest.raises(ValueError):
        _request(())
