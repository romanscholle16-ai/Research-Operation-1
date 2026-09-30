from datetime import datetime, timedelta, timezone

import pytest

from app.backtesting.market_data import Candle, CandleSeries, Timeframe
from tests.fixtures.synthetic_data import DEFAULT_START, build_series

UTC = timezone.utc


def test_candle_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Candle(timestamp=datetime(2024, 1, 1), open=1, high=2, low=0, close=1, volume=1)


def test_candle_normalizes_non_utc_timezone_to_utc() -> None:
    from datetime import timezone as tz

    offset_tz = tz(timedelta(hours=5))
    local_ts = datetime(2024, 1, 1, 10, 0, tzinfo=offset_tz)
    candle = Candle(timestamp=local_ts, open=1, high=2, low=0, close=1, volume=1)
    assert candle.timestamp.tzinfo == UTC
    assert candle.timestamp == datetime(2024, 1, 1, 5, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"open": 1, "high": 0, "low": 2, "close": 1, "volume": 1},  # high < low
        {"open": 5, "high": 2, "low": 0, "close": 1, "volume": 1},  # open outside range
        {"open": 1, "high": 2, "low": 0, "close": 5, "volume": 1},  # close outside range
        {"open": 1, "high": 2, "low": 0, "close": 1, "volume": -1},  # negative volume
    ],
)
def test_candle_rejects_invalid_ohlcv(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        Candle(timestamp=DEFAULT_START, **kwargs)


def test_candle_series_requires_strictly_increasing_timestamps() -> None:
    c1 = Candle(timestamp=DEFAULT_START, open=1, high=1, low=1, close=1, volume=1)
    c2 = Candle(timestamp=DEFAULT_START, open=1, high=1, low=1, close=1, volume=1)  # duplicate
    with pytest.raises(ValueError, match="strictly increasing"):
        CandleSeries([c1, c2], symbol="X", timeframe=Timeframe.M1)


def test_candle_series_rejects_out_of_order_candles() -> None:
    c1 = Candle(timestamp=DEFAULT_START + timedelta(minutes=2), open=1, high=1, low=1, close=1, volume=1)
    c2 = Candle(timestamp=DEFAULT_START + timedelta(minutes=1), open=1, high=1, low=1, close=1, volume=1)
    with pytest.raises(ValueError, match="strictly increasing"):
        CandleSeries([c1, c2], symbol="X", timeframe=Timeframe.M1)


def test_candle_series_slicing_preserves_symbol_and_timeframe() -> None:
    series = build_series([(1, 1, 1, 1, 1)] * 5, symbol="ETH/USDT", timeframe=Timeframe.M5)
    sliced = series[1:3]
    assert isinstance(sliced, CandleSeries)
    assert sliced.symbol == "ETH/USDT"
    assert sliced.timeframe == Timeframe.M5
    assert len(sliced) == 2


def test_candle_series_start_and_end() -> None:
    series = build_series([(1, 1, 1, 1, 1)] * 3, timeframe=Timeframe.M1)
    assert series.start == series[0].timestamp
    assert series.end == series[-1].timestamp


def test_empty_candle_series_start_end_are_none() -> None:
    series = CandleSeries([], symbol="X", timeframe=Timeframe.M1)
    assert series.start is None
    assert series.end is None
    assert len(series) == 0


def test_index_at_or_before() -> None:
    series = build_series([(1, 1, 1, 1, 1)] * 3, timeframe=Timeframe.M1)  # closes at +1,+2,+3 min
    assert series.index_at_or_before(series[0].timestamp) == 0
    assert series.index_at_or_before(series[1].timestamp) == 1
    assert series.index_at_or_before(series[0].timestamp - timedelta(seconds=1)) is None
    assert series.index_at_or_before(series[-1].timestamp + timedelta(days=1)) == 2


def test_timeframe_minutes_mapping() -> None:
    assert Timeframe.M1.minutes == 1
    assert Timeframe.M5.minutes == 5
    assert Timeframe.M15.minutes == 15
    assert Timeframe.M45.minutes == 45
    assert Timeframe.H1.minutes == 60
    assert Timeframe.H4.minutes == 240
    assert Timeframe.M1 < Timeframe.H4
