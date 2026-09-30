"""A completed trade: the record produced when a position fully closes.
Designed to map directly onto the `trades` table (app/database/schema.py,
migration 2) without loss - every field here has a matching column.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from app.backtesting.positions import Side


class ExitReason(str, Enum):
    SIGNAL = "signal"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    END_OF_DATA = "end_of_data"


@dataclass(frozen=True)
class Trade:
    strategy_name: str
    symbol: str
    side: Side
    entry_time: datetime
    entry_price: float
    exit_time: datetime
    exit_price: float
    quantity: float
    gross_pnl: float
    fees: float
    slippage_cost: float
    exit_reason: ExitReason
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.fees - self.slippage_cost

    @property
    def return_pct(self) -> float:
        notional = abs(self.entry_price * self.quantity)
        if notional == 0:
            return 0.0
        return self.net_pnl / notional

    @property
    def is_win(self) -> bool:
        return self.net_pnl > 0
