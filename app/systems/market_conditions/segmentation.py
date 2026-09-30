"""Deterministic, basic segmentation of candle data into named subsets
(Phase 3 brief section 4). No regime-detection ML, no sophistication
beyond simple, explainable splits - median-based volatility split,
calendar day-of-week, fixed time-of-day session windows, and equal-sized
chronological chunks (also reused by the Adversarial system for
leave-one-period-out testing).

A `Segment`'s `candles` need not be contiguous - `CandleSeries` only
requires strictly increasing timestamps (see market_data.py), so a
filtered, non-contiguous subset (e.g. "every Tuesday candle") is valid.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import time

from app.backtesting.market_data import Candle, CandleSeries

WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


@dataclass(frozen=True)
class Segment:
    label: str
    method: str
    candles: CandleSeries


def _rebuild(candles: list[Candle], *, symbol: str, timeframe) -> CandleSeries:
    return CandleSeries(candles, symbol=symbol, timeframe=timeframe)


def segment_by_chronological_chunks(series: CandleSeries, chunk_count: int) -> list[Segment]:
    """Split into `chunk_count` contiguous, (near-)equal chunks in time
    order. Useful both as a market-condition dimension ("early vs late
    sample") and as the leave-one-out unit for the Adversarial system."""
    if chunk_count < 1:
        raise ValueError("chunk_count must be >= 1")
    n = len(series)
    segments = []
    for i in range(chunk_count):
        start = (n * i) // chunk_count
        end = (n * (i + 1)) // chunk_count
        segments.append(
            Segment(label=f"chunk_{i + 1}_of_{chunk_count}", method="chronological_chunks", candles=series[start:end])
        )
    return segments


def segment_leave_one_out_chronological(series: CandleSeries, chunk_count: int) -> list[Segment]:
    """The complement of `segment_by_chronological_chunks`: one segment
    per chunk, containing every candle EXCEPT that chunk. Used by the
    Adversarial system to test "does performance depend on one tiny
    market period" - dropping a contiguous middle range preserves the
    remaining candles' strict time ordering, so each result is a valid
    `CandleSeries`.
    """
    chunks = segment_by_chronological_chunks(series, chunk_count)
    segments = []
    for i in range(len(chunks)):
        remaining: list[Candle] = []
        for j, chunk in enumerate(chunks):
            if j != i:
                remaining.extend(chunk.candles)
        segments.append(
            Segment(
                label=f"without_chunk_{i + 1}_of_{chunk_count}",
                method="leave_one_out_chronological",
                candles=_rebuild(remaining, symbol=series.symbol, timeframe=series.timeframe),
            )
        )
    return segments


def segment_by_volatility(series: CandleSeries) -> list[Segment]:
    """Median-split by each candle's (high - low) range into two
    non-contiguous subsets. A simple, explainable stand-in for a
    volatility regime - not a sophisticated detector."""
    if len(series) == 0:
        return [
            Segment(label="low_volatility", method="volatility_median_split", candles=series),
            Segment(label="high_volatility", method="volatility_median_split", candles=series),
        ]
    ranges = [c.high - c.low for c in series]
    median = statistics.median(ranges)
    low = [c for c in series if (c.high - c.low) <= median]
    high = [c for c in series if (c.high - c.low) > median]
    return [
        Segment(label="low_volatility", method="volatility_median_split", candles=_rebuild(low, symbol=series.symbol, timeframe=series.timeframe)),
        Segment(label="high_volatility", method="volatility_median_split", candles=_rebuild(high, symbol=series.symbol, timeframe=series.timeframe)),
    ]


def segment_by_day_of_week(series: CandleSeries) -> list[Segment]:
    """One segment per weekday (UTC) actually present in the data."""
    buckets: dict[int, list[Candle]] = {i: [] for i in range(7)}
    for c in series:
        buckets[c.timestamp.weekday()].append(c)
    segments = []
    for weekday, candles in buckets.items():
        if not candles:
            continue
        segments.append(
            Segment(
                label=WEEKDAY_NAMES[weekday],
                method="day_of_week",
                candles=_rebuild(candles, symbol=series.symbol, timeframe=series.timeframe),
            )
        )
    return segments


def segment_by_session(series: CandleSeries, sessions: dict[str, tuple[time, time]]) -> list[Segment]:
    """`sessions` maps a name to a (start, end) UTC time-of-day window,
    e.g. {"london": (time(8, 0), time(16, 30))}. Non-wrapping windows
    only (start < end) - a session crossing UTC midnight is out of scope
    for this simple version."""
    segments = []
    for name, (start, end) in sessions.items():
        if start >= end:
            raise ValueError(f"Session '{name}' must not wrap midnight (start < end required)")
        matched = [c for c in series if start <= c.timestamp.time() < end]
        segments.append(
            Segment(
                label=name,
                method="session",
                candles=_rebuild(matched, symbol=series.symbol, timeframe=series.timeframe),
            )
        )
    return segments
