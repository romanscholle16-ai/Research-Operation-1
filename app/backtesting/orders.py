"""Orders: the engine-internal, execution-ready representation of a
signal. See app/backtesting/signals.py for the strategy-facing intent
type and app/backtesting/fills.py for what an order becomes once filled.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from app.backtesting.positions import Side
from app.backtesting.signals import OrderType


class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"


@dataclass
class Order:
    """An entry or close order queued for execution on the *next* candle
    after the one whose close produced it (see engine.py). A LIMIT order
    that isn't touched by the very next candle's range is cancelled
    rather than left resting indefinitely - see ARCHITECTURE.md
    "Order model simplifications" for why.

    For a "close" order, `side` and `quantity` are unused (the execution
    engine reads them from the actual open `Position` instead, since that
    is the only source of truth for what is being closed) and left None.
    """

    action: str  # "open" | "close" - kept as str to avoid importing SignalAction here
    created_at: datetime
    side: Side | None = None
    order_type: OrderType = OrderType.MARKET
    quantity: float | None = None
    limit_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    reason: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: OrderStatus = OrderStatus.PENDING
