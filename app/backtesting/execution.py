"""Turns pending orders and open-position stop/target levels into fills
against one candle, and applies those fills to the portfolio.

Execution order within one candle (see engine.py for the surrounding
loop): stop-loss/take-profit checks for *already-open* positions run
first, using this candle's [low, high] - a position cannot be stopped out
on the very candle it was opened, since that check runs before this
candle's entry orders are applied. This sidesteps same-bar entry/exit
ambiguity entirely rather than guessing at intrabar sequencing for it;
see ARCHITECTURE.md "Intrabar execution assumptions".

Market orders fill at this candle's `open` - the next bar after the
signal's originating candle closed (see engine.py). LIMIT orders fill at
their limit price only if this candle's range touches it; otherwise they
are cancelled (not carried forward) - see orders.py's docstring.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.backtesting.costs import FeeModel, SlippageModel
from app.backtesting.fills import Fill
from app.backtesting.intrabar import IntrabarPolicy, resolve_exit
from app.backtesting.market_data import Candle
from app.backtesting.orders import Order, OrderStatus
from app.backtesting.portfolio import Portfolio
from app.backtesting.positions import Side
from app.backtesting.signals import OrderType
from app.backtesting.trades import ExitReason, Trade


@dataclass
class ExecutionResult:
    fills: list[Fill]
    trades: list[Trade]
    warnings: list[str]


def is_buy_for_open(side: Side) -> bool:
    return side is Side.LONG


def is_buy_for_close(position_side: Side) -> bool:
    return position_side is Side.SHORT


def make_fill(
    *,
    order_id: str,
    side: Side,
    is_buy: bool,
    quantity: float,
    theoretical_price: float,
    candle: Candle,
    fee_model: FeeModel,
    slippage_model: SlippageModel,
    reason: str,
) -> Fill:
    fill_price = slippage_model.apply(theoretical_price, is_buy=is_buy, quantity=quantity)
    fee = fee_model.calculate_fee(fill_price, quantity)
    return Fill(
        order_id=order_id,
        side=side,
        is_buy=is_buy,
        quantity=quantity,
        theoretical_price=theoretical_price,
        price=fill_price,
        fee=fee,
        time=candle.timestamp,
        reason=reason,
    )


def process_candle(
    *,
    candle: Candle,
    pending_orders: list[Order],
    portfolio: Portfolio,
    fee_model: FeeModel,
    slippage_model: SlippageModel,
    intrabar_policy: IntrabarPolicy,
    strategy_name: str,
    symbol: str,
) -> ExecutionResult:
    fills: list[Fill] = []
    trades: list[Trade] = []
    warnings: list[str] = []

    # 1. Stop-loss / take-profit checks for a position already open BEFORE
    #    this candle (see module docstring for why entries are applied after).
    if portfolio.has_open_position(symbol):
        position = portfolio.open_positions[symbol]
        triggered = resolve_exit(candle, position.side, position.stop_loss, position.take_profit, intrabar_policy)
        if triggered is not None:
            exit_price, exit_reason = triggered
            is_buy = is_buy_for_close(position.side)
            fill = make_fill(
                order_id=f"auto-exit-{symbol}",
                side=position.side,
                is_buy=is_buy,
                quantity=position.quantity,
                theoretical_price=exit_price,
                candle=candle,
                fee_model=fee_model,
                slippage_model=slippage_model,
                reason=exit_reason.value,
            )
            fills.append(fill)
            trades.append(
                portfolio.close_position(symbol, fill, strategy_name=strategy_name, exit_reason=exit_reason)
            )

    # 2. Pending orders queued from the previous candle's close.
    for order in pending_orders:
        if order.action == "open":
            if portfolio.has_open_position(symbol):
                order.status = OrderStatus.CANCELLED
                warnings.append(
                    f"Order {order.id} at {candle.timestamp.isoformat()} cancelled: "
                    f"{symbol} already has an open position"
                )
                continue

            fill_price = _resolve_entry_price(order, candle)
            if fill_price is None:
                order.status = OrderStatus.CANCELLED
                warnings.append(
                    f"LIMIT order {order.id} at {candle.timestamp.isoformat()} cancelled: "
                    f"limit price {order.limit_price} not reached"
                )
                continue

            is_buy = is_buy_for_open(order.side)
            fill = make_fill(
                order_id=order.id,
                side=order.side,
                is_buy=is_buy,
                quantity=order.quantity,
                theoretical_price=fill_price,
                candle=candle,
                fee_model=fee_model,
                slippage_model=slippage_model,
                reason=order.reason,
            )
            fills.append(fill)
            order.status = OrderStatus.FILLED
            portfolio.open_position(symbol, fill, stop_loss=order.stop_loss, take_profit=order.take_profit)

        elif order.action == "close":
            if not portfolio.has_open_position(symbol):
                order.status = OrderStatus.CANCELLED
                warnings.append(
                    f"Close order {order.id} at {candle.timestamp.isoformat()} cancelled: "
                    f"no open position in {symbol}"
                )
                continue

            position = portfolio.open_positions[symbol]
            fill_price = _resolve_entry_price(order, candle)  # same LIMIT/MARKET resolution logic
            if fill_price is None:
                order.status = OrderStatus.CANCELLED
                warnings.append(
                    f"LIMIT close order {order.id} at {candle.timestamp.isoformat()} cancelled: "
                    f"limit price {order.limit_price} not reached"
                )
                continue

            is_buy = is_buy_for_close(position.side)
            fill = make_fill(
                order_id=order.id,
                side=position.side,
                is_buy=is_buy,
                quantity=position.quantity,
                theoretical_price=fill_price,
                candle=candle,
                fee_model=fee_model,
                slippage_model=slippage_model,
                reason=order.reason,
            )
            fills.append(fill)
            order.status = OrderStatus.FILLED
            trades.append(
                portfolio.close_position(
                    symbol, fill, strategy_name=strategy_name, exit_reason=ExitReason.SIGNAL
                )
            )

    return ExecutionResult(fills=fills, trades=trades, warnings=warnings)


def _resolve_entry_price(order: Order, candle: Candle) -> float | None:
    if order.order_type is OrderType.MARKET:
        return candle.open
    # LIMIT: fill exactly at the limit price if this candle's range touches it.
    assert order.limit_price is not None
    if candle.low <= order.limit_price <= candle.high:
        return order.limit_price
    return None
