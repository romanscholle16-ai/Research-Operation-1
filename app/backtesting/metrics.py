"""Deterministic performance-metric calculation (Phase 2 brief section 12).

Every metric that can be undefined for a degenerate input (no trades, no
losing trades, ...) returns `None` rather than raising or returning a
sentinel like `inf`/`nan` that would break JSON serialization and equality
checks. `total_trades == 0` is the only input this module treats as fully
degenerate; see each field's comment for its specific undefined case.

`expectancy` is defined here as mean net P&L per trade (equivalent to
`average_trade`) - there is no R-multiple/risk-normalized data available
at this layer of the engine, so a risk-adjusted expectancy is not
computable yet. A future phase with an explicit "risk per trade" concept
can add a separate `expectancy_r` metric without changing this one.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.backtesting.trades import Trade


@dataclass(frozen=True)
class PerformanceMetrics:
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    gross_profit: float
    gross_loss: float
    net_profit: float
    average_trade: float
    expectancy: float
    profit_factor: float | None  # None: no losing trades to divide by
    max_drawdown: float
    max_drawdown_pct: float
    total_fees: float
    total_slippage: float
    average_win: float | None  # None: no winning trades
    average_loss: float | None  # None: no losing trades
    largest_win: float | None  # None: no winning trades
    largest_loss: float | None  # None: no losing trades

    def to_dict(self) -> dict:
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "gross_profit": self.gross_profit,
            "gross_loss": self.gross_loss,
            "net_profit": self.net_profit,
            "average_trade": self.average_trade,
            "expectancy": self.expectancy,
            "profit_factor": self.profit_factor,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_pct": self.max_drawdown_pct,
            "total_fees": self.total_fees,
            "total_slippage": self.total_slippage,
            "average_win": self.average_win,
            "average_loss": self.average_loss,
            "largest_win": self.largest_win,
            "largest_loss": self.largest_loss,
        }


def compute_metrics(
    trades: list[Trade],
    *,
    max_drawdown: float,
    max_drawdown_pct: float,
) -> PerformanceMetrics:
    total_trades = len(trades)
    total_fees = sum(t.fees for t in trades)
    total_slippage = sum(t.slippage_cost for t in trades)

    if total_trades == 0:
        return PerformanceMetrics(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            gross_profit=0.0,
            gross_loss=0.0,
            net_profit=0.0,
            average_trade=0.0,
            expectancy=0.0,
            profit_factor=None,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            total_fees=total_fees,
            total_slippage=total_slippage,
            average_win=None,
            average_loss=None,
            largest_win=None,
            largest_loss=None,
        )

    wins = [t.net_pnl for t in trades if t.net_pnl > 0]
    losses = [t.net_pnl for t in trades if t.net_pnl < 0]  # negative values

    winning_trades = len(wins)
    losing_trades = len(losses)
    gross_profit = sum(wins)
    gross_loss = sum(losses)  # <= 0
    net_profit = gross_profit + gross_loss
    average_trade = net_profit / total_trades

    return PerformanceMetrics(
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        win_rate=winning_trades / total_trades,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_profit=net_profit,
        average_trade=average_trade,
        expectancy=average_trade,
        profit_factor=(gross_profit / abs(gross_loss)) if gross_loss < 0 else None,
        max_drawdown=max_drawdown,
        max_drawdown_pct=max_drawdown_pct,
        total_fees=total_fees,
        total_slippage=total_slippage,
        average_win=(gross_profit / winning_trades) if winning_trades > 0 else None,
        average_loss=(gross_loss / losing_trades) if losing_trades > 0 else None,
        largest_win=max(wins) if wins else None,
        largest_loss=min(losses) if losses else None,
    )
