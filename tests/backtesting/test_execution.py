from app.backtesting.costs import FixedBpsSlippageModel, PercentageFeeModel
from app.backtesting.engine import BacktestConfig, run_backtest
from app.backtesting.market_data import Timeframe
from app.backtesting.positions import Side
from app.backtesting.signals import OrderType, Signal, SignalAction
from app.backtesting.trades import ExitReason
from tests.fixtures.mock_strategies import ScriptedStrategy
from tests.fixtures.synthetic_data import build_series

LONG_ROWS = [
    (100, 101, 99, 100, 1000),   # idx0: signal candle (close=100 -> OPEN_LONG)
    (100, 105, 100, 104, 1000),  # idx1: entry fill candle (open=100)
    (104, 110, 103, 108, 1000),  # idx2: signal candle (close=108 -> CLOSE)
    (108, 109, 107, 108, 1000),  # idx3: exit fill candle (open=108)
]

SHORT_ROWS = [
    (108, 109, 107, 108, 1000),  # idx0: signal candle (close=108 -> OPEN_SHORT)
    (108, 110, 103, 104, 1000),  # idx1: entry fill candle (open=108)
    (104, 105, 99, 100, 1000),   # idx2: signal candle (close=100 -> CLOSE)
    (100, 101, 99, 100, 1000),   # idx3: exit fill candle (open=100)
]


def _config(symbol: str = "TEST/USDT", **overrides) -> BacktestConfig:
    defaults = dict(symbol=symbol, timeframe=Timeframe.M1, starting_capital=10_000.0)
    defaults.update(overrides)
    return BacktestConfig(**defaults)


def test_simple_profitable_long_no_costs() -> None:
    series = build_series(LONG_ROWS)
    script = {
        0: [Signal(SignalAction.OPEN_LONG, timestamp=series[0].timestamp, quantity=1.0)],
        2: [Signal(SignalAction.CLOSE, timestamp=series[2].timestamp)],
    }
    result = run_backtest(ScriptedStrategy(script), series, _config())

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.side is Side.LONG
    assert trade.entry_time == series[1].timestamp  # filled the candle AFTER the signal
    assert trade.entry_price == 100
    assert trade.exit_time == series[3].timestamp
    assert trade.exit_price == 108
    assert trade.quantity == 1
    assert trade.gross_pnl == 8
    assert trade.fees == 0
    assert trade.slippage_cost == 0
    assert trade.net_pnl == 8
    assert trade.exit_reason is ExitReason.SIGNAL
    assert result.equity_curve.ending_equity == 10_008.0


def test_simple_losing_long_no_costs() -> None:
    rows = [
        (100, 101, 99, 100, 1000),
        (100, 101, 95, 96, 1000),   # entry fill at open=100
        (96, 97, 90, 92, 1000),
        (92, 93, 88, 90, 1000),     # exit fill at open=92
    ]
    series = build_series(rows)
    script = {
        0: [Signal(SignalAction.OPEN_LONG, timestamp=series[0].timestamp, quantity=2.0)],
        2: [Signal(SignalAction.CLOSE, timestamp=series[2].timestamp)],
    }
    result = run_backtest(ScriptedStrategy(script), series, _config())

    trade = result.trades[0]
    assert trade.entry_price == 100
    assert trade.exit_price == 92
    assert trade.gross_pnl == (92 - 100) * 2
    assert trade.net_pnl == -16
    assert result.equity_curve.ending_equity == 10_000.0 - 16


def test_short_trade_profitable_no_costs() -> None:
    series = build_series(SHORT_ROWS)
    script = {
        0: [Signal(SignalAction.OPEN_SHORT, timestamp=series[0].timestamp, quantity=1.0)],
        2: [Signal(SignalAction.CLOSE, timestamp=series[2].timestamp)],
    }
    result = run_backtest(ScriptedStrategy(script), series, _config())

    trade = result.trades[0]
    assert trade.side is Side.SHORT
    assert trade.entry_price == 108
    assert trade.exit_price == 100
    assert trade.gross_pnl == 8  # price fell, short profits
    assert trade.net_pnl == 8


def test_fees_are_charged_on_entry_and_exit() -> None:
    series = build_series(LONG_ROWS)
    script = {
        0: [Signal(SignalAction.OPEN_LONG, timestamp=series[0].timestamp, quantity=1.0)],
        2: [Signal(SignalAction.CLOSE, timestamp=series[2].timestamp)],
    }
    result = run_backtest(
        ScriptedStrategy(script), series, _config(fee_model=PercentageFeeModel(rate=0.001))
    )
    trade = result.trades[0]
    assert trade.gross_pnl == 8
    assert round(trade.fees, 6) == round(100 * 1 * 0.001 + 108 * 1 * 0.001, 6)
    assert round(trade.net_pnl, 6) == round(8 - trade.fees, 6)


