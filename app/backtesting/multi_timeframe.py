"""Look-ahead-safe access to multiple synchronized timeframes.

A strategy trading a 5m primary timeframe might also want to see 1h
candles. The 1h candle that CONTAINS "now" is still forming and must not
be visible - only 1h candles that have already CLOSED at or before the
primary timeframe's current candle close are. `MultiTimeframeView` is the
only sanctioned way a `Strategy` reads another timeframe, specifically so
this rule can't be bypassed by reaching into a full series directly.
"""

from __future__ import annotations

from datetime import datetime

from app.backtesting.market_data import CandleSeries, Timeframe


class MultiTimeframeView:
    def __init__(self, series_by_timeframe: dict[Timeframe, CandleSeries]) -> None:
        self._series = dict(series_by_timeframe)

    @property
    def timeframes(self) -> tuple[Timeframe, ...]:
        return tuple(self._series.keys())

    def as_of(self, timeframe: Timeframe, timestamp: datetime) -> CandleSeries:
        """All candles of `timeframe` that had fully closed at or before
        `timestamp`. Returns an empty series if none have closed yet."""
        series = self._series[timeframe]
        end_index = series.index_at_or_before(timestamp)
        if end_index is None:
            return series[:0]
        return series[: end_index + 1]
