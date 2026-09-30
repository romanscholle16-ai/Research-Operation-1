from datetime import datetime, time, timedelta, timezone

import pytest

from app.backtesting.engine import BacktestConfig
from app.backtesting.market_data import Candle, CandleSeries, Timeframe
from app.systems.market_conditions import (
    MarketConditionRequest,
    MarketConditionTester,
    segment_by_chronological_chunks,
    segment_by_day_of_week,
    segment_by_session,
    segment_by_volatility,
)
from app.systems.market_conditions.segmentation import segment_leave_one_out_chronological
from tests.fixtures.mock_strategies import FixedTradeStrategy
from tests.fixtures.synthetic_data import build_series

UTC = timezone.utc


def test_chronological_chunks_cover_every_candle_exactly_once() -> None:
    series = build_series([(1, 1, 1, 1, 1)] * 10)
    chunks = segment_by_chronological_chunks(series, 3)
    assert sum(len(c.candles) for c in chunks) == 10
    assert len(chunks) == 3
    # chunks are contiguous and in order
    reconstructed = [c.timestamp for chunk in chunks for c in chunk.candles]
    assert reconstructed == [c.timestamp for c in series]


def test_chronological_chunks_rejects_invalid_count() -> None:
    series = build_series([(1, 1, 1, 1, 1)] * 5)
    with pytest.raises(ValueError):
        segment_by_chronological_chunks(series, 0)


def test_leave_one_out_excludes_exactly_one_chunk() -> None:
    series = build_series([(1, 1, 1, 1, 1)] * 9)
    segments = segment_leave_one_out_chronological(series, 3)
    assert len(segments) == 3
    for segment in segments:
        assert len(segment.candles) == 6  # 9 - 3


def test_leave_one_out_preserves_timestamp_order() -> None:
    series = build_series([(1, 1, 1, 1, 1)] * 9)
    segments = segment_leave_one_out_chronological(series, 3)
    for segment in segments:
        timestamps = [c.timestamp for c in segment.candles]
        assert timestamps == sorted(timestamps)


def test_volatility_split_is_a_median_split() -> None:
    rows = [
        (100, 101, 99, 100, 1),   # range 2 (low)
        (100, 102, 98, 100, 1),   # range 4 (low, == median)
        (100, 110, 90, 100, 1),   # range 20 (high)
        (100, 120, 80, 100, 1),   # range 40 (high)
    ]
    series = build_series(rows)
    segments = segment_by_volatility(series)
    low = next(s for s in segments if s.label == "low_volatility")
    high = next(s for s in segments if s.label == "high_volatility")
    assert len(low.candles) == 2
    assert len(high.candles) == 2


def test_day_of_week_groups_only_present_weekdays() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)  # a Monday
    candles = [
        Candle(timestamp=start + timedelta(days=0, minutes=1), open=1, high=1, low=1, close=1, volume=1),
        Candle(timestamp=start + timedelta(days=0, minutes=2), open=1, high=1, low=1, close=1, volume=1),
        Candle(timestamp=start + timedelta(days=2, minutes=1), open=1, high=1, low=1, close=1, volume=1),
    ]
    series = CandleSeries(candles, symbol="X", timeframe=Timeframe.M1)
    segments = segment_by_day_of_week(series)
    labels = {s.label: len(s.candles) for s in segments}
    assert labels == {"monday": 2, "wednesday": 1}


def test_session_filters_by_time_of_day() -> None:
    day = datetime(2024, 1, 1, tzinfo=UTC)
    candles = [
        Candle(timestamp=day.replace(hour=9), open=1, high=1, low=1, close=1, volume=1),   # inside london
        Candle(timestamp=day.replace(hour=20), open=1, high=1, low=1, close=1, volume=1),  # outside
    ]
    series = CandleSeries(candles, symbol="X", timeframe=Timeframe.M1)
    segments = segment_by_session(series, {"london": (time(8, 0), time(16, 30))})
    assert len(segments) == 1
    assert len(segments[0].candles) == 1
    assert segments[0].candles[0].timestamp.hour == 9


def test_session_rejects_wrapping_window() -> None:
    series = build_series([(1, 1, 1, 1, 1)] * 3)
    with pytest.raises(ValueError):
        segment_by_session(series, {"bad": (time(22, 0), time(2, 0))})


ROWS = [
    (100, 101, 99, 100, 1000),
    (100, 105, 100, 104, 1000),
    (104, 110, 103, 108, 1000),
    (108, 109, 107, 108, 1000),
]


def test_tester_generates_one_experiment_per_segment() -> None:
    series = build_series(ROWS)
    segments = segment_by_chronological_chunks(series, 2)
    request = MarketConditionRequest(
        strategy_name="fixed_trade",
        strategy_version="1",
        strategy_factory=lambda p: FixedTradeStrategy(p),
        candles=series,
        execution_config=BacktestConfig(symbol="TEST/USDT", timeframe=Timeframe.M1, starting_capital=10_000.0),
        segments=tuple(segments),
    )
    experiments = MarketConditionTester().generate_experiments(request)
    assert len(experiments) == 2
    assert experiments[0].candles is segments[0].candles
    assert experiments[0].rule_configuration["segment_label"] == segments[0].label
    assert experiments[0].rule_configuration["segmentation_method"] == "chronological_chunks"


def test_tester_requires_at_least_one_segment() -> None:
    with pytest.raises(ValueError):
        MarketConditionRequest(
            strategy_name="fixed_trade",
            strategy_version="1",
            strategy_factory=lambda p: FixedTradeStrategy(p),
            candles=build_series(ROWS),
            execution_config=BacktestConfig(symbol="TEST/USDT", timeframe=Timeframe.M1, starting_capital=10_000.0),
            segments=(),
        )
