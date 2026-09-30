"""Deterministic synthetic OHLCV data for backtesting-engine tests.
Never downloads or reads real market data (Phase 2 brief section 17).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.backtesting.market_data import Candle, CandleSeries, Timeframe

UTC = timezone.utc
DEFAULT_START = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)


def build_series(
    rows: list[tuple[float, float, float, float, float]],
    *,
    symbol: str = "TEST/USDT",
    timeframe: Timeframe = Timeframe.M1,
    start: datetime = DEFAULT_START,
) -> CandleSeries:
    """Build a CandleSeries from (open, high, low, close, volume) rows.

    Row `i`'s timestamp is `start + (i+1) * timeframe` - i.e. each row's
    own CLOSE time, consistent with `Candle.timestamp`'s documented
    convention (see app/backtesting/market_data.py).
    """
    step = timedelta(minutes=timeframe.minutes)
    candles = []
    for i, (o, h, l, c, v) in enumerate(rows):
        ts = start + step * (i + 1)
        candles.append(Candle(timestamp=ts, open=o, high=h, low=l, close=c, volume=v, symbol=symbol))
    return CandleSeries(candles, symbol=symbol, timeframe=timeframe)
