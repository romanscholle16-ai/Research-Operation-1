from app.backtesting.engine import BacktestConfig, run_backtest
from app.backtesting.market_data import CandleSeries, Timeframe
from app.backtesting.signals import Signal, SignalAction
from tests.fixtures.mock_strategies import NoOpStrategy, ScriptedStrategy
from tests.fixtures.synthetic_data import build_series


def _config(**overrides) -> BacktestConfig:
    defaults = dict(symbol="TEST/USDT", timeframe=Timeframe.M1, starting_capital=10_000.0)
    defaults.update(overrides)
    return BacktestConfig(**defaults)


def test_no_trade_backtest_is_well_defined() -> None:
    series = build_series([(100, 101, 99, 100, 1000)] * 5)
    result = run_backtest(NoOpStrategy(), series, _config())

    assert result.trades == ()
    assert result.metrics.total_trades == 0
    assert result.equity_curve.ending_equity == 10_000.0
    assert result.equity_curve.max_drawdown == 0.0
    assert result.warnings == ()
    assert result.data_start == series[0].timestamp
    assert result.data_end == series[-1].timestamp


def test_empty_candle_series_backtest_does_not_crash() -> None:
    empty = CandleSeries([], symbol="TEST/USDT", timeframe=Timeframe.M1)
    result = run_backtest(NoOpStrategy(), empty, _config())

    assert result.trades == ()
    assert result.metrics.total_trades == 0
    assert result.data_start is None
    assert result.data_end is None
    assert result.equity_curve.ending_equity == 10_000.0


def test_multiple_trades_sequence() -> None:
    # open/close, open/close, open/close - three round trips back to back.
    rows = [
        (100, 101, 99, 100, 1000),   # 0 signal open #1
        (100, 101, 99, 101, 1000),   # 1 entry fill @100
        (101, 106, 100, 105, 1000),  # 2 signal close #1
        (105, 106, 104, 106, 1000),  # 3 exit fill @105 -> +5
        (106, 107, 105, 106, 1000),  # 4 signal open #2
        (106, 107, 100, 101, 1000),  # 5 entry fill @106
        (101, 102, 95, 96, 1000),    # 6 signal close #2
        (96, 97, 90, 91, 1000),      # 7 exit fill @96 -> -10
        (91, 96, 90, 95, 1000),      # 8 signal open #3
        (95, 100, 94, 99, 1000),     # 9 entry fill @95
        (99, 104, 98, 103, 1000),    # 10 signal close #3
        (103, 108, 102, 107, 1000),  # 11 exit fill @103 -> +8
    ]
    series = build_series(rows)
    script = {
        0: [Signal(SignalAction.OPEN_LONG, timestamp=series[0].timestamp, quantity=1.0)],
        2: [Signal(SignalAction.CLOSE, timestamp=series[2].timestamp)],
        4: [Signal(SignalAction.OPEN_LONG, timestamp=series[4].timestamp, quantity=1.0)],
        6: [Signal(SignalAction.CLOSE, timestamp=series[6].timestamp)],
        8: [Signal(SignalAction.OPEN_LONG, timestamp=series[8].timestamp, quantity=1.0)],
        10: [Signal(SignalAction.CLOSE, timestamp=series[10].timestamp)],
    }
    result = run_backtest(ScriptedStrategy(script), series, _config())

    assert len(result.trades) == 3
    net_pnls = [t.net_pnl for t in result.trades]
    assert net_pnls == [5.0, -10.0, 8.0]
    assert result.metrics.total_trades == 3
    assert result.metrics.winning_trades == 2
    assert result.metrics.losing_trades == 1
    assert result.equity_curve.ending_equity == 10_000.0 + sum(net_pnls)


def test_drawdown_reflects_losing_streak_between_new_equity_highs() -> None:
    rows = [
        (100, 101, 99, 100, 1000),
        (100, 101, 99, 101, 1000),
        (101, 111, 100, 110, 1000),
        (110, 111, 109, 110, 1000),   # exit #1 @110 -> +10 (equity 10010, new peak)
        (110, 111, 109, 110, 1000),
        (110, 111, 100, 101, 1000),
        (101, 102, 90, 95, 1000),
        (95, 96, 89, 90, 1000),       # exit #2 @95 -> -15 (equity 9995, drawdown from peak 10010)
    ]
    series = build_series(rows)
    script = {
        0: [Signal(SignalAction.OPEN_LONG, timestamp=series[0].timestamp, quantity=1.0)],
        2: [Signal(SignalAction.CLOSE, timestamp=series[2].timestamp)],
        4: [Signal(SignalAction.OPEN_LONG, timestamp=series[4].timestamp, quantity=1.0)],
        6: [Signal(SignalAction.CLOSE, timestamp=series[6].timestamp)],
    }
    result = run_backtest(ScriptedStrategy(script), series, _config())

    assert [t.net_pnl for t in result.trades] == [10.0, -15.0]
    assert result.equity_curve.peak_equity == 10_010.0
    assert result.equity_curve.max_drawdown == 15.0
    assert round(result.equity_curve.max_drawdown_pct, 9) == round(15.0 / 10_010.0, 9)
