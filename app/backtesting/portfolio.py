"""Account state: cash/equity plus at most one open position per symbol.

Equity changes only at trade close (Phase 2 brief section 13: the equity
curve is built "from completed executions/trades"), not mark-to-market
intrabar. Leverage/margin is not modeled - `quantity * price` is treated
as the full notional with no multiplier; see positions.py's module
docstring for why this is deferred rather than half-built.
"""

from __future__ import annotations

from app.backtesting.fills import Fill
from app.backtesting.positions import Position
from app.backtesting.trades import ExitReason, Trade


class Portfolio:
    def __init__(self, starting_capital: float) -> None:
        self.starting_capital = starting_capital
        self.equity = starting_capital
        self.open_positions: dict[str, Position] = {}

    def has_open_position(self, symbol: str) -> bool:
        return symbol in self.open_positions

    def open_position(
        self,
        symbol: str,
        fill: Fill,
        *,
        stop_loss: float | None,
        take_profit: float | None,
    ) -> Position:
        if symbol in self.open_positions:
            raise ValueError(f"Cannot open {symbol}: a position is already open")
        position = Position(
            symbol=symbol,
            side=fill.side,
            quantity=fill.quantity,
            entry_price=fill.price,
            entry_theoretical_price=fill.theoretical_price,
            entry_time=fill.time,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_fee=fill.fee,
            entry_slippage_cost=fill.slippage_cost,
        )
        self.open_positions[symbol] = position
        return position

    def close_position(
        self,
        symbol: str,
        fill: Fill,
        *,
        strategy_name: str,
        exit_reason: ExitReason,
    ) -> Trade:
        position = self.open_positions.pop(symbol)
        # gross P&L is computed from THEORETICAL (pre-slippage) prices, so
        # fees and slippage_cost can both be subtracted from it below
        # without double-counting slippage's effect on the actual fill
        # prices - see ARCHITECTURE.md "Gross vs net P&L".
        gross_pnl = (
            (fill.theoretical_price - position.entry_theoretical_price) * position.quantity * position.side.sign
        )
        trade = Trade(
            strategy_name=strategy_name,
            symbol=symbol,
            side=position.side,
            entry_time=position.entry_time,
            entry_price=position.entry_price,
            exit_time=fill.time,
            exit_price=fill.price,
            quantity=position.quantity,
            gross_pnl=gross_pnl,
            fees=position.entry_fee + fill.fee,
            slippage_cost=position.entry_slippage_cost + fill.slippage_cost,
            exit_reason=exit_reason,
        )
        self.equity += trade.net_pnl
        return trade
