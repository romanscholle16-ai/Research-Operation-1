"""Experiment and campaign execution (Phase 3 brief sections 5-7).

`ExperimentRunner.execute()` is a pure function of `(definition,
campaign_id)` plus the database - it holds no state of its own between
calls. That is deliberate: it is what makes future concurrent execution
possible without a rewrite (brief section 11) - a thread/process pool
could call `execute()` for many experiments in parallel today, each
against its own `Database` connection (SQLite + WAL, already enabled in
Phase 1, supports multiple connections; a single `sqlite3.Connection` is
not thread-safe, so each worker would need its own). `CampaignRunner`
currently loops sequentially (`for definition in definitions:
self._runner.execute(...)`) - that loop body is exactly what a future
`ThreadPoolExecutor.map`/similar would replace, without touching
`ExperimentRunner` itself.

Never computes P&L or any financial metric - `run_backtest()` does that;
this module only orchestrates calling it and recording the outcome.
"""

from __future__ import annotations

import dataclasses
import traceback
from typing import Any

from app.backtesting.engine import run_backtest
from app.backtesting.persistence import save_backtest_result
from app.backtesting.result import ExecutionAssumptions
from app.core.events import EventRecorder, EventType
from app.database.connection import Database
from app.logging.setup import LogCategory, get_logger
from app.systems.campaign import CampaignRecord, CampaignStatus, new_campaign_id
from app.systems.experiment import ExperimentDefinition, ExperimentRecord, ExperimentStatus
from app.systems.fingerprint import compute_experiment_fingerprint
from app.systems import persistence


class ExperimentRunner:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._events = EventRecorder(db)
        self._log = get_logger(LogCategory.EXPERIMENT, "app.systems.runner")

    def execute(self, definition: ExperimentDefinition, *, campaign_id: str | None = None) -> ExperimentRecord:
        fingerprint, data_identity = compute_experiment_fingerprint(definition)
        # Resolved parameters must reach BacktestConfig.strategy_params: it
        # is both what Phase 2's own fingerprint/unique-index uses to tell
        # backtests apart (app/backtesting/engine.py) and what a Strategy
        # sees via StrategyContext.params. Without this, two experiments
        # that only differ by `definition.parameters` (e.g. a Parameter
        # Explorer sweep) would collide on Phase 2's `experiments.
        # fingerprint` UNIQUE index even though they are genuinely
        # different experiments here.
        config = dataclasses.replace(definition.execution_config, strategy_params=definition.parameters)
        execution_configuration = ExecutionAssumptions(
            starting_capital=config.starting_capital,
            fee_model=config.fee_model,
            slippage_model=config.slippage_model,
            intrabar_policy=config.intrabar_policy,
        ).to_dict()

        log_extra: dict[str, Any] = {
            "system": definition.research_system,
            "experiment_id": definition.id,
            "campaign_id": campaign_id,
        }

        persistence.create_experiment(
            self._db,
            experiment_id=definition.id,
            campaign_id=campaign_id,
            research_system=definition.research_system,
            strategy_name=definition.strategy_name,
            strategy_version=definition.strategy_version,
            parameters=definition.parameters,
            rule_configuration=definition.rule_configuration,
            execution_configuration=execution_configuration,
            data_identity=data_identity,
            timeframe=config.timeframe,
            data_start=definition.candles.start,
            data_end=definition.candles.end,
            parent_experiment_id=definition.parent_experiment_id,
            fingerprint=fingerprint,
        )
        self._events.record(
            EventType.EXPERIMENT_CREATED,
            category="experiment",
            message=f"experiment created ({definition.research_system})",
            payload={"research_system": definition.research_system, "fingerprint": fingerprint},
            related_id=definition.id,
        )
        self._log.info("experiment created", extra=log_extra)

        existing = persistence.find_completed_by_fingerprint(self._db, fingerprint)
        if existing is not None:
            persistence.set_experiment_status(
                self._db,
                definition.id,
                ExperimentStatus.COMPLETED,
                completed=True,
                backtest_run_id=existing.backtest_run_id,
                result_fingerprint=existing.result_fingerprint,
                duplicate_of_experiment_id=existing.id,
            )
            self._events.record(
                EventType.EXPERIMENT_SKIPPED_DUPLICATE,
                category="experiment",
                message="duplicate of an already-completed experiment; backtest not re-run",
                payload={"duplicate_of_experiment_id": existing.id, "fingerprint": fingerprint},
                related_id=definition.id,
            )
            self._log.info("experiment skipped as duplicate", extra={**log_extra, "duplicate_of": existing.id})
            if campaign_id:
                persistence.refresh_campaign_counts(self._db, campaign_id)
            return persistence.load_experiment(self._db, definition.id)  # type: ignore[return-value]

        persistence.set_experiment_status(self._db, definition.id, ExperimentStatus.RUNNING, started=True)
        self._events.record(
            EventType.EXPERIMENT_STARTED,
            category="experiment",
            payload={"research_system": definition.research_system},
            related_id=definition.id,
        )
        self._log.info("experiment started", extra=log_extra)

        try:
            strategy = definition.build_strategy()
            result = run_backtest(strategy, definition.candles, config)
            save_backtest_result(self._db, result)
            persistence.set_experiment_status(
                self._db,
                definition.id,
                ExperimentStatus.COMPLETED,
                completed=True,
                backtest_run_id=result.run_id,
                result_fingerprint=result.fingerprint,
            )
            self._events.record(
                EventType.EXPERIMENT_COMPLETED,
                category="experiment",
                payload={
                    "backtest_run_id": result.run_id,
                    "total_trades": result.metrics.total_trades,
                    "net_profit": result.metrics.net_profit,
                },
                related_id=definition.id,
            )
            self._log.info(
                "experiment completed",
                extra={**log_extra, "total_trades": result.metrics.total_trades, "net_profit": result.metrics.net_profit},
            )
        except Exception as exc:  # noqa: BLE001 - deterministically recorded, never re-raised (brief section 5)
            failure_info = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
            persistence.set_experiment_status(
                self._db, definition.id, ExperimentStatus.FAILED, completed=True, failure_info=failure_info
            )
            self._events.record(
                EventType.EXPERIMENT_FAILED,
                category="experiment",
                message=f"{type(exc).__name__}: {exc}",
                payload={"research_system": definition.research_system},
                related_id=definition.id,
            )
            self._log.error("experiment failed", extra={**log_extra, "error": f"{type(exc).__name__}: {exc}"})

        if campaign_id:
            persistence.refresh_campaign_counts(self._db, campaign_id)
        return persistence.load_experiment(self._db, definition.id)  # type: ignore[return-value]


