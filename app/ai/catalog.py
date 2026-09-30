"""Everything a research session needs that is NOT AI-authorable: the
strategy under test, the market data, the base execution assumptions,
and pre-built catalogs of rule/execution variants the AI may select by
name (Phase 4 brief section 5's safety boundary - the AI proposes, this
is assembled by a human/deterministic caller ahead of time).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.backtesting.engine import BacktestConfig
from app.backtesting.market_data import CandleSeries, Timeframe
from app.backtesting.strategy import Strategy
from app.systems.risk_execution import ExecutionVariant
from app.systems.rule_explorer import RuleVariant


@dataclass(frozen=True)
class ResearchCatalog:
    strategy_name: str
    strategy_version: str
    strategy_factory: Callable[[dict[str, Any]], Strategy]
    candles: CandleSeries
    execution_config: BacktestConfig
    higher_timeframes: dict[Timeframe, CandleSeries] = field(default_factory=dict)
    rule_variants: dict[str, RuleVariant] = field(default_factory=dict)
    execution_variants: dict[str, ExecutionVariant] = field(default_factory=dict)

    KNOWN_RESEARCH_SYSTEMS = (
        "parameter_explorer",
        "rule_explorer",
        "risk_execution",
        "market_conditions",
        "adversarial",
    )
    KNOWN_SEGMENTATION_METHODS = ("chronological_chunks", "volatility", "day_of_week")
