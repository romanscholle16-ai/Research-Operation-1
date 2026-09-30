"""Equity curve and drawdown, computed strictly from completed trades
(Phase 2 brief section 13) - no intrabar mark-to-market.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.backtesting.trades import Trade


@dataclass(frozen=True)
class EquityPoint:
    timestamp: datetime
    equity: float


@dataclass(frozen=True)
class EquityCurve:
    starting_equity: float
    ending_equity: float
    points: tuple[EquityPoint, ...]
    peak_equity: float
    max_drawdown: float
    max_drawdown_pct: float

    def to_dict(self) -> dict:
        return {
            "starting_equity": self.starting_equity,
            "ending_equity": self.ending_equity,
            "points": [{"timestamp": p.timestamp.isoformat(), "equity": p.equity} for p in self.points],
            "peak_equity": self.peak_equity,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_pct": self.max_drawdown_pct,
        }


def compute_equity_curve(trades: list[Trade], starting_equity: float) -> EquityCurve:
    equity = starting_equity
    peak = starting_equity
    max_dd = 0.0
    max_dd_pct = 0.0
    points: list[EquityPoint] = []

    ordered_trades = sorted(trades, key=lambda t: t.exit_time)
    for trade in ordered_trades:
        equity += trade.net_pnl
        points.append(EquityPoint(timestamp=trade.exit_time, equity=equity))
        peak = max(peak, equity)
        drawdown = peak - equity
        drawdown_pct = (drawdown / peak) if peak > 0 else 0.0
        max_dd = max(max_dd, drawdown)
        max_dd_pct = max(max_dd_pct, drawdown_pct)

    return EquityCurve(
        starting_equity=starting_equity,
        ending_equity=equity,
        points=tuple(points),
        peak_equity=peak,
        max_drawdown=max_dd,
        max_drawdown_pct=max_dd_pct,
    )
