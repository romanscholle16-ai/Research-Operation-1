import pytest

from app.backtesting.engine import BacktestConfig
from app.backtesting.market_data import Timeframe
from app.systems.rule_explorer import RuleExplorer, RuleExplorerRequest, RuleVariant
from tests.fixtures.mock_strategies import FixedTradeStrategy
from tests.fixtures.synthetic_data import build_series

ROWS = [
    (100, 101, 99, 100, 1000),
    (100, 105, 100, 104, 1000),
    (104, 110, 103, 108, 1000),
    (108, 109, 107, 108, 1000),
]


def _variants() -> tuple[RuleVariant, ...]:
    return (
        RuleVariant(
            name="long_only",
            strategy_factory=lambda p: FixedTradeStrategy({"side": "long"}),
            description="always enter long",
        ),
        RuleVariant(
            name="short_only",
            strategy_factory=lambda p: FixedTradeStrategy({"side": "short"}),
            description="always enter short",
            metadata={"confirmation": "none"},
        ),
    )


def _request(**overrides) -> RuleExplorerRequest:
    defaults = dict(
        strategy_name="fixed_trade",
        strategy_version="1",
        strategy_factory=lambda p: FixedTradeStrategy(p),  # unused per-experiment; variants override
        candles=build_series(ROWS),
        execution_config=BacktestConfig(symbol="TEST/USDT", timeframe=Timeframe.M1, starting_capital=10_000.0),
        variants=_variants(),
    )
    defaults.update(overrides)
    return RuleExplorerRequest(**defaults)


def test_one_experiment_per_variant() -> None:
    experiments = RuleExplorer().generate_experiments(_request())
    assert len(experiments) == 2


def test_rule_configuration_identifies_the_variant() -> None:
    experiments = RuleExplorer().generate_experiments(_request())
    labels = {e.rule_configuration["variant_name"] for e in experiments}
    assert labels == {"long_only", "short_only"}
    short_exp = next(e for e in experiments if e.rule_configuration["variant_name"] == "short_only")
    assert short_exp.rule_configuration["confirmation"] == "none"
    assert short_exp.rule_configuration["description"] == "always enter short"


def test_each_variant_uses_its_own_strategy_factory_not_the_default() -> None:
    experiments = RuleExplorer().generate_experiments(_request())
    long_exp = next(e for e in experiments if e.rule_configuration["variant_name"] == "long_only")
    short_exp = next(e for e in experiments if e.rule_configuration["variant_name"] == "short_only")
    assert long_exp.build_strategy().side == "long"
    assert short_exp.build_strategy().side == "short"


def test_requires_at_least_one_variant() -> None:
    with pytest.raises(ValueError):
        _request(variants=())
