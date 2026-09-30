"""Deterministic, reusable backtesting engine.

The quantitative source of truth for the whole project (see
ARCHITECTURE.md "Core principle"): given the same market data, strategy,
parameters, and execution assumptions, `run_backtest` always produces the
same `BacktestResult`. No AI involvement anywhere in this package.
"""

from app.backtesting.costs import (
    FeeModel,
    FixedBpsSlippageModel,
    PercentageFeeModel,
    SlippageModel,
    ZeroFeeModel,
    ZeroSlippageModel,
)
from app.backtesting.engine import BacktestConfig, LookAheadError, run_backtest
from app.backtesting.intrabar import IntrabarPolicy
from app.backtesting.market_data import Candle, CandleSeries, Timeframe
from app.backtesting.metrics import PerformanceMetrics
from app.backtesting.positions import Position, Side
from app.backtesting.result import BacktestResult
from app.backtesting.signals import OrderType, Signal, SignalAction
from app.backtesting.strategy import Strategy, StrategyContext
from app.backtesting.trades import ExitReason, Trade

__all__ = [
    "BacktestConfig",
    "BacktestResult",
    "Candle",
    "CandleSeries",
    "ExitReason",
    "FeeModel",
    "FixedBpsSlippageModel",
    "IntrabarPolicy",
    "LookAheadError",
    "OrderType",
    "PercentageFeeModel",
    "PerformanceMetrics",
    "Position",
    "Side",
    "Signal",
    "SignalAction",
    "SlippageModel",
    "Strategy",
    "StrategyContext",
    "Timeframe",
    "Trade",
    "ZeroFeeModel",
    "ZeroSlippageModel",
    "run_backtest",
]
