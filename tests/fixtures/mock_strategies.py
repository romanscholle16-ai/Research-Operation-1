"""Minimal strategies that exist solely to validate the backtesting
engine (Phase 2 brief section 4) and the Phase 3 research systems - not
real trading strategies.
"""

from __future__ import annotations

from typing import Any

from app.backtesting.signals import Signal, SignalAction
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


class FixedTradeStrategy(Strategy):
    """Opens on the first candle and closes on the third (index 2), with
    quantity/side/stop/target read from `params`. Generic and
    parameterizable - used as the `strategy_factory` target for Phase 3
    research-system tests (Parameter Explorer, Risk/Execution Optimizer,
    Market-Condition Tester, Adversarial), and as the payload for
    Rule Explorer's variant factories (a variant just wraps this with
    different fixed params, e.g. side="short").

    Requires a series of at least 4 candles (a signal at index 0 fills at
    index 1; a close signal at index 2 fills at index 3) - the same shape
    Phase 2's own tests use.
    """

    def __init__(self, params: dict[str, Any] | None = None, *, name: str = "fixed_trade", version: str = "1") -> None:
        params = params or {}
        self.name = name
        self.version = version
        self.params = params
        self.qty = params.get("qty", 1.0)
        self.side = params.get("side", "long")
        self.stop_loss = params.get("stop_loss")
        self.take_profit = params.get("take_profit")

    def on_bar(self, context: StrategyContext) -> list[Signal]:
        index = len(context.history) - 1
        if index == 0 and context.position is None:
            action = SignalAction.OPEN_LONG if self.side == "long" else SignalAction.OPEN_SHORT
            return [
                Signal(
                    action,
                    timestamp=context.current_candle.timestamp,
                    quantity=self.qty,
                    stop_loss=self.stop_loss,
                    take_profit=self.take_profit,
                )
            ]
        if index == 2 and context.position is not None:
            return [Signal(SignalAction.CLOSE, timestamp=context.current_candle.timestamp)]
        return []


class AlwaysFailsStrategy(Strategy):
    """Raises on the first bar. Used to test deterministic failure
    handling in ExperimentRunner - never a real strategy."""

    name = "always_fails"
    version = "1"

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        pass

    def on_bar(self, context: StrategyContext) -> list[Signal]:
        raise RuntimeError("intentional failure for testing")
