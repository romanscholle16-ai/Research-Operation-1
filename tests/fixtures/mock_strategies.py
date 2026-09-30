"""Minimal strategies that exist solely to validate the backtesting
engine (Phase 2 brief section 4) - not real trading strategies.
"""

from __future__ import annotations

from app.backtesting.signals import Signal
from app.backtesting.strategy import Strategy, StrategyContext


class ScriptedStrategy(Strategy):
    """Emits exactly the signals it's told to, indexed by candle position
    (0 = the first candle in the series). Lets tests pin down precisely
    which candle a signal originates from without writing indicator
    logic, while still exercising the real engine/execution/accounting
    path end to end.
    """

    def __init__(self, script: dict[int, list[Signal]], *, name: str = "scripted", version: str = "1") -> None:
        self.script = script
        self.name = name
        self.version = version

    def on_bar(self, context: StrategyContext) -> list[Signal]:
        index = len(context.history) - 1
        return self.script.get(index, [])


class NoOpStrategy(Strategy):
    """Never trades. Used for the empty/no-trade backtest case."""

    name = "no_op"
    version = "1"

    def on_bar(self, context: StrategyContext) -> list[Signal]:
        return []


class RecordingStrategy(Strategy):
    """Wraps another strategy and records the `StrategyContext` seen at
    every bar, so tests can assert on exactly what was visible (history
    length, higher-timeframe series contents, current position) at each
    step - used for look-ahead and multi-timeframe synchronization tests.
    """

    name = "recording"
    version = "1"

    def __init__(self, inner: Strategy) -> None:
        self.inner = inner
        self.name = inner.name
        self.version = inner.version
        self.seen_contexts: list[StrategyContext] = []

    def on_bar(self, context: StrategyContext) -> list[Signal]:
        self.seen_contexts.append(context)
        return self.inner.on_bar(context)
