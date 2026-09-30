"""Normalized market-data model: candles and candle series.

Timezone policy (see ARCHITECTURE.md "Time handling"): every timestamp
inside the engine is timezone-aware and canonicalized to UTC at the
boundary (`Candle.__post_init__`). Callers may pass any tz-aware
datetime; it is converted to UTC on construction, so internal ordering
and comparisons are never affected by DST or local-time ambiguity.

`Candle.timestamp` is the bar's CLOSE time - the moment this OHLCV data
became fully known. This is the anchor the look-ahead protection in
`app/backtesting/engine.py` relies on: a strategy may only see a candle
once "now" has reached its timestamp, and any signal it produces can only
be filled using a later candle's data.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class Timeframe(str, Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M45 = "45m"
    H1 = "1h"
    H4 = "4h"

    @property
    def minutes(self) -> int:
        return _TIMEFRAME_MINUTES[self]

    def __lt__(self, other: "Timeframe") -> bool:
        if not isinstance(other, Timeframe):
            return NotImplemented
        return self.minutes < other.minutes


_TIMEFRAME_MINUTES: dict[Timeframe, int] = {
    Timeframe.M1: 1,
    Timeframe.M5: 5,
    Timeframe.M15: 15,
    Timeframe.M45: 45,
    Timeframe.H1: 60,
    Timeframe.H4: 240,
}


@dataclass(frozen=True)
class Candle:
    """One OHLCV bar. `timestamp` is the bar's CLOSE time, always UTC."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str = ""

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError(
                f"Candle timestamp must be timezone-aware, got naive datetime {self.timestamp!r}"
            )
        if self.timestamp.tzinfo != timezone.utc:
            object.__setattr__(self, "timestamp", self.timestamp.astimezone(timezone.utc))
        if self.high < self.low:
            raise ValueError(f"Candle high ({self.high}) < low ({self.low}) at {self.timestamp}")
        if not (self.low <= self.open <= self.high):
            raise ValueError(f"Candle open ({self.open}) outside [low, high] at {self.timestamp}")
        if not (self.low <= self.close <= self.high):
            raise ValueError(f"Candle close ({self.close}) outside [low, high] at {self.timestamp}")
        if self.volume < 0:
            raise ValueError(f"Candle volume ({self.volume}) is negative at {self.timestamp}")


class CandleSeries(Sequence[Candle]):
    """An ordered, deterministic, immutable series of candles for one
    symbol + timeframe. Enforces strictly increasing timestamps at
    construction so downstream code never has to re-check ordering."""

    def __init__(self, candles: Sequence[Candle], *, symbol: str, timeframe: Timeframe) -> None:
        self.symbol = symbol
        self.timeframe = timeframe
        self._candles: tuple[Candle, ...] = tuple(candles)
        self._validate_order()

    def _validate_order(self) -> None:
        previous: Candle | None = None
        for candle in self._candles:
            if previous is not None and candle.timestamp <= previous.timestamp:
                raise ValueError(
                    "CandleSeries requires strictly increasing timestamps: "
                    f"{candle.timestamp} does not come after {previous.timestamp}"
                )
            previous = candle

    def __len__(self) -> int:
        return len(self._candles)

    def __getitem__(self, index):  # type: ignore[override]
        if isinstance(index, slice):
            return CandleSeries(self._candles[index], symbol=self.symbol, timeframe=self.timeframe)
        return self._candles[index]

    def __iter__(self) -> Iterator[Candle]:
        return iter(self._candles)

    @property
    def start(self) -> datetime | None:
        return self._candles[0].timestamp if self._candles else None

    @property
    def end(self) -> datetime | None:
        return self._candles[-1].timestamp if self._candles else None

    def index_at_or_before(self, timestamp: datetime) -> int | None:
        """Highest index whose candle timestamp is <= `timestamp`, or None.

        Used for look-ahead-safe multi-timeframe alignment: "what is the
        latest higher-timeframe candle that had already fully closed by
        this point in time".
        """
        result: int | None = None
        for i, candle in enumerate(self._candles):
            if candle.timestamp <= timestamp:
                result = i
            else:
                break
        return result
