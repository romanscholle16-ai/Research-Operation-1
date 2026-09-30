"""Market-Condition Tester: runs the same strategy/parameters against
different data segments (see segmentation.py) to see how behavior
changes across conditions. Segmentation is basic and deterministic by
design - no regime-detection ML."""

from app.systems.market_conditions.segmentation import (
    Segment,
    segment_by_chronological_chunks,
    segment_by_day_of_week,
    segment_by_session,
    segment_by_volatility,
)
from app.systems.market_conditions.tester import MarketConditionRequest, MarketConditionTester

__all__ = [
    "MarketConditionRequest",
    "MarketConditionTester",
    "Segment",
    "segment_by_chronological_chunks",
    "segment_by_day_of_week",
    "segment_by_session",
    "segment_by_volatility",
]
