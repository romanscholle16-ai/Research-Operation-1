"""Position side and the open-position model.

Leverage is explicitly deferred (Phase 2 brief section 7): quantity is a
plain unit count, `entry_price * quantity` is the full notional, and
there is no margin/leverage multiplier anywhere in the engine. A future
phase that needs leverage should add it as an explicit multiplier on
notional/margin in the portfolio layer, not by changing this model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"

    @property
    def sign(self) -> int:
        return 1 if self is Side.LONG else -1


@dataclass
class Position:
    """A single open position in one symbol. Mutable - owned exclusively
    by `Portfolio`, which is the only thing allowed to change it."""

    symbol: str
    side: Side
    quantity: float
    entry_price: float  # actual (post-slippage) execution price, for reporting
    entry_theoretical_price: float  # pre-slippage price, used for gross P&L
    entry_time: datetime
    stop_loss: float | None = None
    take_profit: float | None = None
    entry_fee: float = 0.0
    entry_slippage_cost: float = 0.0

    def unrealized_pnl(self, mark_price: float) -> float:
        return (mark_price - self.entry_price) * self.quantity * self.side.sign
