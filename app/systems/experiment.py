"""The experiment model shared by all five research systems.

Lineage (Phase 3 brief section 2):

    Strategy -> Research Campaign -> Experiment -> Backtest Run -> Backtest Result

`ExperimentDefinition` is the *plan* for an experiment (research-system
output, before it runs): everything `ExperimentRunner` needs to invoke
`app.backtesting.run_backtest()`. `ExperimentRecord` is the *persisted*
row (research_experiments table) after `ExperimentRunner` has processed
it - it never holds live objects (candles, a Strategy instance), only the
serializable facts. "Backtest Run"/"Backtest Result" are exactly Phase
2's `experiments` table row and `BacktestResult` - this module does not
duplicate either.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from app.backtesting.engine import BacktestConfig
from app.backtesting.market_data import CandleSeries
from app.backtesting.strategy import Strategy


class ExperimentStatus(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


def new_experiment_id() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True)
class ExperimentDefinition:
    """A fully-specified, not-yet-executed experiment. Produced by a
    `ResearchSystem`, consumed by `ExperimentRunner`.

    `strategy_factory` is what keeps every research system generic: it
    takes the resolved `parameters` for this one experiment and returns a
    ready-to-run `Strategy` instance. No research system hardcodes a
    particular trading strategy (Phase 3 brief section 1/PARAMETER
    EXPLORER).
    """

    research_system: str
    strategy_name: str
    strategy_version: str
    strategy_factory: Callable[[dict[str, Any]], Strategy]
    parameters: dict[str, Any]
    candles: CandleSeries
    execution_config: BacktestConfig
    rule_configuration: dict[str, Any] = field(default_factory=dict)
    higher_timeframes: dict[Any, CandleSeries] = field(default_factory=dict)
    parent_experiment_id: str | None = None
    id: str = field(default_factory=new_experiment_id)

    def build_strategy(self) -> Strategy:
        return self.strategy_factory(self.parameters)


@dataclass(frozen=True)
class ExperimentRecord:
    """The persisted state of an experiment (mirrors the
    `research_experiments` table - see app/systems/persistence.py)."""

    id: str
    campaign_id: str | None
    research_system: str
    strategy_name: str
    strategy_version: str
    parameters: dict[str, Any]
    rule_configuration: dict[str, Any]
    execution_configuration: dict[str, Any]
    data_identity: str
    timeframe: str
    data_start: datetime | None
    data_end: datetime | None
    parent_experiment_id: str | None
    status: ExperimentStatus
    fingerprint: str
    backtest_run_id: str | None
    result_fingerprint: str | None
    duplicate_of_experiment_id: str | None
    failure_info: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
