"""Common interface shared by all five research systems (Phase 3 brief
section 1). Each system is independently executable and importable on
its own, but they all speak the same `ResearchRequest` -> `list[
ExperimentDefinition]` contract, so `CampaignRunner` (runner.py) never
needs to know which system it's driving.

No research system calculates financial performance. `generate_
experiments()` only ever returns `ExperimentDefinition`s - it never calls
`run_backtest()` itself; that happens in `ExperimentRunner`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.backtesting.engine import BacktestConfig
from app.backtesting.market_data import CandleSeries, Timeframe
from app.backtesting.strategy import Strategy
from app.systems.experiment import ExperimentDefinition


@dataclass(frozen=True)
class ResearchRequest:
    """Fields every research system needs, regardless of what it
    specifically varies. Concrete request types (e.g.
    `ParameterExplorerRequest`) add exactly one more field on top of this
    for their system-specific configuration - see each system's module.
    """

    strategy_name: str
    strategy_version: str
    strategy_factory: Callable[[dict[str, Any]], Strategy]
    candles: CandleSeries
    execution_config: BacktestConfig
    higher_timeframes: dict[Timeframe, CandleSeries] = field(default_factory=dict)
    base_parameters: dict[str, Any] = field(default_factory=dict)
    parent_experiment_id: str | None = None


class ResearchSystem(ABC):
    """Subclass and implement `generate_experiments`. Instances are
    stateless with respect to any one call - all inputs come from the
    request, so a system is safe to reuse across many campaigns."""

    name: str = "unnamed_research_system"

    @abstractmethod
    def generate_experiments(self, request: ResearchRequest) -> list[ExperimentDefinition]:
        """Return the experiments this system wants to run for `request`.
        Must not call run_backtest() or compute any financial metric."""
        raise NotImplementedError
