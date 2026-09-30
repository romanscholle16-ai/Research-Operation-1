"""Deterministic research-context construction (Phase 4 brief section
11). Deliberately bounded: `build_research_context` pulls at most the
last `max_previous_experiments` experiments for this session, with only
their key metrics (net profit, trade count, win rate, drawdown, profit
factor, costs) - never full trade lists, never the whole database. The
AI provider is the only thing that receives a `ResearchContext`; the
context builder never talks to an `AIProvider` itself, keeping "what the
AI sees" and "how the AI is invoked" independently testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.ai.catalog import ResearchCatalog
from app.ai.limits import ResearchLimits
from app.ai.persistence import list_session_experiments
from app.backtesting.persistence import load_experiment_metrics
from app.database.connection import Database

DEFAULT_MAX_PREVIOUS_EXPERIMENTS = 10


@dataclass(frozen=True)
class ExperimentSummary:
    experiment_id: str
    research_system: str
    status: str
    parameters: dict[str, Any]
    rule_configuration: dict[str, Any]
    net_profit: float | None
    total_trades: float | None
    win_rate: float | None
    max_drawdown: float | None
    profit_factor: float | None
    total_fees: float | None
    total_slippage: float | None


@dataclass(frozen=True)
class ResearchContext:
    session_id: str
    objective: str
    iteration: int
    strategy_name: str
    strategy_version: str
    timeframe: str
    data_identity: str
    execution_assumptions: dict[str, Any]
    available_research_systems: tuple[str, ...]
    available_rule_variant_names: tuple[str, ...]
    available_execution_variant_names: tuple[str, ...]
    previous_hypotheses: tuple[str, ...]
    previous_experiments: tuple[ExperimentSummary, ...]
    limits: dict[str, int]
    experiments_run: int
    experiments_failed: int
    consecutive_no_progress: int

    def summary(self, *, max_chars: int = 2000) -> str:
        """A short, bounded, human-readable rendering - what actually
        gets logged/audited (app.ai.persistence.record_ai_action), never
        the full structured object."""
        lines = [
            f"objective={self.objective!r} iteration={self.iteration}",
            f"strategy={self.strategy_name}@{self.strategy_version} timeframe={self.timeframe}",
            f"previous_experiments={len(self.previous_experiments)} "
            f"run={self.experiments_run} failed={self.experiments_failed} "
            f"no_progress_streak={self.consecutive_no_progress}",
        ]
        text = "\n".join(lines)
        return text[:max_chars]


def _data_identity(catalog: ResearchCatalog) -> str:
    from app.backtesting.result import compute_data_identity

    return compute_data_identity(catalog.candles)


def build_research_context(
    db: Database,
    *,
    session_id: str,
    objective: str,
    iteration: int,
    catalog: ResearchCatalog,
    limits: ResearchLimits,
    previous_hypotheses: list[str],
    experiments_run: int,
    experiments_failed: int,
    consecutive_no_progress: int,
    max_previous_experiments: int = DEFAULT_MAX_PREVIOUS_EXPERIMENTS,
) -> ResearchContext:
    from app.backtesting.result import ExecutionAssumptions

    execution_assumptions = ExecutionAssumptions(
        starting_capital=catalog.execution_config.starting_capital,
        fee_model=catalog.execution_config.fee_model,
        slippage_model=catalog.execution_config.slippage_model,
        intrabar_policy=catalog.execution_config.intrabar_policy,
    ).to_dict()

    rows = list_session_experiments(db, session_id, limit=max_previous_experiments)
    summaries = []
    for row in rows:
        metrics = load_experiment_metrics(db, row["backtest_run_id"]) if row["backtest_run_id"] else {}
        summaries.append(
            ExperimentSummary(
                experiment_id=row["id"],
                research_system=row["research_system"],
                status=row["status"],
                parameters=_json_or_empty(row["parameters"]),
                rule_configuration=_json_or_empty(row["rule_configuration"]),
                net_profit=metrics.get("net_profit"),
                total_trades=metrics.get("total_trades"),
                win_rate=metrics.get("win_rate"),
                max_drawdown=metrics.get("max_drawdown"),
                profit_factor=metrics.get("profit_factor"),
                total_fees=metrics.get("total_fees"),
                total_slippage=metrics.get("total_slippage"),
            )
        )

    return ResearchContext(
        session_id=session_id,
        objective=objective,
        iteration=iteration,
        strategy_name=catalog.strategy_name,
        strategy_version=catalog.strategy_version,
        timeframe=catalog.execution_config.timeframe.value,
        data_identity=_data_identity(catalog),
        execution_assumptions=execution_assumptions,
        available_research_systems=ResearchCatalog.KNOWN_RESEARCH_SYSTEMS,
        available_rule_variant_names=tuple(catalog.rule_variants.keys()),
        available_execution_variant_names=tuple(catalog.execution_variants.keys()),
        previous_hypotheses=tuple(previous_hypotheses),
        previous_experiments=tuple(summaries),
        limits={
            "max_iterations": limits.max_iterations,
            "max_experiments": limits.max_experiments,
            "max_failed_experiments": limits.max_failed_experiments,
            "max_consecutive_no_progress": limits.max_consecutive_no_progress,
        },
        experiments_run=experiments_run,
        experiments_failed=experiments_failed,
        consecutive_no_progress=consecutive_no_progress,
    )


def _json_or_empty(raw: str | None) -> dict[str, Any]:
    import json

    return json.loads(raw) if raw else {}
