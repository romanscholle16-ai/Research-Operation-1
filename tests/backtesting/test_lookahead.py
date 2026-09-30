from datetime import timedelta

import pytest

from app.backtesting.engine import BacktestConfig, LookAheadError, run_backtest
from app.backtesting.market_data import Candle, CandleSeries, Timeframe
from app.backtesting.multi_timeframe import MultiTimeframeView
from app.backtesting.signals import Signal, SignalAction
from tests.fixtures.mock_strategies import NoOpStrategy, RecordingStrategy, ScriptedStrategy
from tests.fixtures.synthetic_data import DEFAULT_START, build_series


def _config() -> BacktestConfig:
    return BacktestConfig(symbol="TEST/USDT", timeframe=Timeframe.M1, starting_capital=10_000.0)


def test_signal_with_wrong_timestamp_raises_lookahead_error() -> None:
    series = build_series([(1, 1, 1, 1, 1)] * 3, timeframe=Timeframe.M1)
    # Signal claims candle[1]'s timestamp while being produced at candle[0].
    script = {0: [Signal(SignalAction.OPEN_LONG, timestamp=series[1].timestamp, quantity=1.0)]}
    with pytest.raises(LookAheadError):
        run_backtest(ScriptedStrategy(script), series, _config())


def test_strategy_never_sees_more_history_than_the_current_candle() -> None:
    series = build_series([(1, 1, 1, 1, 1)] * 6, timeframe=Timeframe.M1)
    recorder = RecordingStrategy(NoOpStrategy())
    run_backtest(recorder, series, _config())

    assert len(recorder.seen_contexts) == len(series)
    for i, context in enumerate(recorder.seen_contexts):
        assert len(context.history) == i + 1
        assert context.history[-1].timestamp == series[i].timestamp
        # Nothing after the current candle is visible.
        assert context.current_candle.timestamp == series[i].timestamp


def test_multi_timeframe_view_excludes_still_forming_higher_tf_candle() -> None:
    m5_candles = [
        Candle(timestamp=DEFAULT_START + timedelta(minutes=5), open=1, high=1, low=1, close=1, volume=1),
        Candle(timestamp=DEFAULT_START + timedelta(minutes=10), open=1, high=1, low=1, close=1, volume=1),
    ]
    m5_series = CandleSeries(m5_candles, symbol="TEST/USDT", timeframe=Timeframe.M5)
    view = MultiTimeframeView({Timeframe.M5: m5_series})

    # At minute 4, the M5 candle closing at minute 5 has not closed yet.
    visible_at_4 = view.as_of(Timeframe.M5, DEFAULT_START + timedelta(minutes=4))
    assert len(visible_at_4) == 0

    # At minute 5 exactly, that candle has just closed and becomes visible.
    visible_at_5 = view.as_of(Timeframe.M5, DEFAULT_START + timedelta(minutes=5))
    assert len(visible_at_5) == 1
    assert visible_at_5[0].timestamp == m5_candles[0].timestamp

    # At minute 9, the second M5 candle (closes at 10) is still not visible.
    visible_at_9 = view.as_of(Timeframe.M5, DEFAULT_START + timedelta(minutes=9))
    assert len(visible_at_9) == 1

    # At minute 10, both are visible.
    visible_at_10 = view.as_of(Timeframe.M5, DEFAULT_START + timedelta(minutes=10))
    assert len(visible_at_10) == 2


def test_engine_wires_higher_timeframes_into_strategy_context_look_ahead_safely() -> None:
    primary = build_series([(1, 1, 1, 1, 1)] * 10, timeframe=Timeframe.M1)  # closes at +1..+10 min
    m5_candles = [
        Candle(timestamp=DEFAULT_START + timedelta(minutes=5), open=1, high=1, low=1, close=1, volume=1),
        Candle(timestamp=DEFAULT_START + timedelta(minutes=10), open=1, high=1, low=1, close=1, volume=1),
    ]
    m5_series = CandleSeries(m5_candles, symbol="TEST/USDT", timeframe=Timeframe.M5)

    recorder = RecordingStrategy(NoOpStrategy())
    config = BacktestConfig(
        symbol="TEST/USDT",
        timeframe=Timeframe.M1,
        starting_capital=10_000.0,
        higher_timeframes={Timeframe.M5: m5_series},
    )
    run_backtest(recorder, primary, config)

    # Primary candle at minute 4 must not see the M5 candle that closes at minute 5.
    context_at_minute_4 = recorder.seen_contexts[3]
    assert len(context_at_minute_4.higher_timeframes.as_of(Timeframe.M5, context_at_minute_4.current_candle.timestamp)) == 0

    # Primary candle at minute 5 must see exactly that one M5 candle.
    context_at_minute_5 = recorder.seen_contexts[4]
    visible = context_at_minute_5.higher_timeframes.as_of(Timeframe.M5, context_at_minute_5.current_candle.timestamp)
    assert len(visible) == 1
