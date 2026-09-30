from __future__ import annotations

from app.ai.catalog import ResearchCatalog
from app.backtesting.engine import BacktestConfig
from app.backtesting.market_data import Timeframe
from app.systems.risk_execution import ExecutionVariant
from app.systems.rule_explorer import RuleVariant
from tests.fixtures.mock_strategies import FixedTradeStrategy
from tests.fixtures.synthetic_data import build_series

ROWS = [
    (100, 101, 99, 100, 1000),
    (100, 105, 100, 104, 1000),
    (104, 110, 103, 108, 1000),
    (108, 109, 107, 108, 1000),
]


def make_catalog(**overrides) -> ResearchCatalog:
    defaults = dict(
        strategy_name="fixed_trade",
        strategy_version="1",
        strategy_factory=lambda p: FixedTradeStrategy(p),
        candles=build_series(ROWS),
        execution_config=BacktestConfig(symbol="TEST/USDT", timeframe=Timeframe.M1, starting_capital=10_000.0),
        rule_variants={
            "long_only": RuleVariant(name="long_only", strategy_factory=lambda p: FixedTradeStrategy({"side": "long"})),
            "short_only": RuleVariant(name="short_only", strategy_factory=lambda p: FixedTradeStrategy({"side": "short"})),
        },
        execution_variants={
            "baseline": ExecutionVariant(name="baseline"),
        },
    )
    defaults.update(overrides)
    return ResearchCatalog(**defaults)
