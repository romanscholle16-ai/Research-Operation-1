"""Generic strategy interface.

A `Strategy` is a pure function of the data it's given: `on_bar()` must
not reach outside `StrategyContext` for market data (no closing over a
full dataset, no querying "future" candles) - `StrategyContext` is
specifically shaped so that everything reachable from it is already
look-ahead safe. Strategy logic stays separate from execution logic: a
`Strategy` only ever returns `Signal`s: it never sees fills, fees, or
slippage.

No real trading strategy is implemented here - see
tests/fixtures/mock_strategies.py for the minimal strategies used to
validate the engine itself.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.backtesting.market_data import CandleSeries, Timeframe
from app.backtesting.multi_timeframe import MultiTimeframeView
from app.backtesting.positions import Position
from app.backtesting.signals import Signal


@dataclass(frozen=True)
class StrategyContext:
    """Everything a strategy may look at when deciding what to do at the
    close of `history[-1]` (the current candle). `history` never includes
    any candle after the current one."""

    symbol: str
    timeframe: Timeframe
    history: CandleSeries
    higher_timeframes: MultiTimeframeView
    position: Position | None
    params: dict[str, Any]

    @property
    def current_candle(self):
        return self.history[-1]


class Strategy(ABC):
    """Subclass and implement `on_bar`. One instance is reused for an
    entire backtest run, so any internal state (e.g. indicator buffers)
    must itself only ever be derived from `StrategyContext.history`."""

    name: str = "unnamed_strategy"
    version: str = "0"

    @abstractmethod
    def on_bar(self, context: StrategyContext) -> list[Signal]:
        """Return zero or more signals in response to the candle that just closed."""
        raise NotImplementedError