def test_slippage_moves_fill_price_against_trader() -> None:
    series = build_series(LONG_ROWS)
    script = {
        0: [Signal(SignalAction.OPEN_LONG, timestamp=series[0].timestamp, quantity=1.0)],
        2: [Signal(SignalAction.CLOSE, timestamp=series[2].timestamp)],
    }
    result = run_backtest(
        ScriptedStrategy(script), series, _config(slippage_model=FixedBpsSlippageModel(bps=10))
    )
    trade = result.trades[0]
    assert round(trade.entry_price, 4) == round(100 * 1.001, 4)
    assert round(trade.exit_price, 4) == round(108 * 0.999, 4)
    # gross P&L is computed pre-slippage; slippage is a separate deduction
    assert trade.gross_pnl == 8
    assert round(trade.slippage_cost, 6) == round(0.1 + 0.108, 6)
    assert round(trade.net_pnl, 6) == round(8 - trade.slippage_cost, 6)


def test_fees_and_slippage_combined_do_not_double_count() -> None:
    series = build_series(LONG_ROWS)
    script = {
        0: [Signal(SignalAction.OPEN_LONG, timestamp=series[0].timestamp, quantity=1.0)],
        2: [Signal(SignalAction.CLOSE, timestamp=series[2].timestamp)],
    }
    result = run_backtest(
        ScriptedStrategy(script),
        series,
        _config(fee_model=PercentageFeeModel(rate=0.001), slippage_model=FixedBpsSlippageModel(bps=10)),
    )
    trade = result.trades[0]
    assert trade.gross_pnl == 8
    expected_net = 8 - trade.fees - trade.slippage_cost
    assert round(trade.net_pnl, 9) == round(expected_net, 9)
    # Sanity check against the raw executed-price economics, independently derived:
    raw_price_diff_pnl = (trade.exit_price - trade.entry_price) * trade.quantity
    assert round(trade.net_pnl, 6) == round(raw_price_diff_pnl - trade.fees, 6)


def test_signal_fills_on_next_candle_not_same_candle() -> None:
    series = build_series(LONG_ROWS)
    script = {0: [Signal(SignalAction.OPEN_LONG, timestamp=series[0].timestamp, quantity=1.0)]}
    result = run_backtest(ScriptedStrategy(script), series, _config())
    # Position force-closed at end of data; entry must be candle[1], never candle[0].
    trade = result.trades[0]
    assert trade.entry_time == series[1].timestamp
    assert trade.entry_price == series[1].open


def test_duplicate_open_signal_is_cancelled_with_warning() -> None:
    series = build_series(LONG_ROWS)
    script = {
        0: [Signal(SignalAction.OPEN_LONG, timestamp=series[0].timestamp, quantity=1.0)],
        1: [Signal(SignalAction.OPEN_LONG, timestamp=series[1].timestamp, quantity=1.0)],
    }
    result = run_backtest(ScriptedStrategy(script), series, _config())
    assert any("already has an open position" in w for w in result.warnings)
    assert len(result.trades) == 1  # only the end-of-data forced close


def test_limit_order_fills_when_touched() -> None:
    rows = [
        (100, 101, 99, 100, 1000),
        (99, 100, 95, 98, 1000),  # range [95,100] touches limit=97
    ]
    series = build_series(rows)
    script = {
        0: [
            Signal(
                SignalAction.OPEN_LONG,
                timestamp=series[0].timestamp,
                quantity=1.0,
                order_type=OrderType.LIMIT,
                limit_price=97.0,
            )
        ]
    }
    result = run_backtest(ScriptedStrategy(script), series, _config())
    assert len(result.trades) == 1
    assert result.trades[0].entry_price == 97.0


def test_limit_order_cancelled_when_not_touched() -> None:
    rows = [
        (100, 101, 99, 100, 1000),
        (99, 100, 96, 98, 1000),  # range [96,100] never reaches limit=50
    ]
    series = build_series(rows)
    script = {
        0: [
            Signal(
                SignalAction.OPEN_LONG,
                timestamp=series[0].timestamp,
                quantity=1.0,
                order_type=OrderType.LIMIT,
                limit_price=50.0,
            )
        ]
    }
    result = run_backtest(ScriptedStrategy(script), series, _config())
    assert len(result.trades) == 0
    assert any("not reached" in w for w in result.warnings)


def test_close_signal_with_no_open_position_is_cancelled() -> None:
    series = build_series(LONG_ROWS)
    script = {0: [Signal(SignalAction.CLOSE, timestamp=series[0].timestamp)]}
    result = run_backtest(ScriptedStrategy(script), series, _config())
    assert len(result.trades) == 0
    assert any("no open position" in w for w in result.warnings)
