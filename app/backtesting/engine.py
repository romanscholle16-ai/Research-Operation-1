"""Backtest orchestration - the single place that ties market data,
strategy, execution, and result-building together.

## Look-ahead protection (Phase 2 brief section 9)

For candle index `i`:

1. Orders queued from candle `i-1`'s close are executed against candle
   `i` (entries fill at `i.open`; LIMIT orders fill only if `i`'s range
   touches the limit price). Existing positions' stop-loss/take-profit
   are also checked against candle `i`'s range here, BEFORE any new
   entry from this step is applied - a position cannot be stopped out on
   the same candle it was opened (see execution.py).
2. `strategy.on_bar()` is called with a `StrategyContext` whose `history`
   is `candles[0 : i+1]` - never candle `i+1` or later.
3. Any `Signal`s returned become `Order`s queued for step 1 of candle
   `i+1` - never candle `i`. This one-candle delay between decision and
   execution is what prevents a signal from being filled using
   information (that candle's own future high/low/close) that wasn't
   available at the moment the signal was generated.

`Signal.timestamp` is asserted to equal candle `i`'s timestamp; a
strategy that fabricates a different timestamp raises `LookAheadError`
rather than silently being trusted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.backtesting.costs import FeeModel, SlippageModel, ZeroFeeModel, ZeroSlippageModel
from app.backtesting.equity import compute_equity_curve
from app.backtesting.execution import is_buy_for_close, make_fill, process_candle
from app.backtesting.intrabar import IntrabarPolicy
from app.backtesting.market_data import CandleSeries, Timeframe
from app.backtesting.metrics import compute_metrics
from app.backtesting.multi_timeframe import MultiTimeframeView
from app.backtesting.orders import Order
from app.backtesting.portfolio import Portfolio
from app.backtesting.result import (
    ExecutionAssumptions,
    BacktestResult,
    compute_data_identity,
    compute_fingerprint,
    new_run_id,
)
from app.backtesting.signals import Signal, SignalAction
from app.backtesting.strategy import Strategy, StrategyContext
from app.backtesting.trades import ExitReason


class LookAheadError(Exception):
    """Raised when a signal's timestamp doesn't match the candle that
    produced it - a strategy trying to (accidentally or otherwise) claim
    a different point in time than the one it was actually given."""


@dataclass(frozen=True)
class BacktestConfig:
    symbol: str
    timeframe: Timeframe
    starting_capital: float
    fee_model: FeeModel = field(default_factory=ZeroFeeModel)
    slippage_model: SlippageModel = field(default_factory=ZeroSlippageModel)
    intrabar_policy: IntrabarPolicy = IntrabarPolicy.STOP_FIRST
    strategy_params: dict[str, Any] = field(default_factory=dict)
    higher_timeframes: dict[Timeframe, CandleSeries] = field(default_factory=dict)


def _signal_to_order(signal: Signal) -> Order:
    if signal.action is SignalAction.CLOSE:
        return Order(
            action="close",
            created_at=signal.timestamp,
            order_type=signal.order_type,
            limit_price=signal.limit_price,
            reason=signal.reason,
        )
    assert signal.side is not None and signal.quantity is not None
    return Order(
        action="open",
        created_at=signal.timestamp,
        side=signal.side,
        order_type=signal.order_type,
        quantity=signal.quantity,
        limit_price=signal.limit_price,
        stop_loss=signal.stop_loss,
        take_profit=signal.take_profit,
        reason=signal.reason,
    )


def run_backtest(strategy: Strategy, candles: CandleSeries, config: BacktestConfig) -> BacktestResult:
    portfolio = Portfolio(config.starting_capital)
    mtf_view = MultiTimeframeView(config.higher_timeframes)

    pending_orders: list[Order] = []
    all_trades = []
    all_warnings: list[str] = []

    for i in range(len(candles)):
        candle = candles[i]

        exec_result = process_candle(
            candle=candle,
            pending_orders=pending_orders,
            portfolio=portfolio,
            fee_model=config.fee_model,
            slippage_model=config.slippage_model,
            intrabar_policy=config.intrabar_policy,
            strategy_name=strategy.name,
            symbol=config.symbol,
        )
        all_trades.extend(exec_result.trades)
        all_warnings.extend(exec_result.warnings)

        history = candles[: i + 1]
        context = StrategyContext(
            symbol=config.symbol,
            timeframe=config.timeframe,
            history=history,
            higher_timeframes=mtf_view,
            position=portfolio.open_positions.get(config.symbol),
            params=config.strategy_params,
        )
        signals = strategy.on_bar(context)

        pending_orders = []
        for signal in signals:
            if signal.timestamp != candle.timestamp:
                raise LookAheadError(
                    f"Signal timestamp {signal.timestamp.isoformat()} does not match "
                    f"the candle that produced it ({candle.timestamp.isoformat()})"
                )
            pending_orders.append(_signal_to_order(signal))

    if portfolio.has_open_position(config.symbol) and len(candles) > 0:
        last_candle = candles[-1]
        position = portfolio.open_positions[config.symbol]
        fill = make_fill(
            order_id="end-of-data-close",
            side=position.side,
            is_buy=is_buy_for_close(position.side),
            quantity=position.quantity,
            theoretical_price=last_candle.close,
            candle=last_candle,
            fee_model=config.fee_model,
            slippage_model=config.slippage_model,
            reason="end_of_data",
        )
        all_trades.append(
            portfolio.close_position(
                config.symbol, fill, strategy_name=strategy.name, exit_reason=ExitReason.END_OF_DATA
            )
        )
        all_warnings.append(
            f"Open position in {config.symbol} force-closed at end of data ({last_candle.timestamp.isoformat()})"
        )

    equity_curve = compute_equity_curve(all_trades, config.starting_capital)
    metrics = compute_metrics(
        all_trades, max_drawdown=equity_curve.max_drawdown, max_drawdown_pct=equity_curve.max_drawdown_pct
    )

    execution_assumptions = ExecutionAssumptions(
        starting_capital=config.starting_capital,
        fee_model=config.fee_model,
        slippage_model=config.slippage_model,
        intrabar_policy=config.intrabar_policy,
    )
    data_identity = compute_data_identity(candles)
    fingerprint = compute_fingerprint(
        strategy_name=strategy.name,
        strategy_version=strategy.version,
        parameters=config.strategy_params,
        data_identity=data_identity,
        execution_assumptions=execution_assumptions,
    )

    return BacktestResult(
        run_id=new_run_id(),
        fingerprint=fingerprint,
        strategy_name=strategy.name,
        strategy_version=strategy.version,
        symbol=config.symbol,
        timeframe=config.timeframe,
        parameters=config.strategy_params,
        execution_assumptions=execution_assumptions,
        data_start=candles.start,
        data_end=candles.end,
        trades=tuple(all_trades),
        equity_curve=equity_curve,
        metrics=metrics,
        warnings=tuple(all_warnings),
    )
