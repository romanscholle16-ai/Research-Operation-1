"""Strategy output: signals. Kept deliberately separate from orders
(app/backtesting/orders.py) - a signal expresses trading *intent*, an
order is the engine's execution-ready representation of it. See
app/backtesting/engine.py for how a signal generated at candle N's close
becomes an order filled on candle N+1, which is the mechanism that
prevents look-ahead bias.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.backtesting.positions import Side


class SignalAction(str, Enum):
    OPEN_LONG = "open_long"
    OPEN_SHORT = "open_short"
    CLOSE = "close"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


@dataclass(frozen=True)
class Signal:
    """One trading decision emitted by a `Strategy.on_bar()` call.

    `timestamp` must be the timestamp of the candle whose close produced
    this signal - the engine uses it to assert the signal cannot be
    filled before that time.
    """

    action: SignalAction
    timestamp: datetime
    order_type: OrderType = OrderType.MARKET
    quantity: float | None = None
    limit_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.action in (SignalAction.OPEN_LONG, SignalAction.OPEN_SHORT):
            if self.quantity is None or self.quantity <= 0:
                raise ValueError(f"{self.action.value} signal requires a positive quantity")
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("LIMIT order_type requires limit_price")

    @property
    def side(self) -> Side | None:
        if self.action is SignalAction.OPEN_LONG:
            return Side.LONG
        if self.action is SignalAction.OPEN_SHORT:
            return Side.SHORT
        return None
