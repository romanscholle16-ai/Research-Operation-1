"""Intrabar stop/take-profit ambiguity policy (Phase 2 brief section 8).

OHLC candles do not record the order in which price levels were touched
within the bar. If both the stop-loss and take-profit fall inside one
candle's [low, high] range, the engine cannot know from the data alone
which was hit first. This module makes that assumption explicit and
configurable rather than silently picking one.
"""

from __future__ import annotations

from enum import Enum

from app.backtesting.market_data import Candle
from app.backtesting.positions import Side
from app.backtesting.trades import ExitReason


class IntrabarPolicy(str, Enum):
    """How to resolve a candle whose range touches both the stop-loss and
    take-profit of an open position.

    STOP_FIRST: assume the stop was hit first (conservative - never
    overstates a win). This is the engine default.
    TARGET_FIRST: assume the take-profit was hit first (optimistic).
    """

    STOP_FIRST = "stop_first"
    TARGET_FIRST = "target_first"


def resolve_exit(
    candle: Candle,
    side: Side,
    stop_loss: float | None,
    take_profit: float | None,
    policy: IntrabarPolicy,
) -> tuple[float, ExitReason] | None:
    """Return (exit_price, exit_reason) if this candle's range triggers the
    stop-loss and/or take-profit for a position of the given side, else
    None. Only STOP_LOSS/TAKE_PROFIT are considered here - signal-driven
    closes are handled separately by the engine.
    """
    stop_hit = stop_loss is not None and _crosses(candle, side, stop_loss, is_stop=True)
    target_hit = take_profit is not None and _crosses(candle, side, take_profit, is_stop=False)

    if stop_hit and target_hit:
        if policy is IntrabarPolicy.STOP_FIRST:
            return stop_loss, ExitReason.STOP_LOSS  # type: ignore[return-value]
        return take_profit, ExitReason.TAKE_PROFIT  # type: ignore[return-value]
    if stop_hit:
        return stop_loss, ExitReason.STOP_LOSS  # type: ignore[return-value]
    if target_hit:
        return take_profit, ExitReason.TAKE_PROFIT  # type: ignore[return-value]
    return None


def _crosses(candle: Candle, side: Side, level: float, *, is_stop: bool) -> bool:
    """Whether the candle's [low, high] range reaches `level` in the
    direction that would trigger it, for a position of the given side."""
    # For a LONG: stop is below entry (triggers if low <= stop),
    #             target is above entry (triggers if high >= target).
    # For a SHORT: stop is above entry (triggers if high >= stop),
    #              target is below entry (triggers if low <= target).
    stop_direction_is_down = side is Side.LONG
    triggers_on_down_move = is_stop == stop_direction_is_down
    if triggers_on_down_move:
        return candle.low <= level
    return candle.high >= level
