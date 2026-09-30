"""A Fill is what an Order becomes once the execution model resolves it
against a candle: signal -> order -> fill -> position -> trade.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.backtesting.positions import Side


@dataclass(frozen=True)
class Fill:
    order_id: str
    side: Side
    is_buy: bool
    quantity: float
    theoretical_price: float
    price: float  # after slippage
    fee: float
    time: datetime
    reason: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def slippage_cost(self) -> float:
        """Positive number = cost incurred from slippage (price moved
        against the trader), in quote currency for this fill's quantity."""
        direction = 1 if self.is_buy else -1
        return (self.price - self.theoretical_price) * self.quantity * direction