class CampaignRunner:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._events = EventRecorder(db)
        self._experiment_runner = ExperimentRunner(db)
        self._log = get_logger(LogCategory.RESEARCH, "app.systems.runner")

    def run(
        self,
        definitions: list[ExperimentDefinition],
        *,
        research_system: str,
        strategy_name: str | None,
        purpose: str,
        configuration: dict[str, Any] | None = None,
    ) -> CampaignRecord:
        campaign_id = new_campaign_id()
        configuration = configuration or {}

        persistence.create_campaign(
            self._db,
            campaign_id=campaign_id,
            strategy_name=strategy_name,
            research_system=research_system,
            purpose=purpose,
            configuration=configuration,
        )
        self._events.record(
            EventType.CAMPAIGN_CREATED,
            category="research",
            message=f"campaign created ({research_system})",
            payload={"research_system": research_system, "purpose": purpose, "experiment_count": len(definitions)},
            related_id=campaign_id,
        )

        persistence.set_campaign_status(self._db, campaign_id, CampaignStatus.RUNNING, started=True)
        self._events.record(EventType.CAMPAIGN_STARTED, category="research", related_id=campaign_id)
        self._log.info(
            "campaign started",
            extra={"system": research_system, "campaign_id": campaign_id, "experiment_count": len(definitions)},
        )

        # Sequential today; each iteration is independent of the others via
        # ExperimentRunner.execute(), so this is the one line a future
        # concurrent executor would replace (see module docstring).
        for definition in definitions:
            self._experiment_runner.execute(definition, campaign_id=campaign_id)

        persistence.refresh_campaign_counts(self._db, campaign_id)
        persistence.set_campaign_status(self._db, campaign_id, CampaignStatus.COMPLETED, completed=True)
        record = persistence.load_campaign(self._db, campaign_id)
        assert record is not None

        self._events.record(
            EventType.CAMPAIGN_COMPLETED,
            category="research",
            payload={
                "experiment_count": record.experiment_count,
                "completed_count": record.completed_count,
                "failed_count": record.failed_count,
            },
            related_id=campaign_id,
        )
        self._log.info(
            "campaign completed",
            extra={
                "system": research_system,
                "campaign_id": campaign_id,
                "completed_count": record.completed_count,
                "failed_count": record.failed_count,
            },
        )
        return record
