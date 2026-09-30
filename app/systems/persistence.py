"""Database access for campaigns and experiments (research_campaigns /
research_experiments tables, schema migration 3). The only module that
touches those two tables directly - `runner.py` goes through this, never
raw SQL of its own.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.backtesting.market_data import Timeframe
from app.database.connection import Database
from app.systems.campaign import CampaignRecord, CampaignStatus
from app.systems.experiment import ExperimentRecord, ExperimentStatus

_now = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _campaign_row_to_record(row) -> CampaignRecord:
    return CampaignRecord(
        id=row["id"],
        strategy_name=row["strategy_name"],
        research_system=row["research_system"],
        purpose=row["purpose"] or "",
        configuration=json.loads(row["configuration"]) if row["configuration"] else {},
        status=CampaignStatus(row["status"]),
        experiment_count=row["experiment_count"],
        completed_count=row["completed_count"],
        failed_count=row["failed_count"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
    )


def _experiment_row_to_record(row) -> ExperimentRecord:
    return ExperimentRecord(
        id=row["id"],
        campaign_id=row["campaign_id"],
        research_system=row["research_system"],
        strategy_name=row["strategy_name"],
        strategy_version=row["strategy_version"],
        parameters=json.loads(row["parameters"]) if row["parameters"] else {},
        rule_configuration=json.loads(row["rule_configuration"]) if row["rule_configuration"] else {},
        execution_configuration=json.loads(row["execution_configuration"]) if row["execution_configuration"] else {},
        data_identity=row["data_identity"] or "",
        timeframe=row["timeframe"] or "",
        data_start=_parse_dt(row["data_start"]),
        data_end=_parse_dt(row["data_end"]),
        parent_experiment_id=row["parent_experiment_id"],
        status=ExperimentStatus(row["status"]),
        fingerprint=row["fingerprint"],
        backtest_run_id=row["backtest_run_id"],
        result_fingerprint=row["result_fingerprint"],
        duplicate_of_experiment_id=row["duplicate_of_experiment_id"],
        failure_info=row["failure_info"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
    )


def create_campaign(
    db: Database,
    *,
    campaign_id: str,
    strategy_name: str | None,
    research_system: str,
    purpose: str,
    configuration: dict[str, Any],
) -> None:
    db.execute(
        """
        INSERT INTO research_campaigns (id, strategy_name, research_system, purpose, configuration, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (campaign_id, strategy_name, research_system, purpose, json.dumps(configuration, default=str), CampaignStatus.CREATED.value),
    )


def set_campaign_status(db: Database, campaign_id: str, status: CampaignStatus, *, started: bool = False, completed: bool = False) -> None:
    if started:
        db.execute(
            "UPDATE research_campaigns SET status = ?, started_at = ? WHERE id = ?",
            (status.value, _now(), campaign_id),
        )
    elif completed:
        db.execute(
            "UPDATE research_campaigns SET status = ?, completed_at = ? WHERE id = ?",
            (status.value, _now(), campaign_id),
        )
    else:
        db.execute("UPDATE research_campaigns SET status = ? WHERE id = ?", (status.value, campaign_id))


def refresh_campaign_counts(db: Database, campaign_id: str) -> None:
    """Recompute experiment/completed/failed counts from the source of
    truth (research_experiments rows) rather than incrementing counters -
    avoids drift and stays correct under future concurrent execution."""
    db.execute(
        """
        UPDATE research_campaigns SET
            experiment_count = (SELECT COUNT(*) FROM research_experiments WHERE campaign_id = ?),
            completed_count = (SELECT COUNT(*) FROM research_experiments WHERE campaign_id = ? AND status = 'completed'),
            failed_count = (SELECT COUNT(*) FROM research_experiments WHERE campaign_id = ? AND status = 'failed')
        WHERE id = ?
        """,
        (campaign_id, campaign_id, campaign_id, campaign_id),
    )


def load_campaign(db: Database, campaign_id: str) -> CampaignRecord | None:
    row = db.query_one("SELECT * FROM research_campaigns WHERE id = ?", (campaign_id,))
    return _campaign_row_to_record(row) if row else None


def create_experiment(
    db: Database,
    *,
    experiment_id: str,
    campaign_id: str | None,
    research_system: str,
    strategy_name: str,
    strategy_version: str,
    parameters: dict[str, Any],
    rule_configuration: dict[str, Any],
    execution_configuration: dict[str, Any],
    data_identity: str,
    timeframe: Timeframe,
    data_start: datetime | None,
    data_end: datetime | None,
    parent_experiment_id: str | None,
    fingerprint: str,
) -> None:
    db.execute(
        """
        INSERT INTO research_experiments (
            id, campaign_id, research_system, strategy_name, strategy_version,
            parameters, rule_configuration, execution_configuration,
            data_identity, timeframe, data_start, data_end,
            parent_experiment_id, status, fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            experiment_id,
            campaign_id,
            research_system,
            strategy_name,
            strategy_version,
            json.dumps(parameters, default=str),
            json.dumps(rule_configuration, default=str),
            json.dumps(execution_configuration, default=str),
            data_identity,
            timeframe.value,
            data_start.isoformat() if data_start else None,
            data_end.isoformat() if data_end else None,
            parent_experiment_id,
            ExperimentStatus.CREATED.value,
            fingerprint,
        ),
    )


def set_experiment_status(
    db: Database,
    experiment_id: str,
    status: ExperimentStatus,
    *,
    started: bool = False,
    completed: bool = False,
    backtest_run_id: str | None = None,
    result_fingerprint: str | None = None,
    duplicate_of_experiment_id: str | None = None,
    failure_info: str | None = None,
) -> None:
    fields = ["status = ?"]
    params: list[Any] = [status.value]
    if started:
        fields.append("started_at = ?")
        params.append(_now())
    if completed:
        fields.append("completed_at = ?")
        params.append(_now())
    if backtest_run_id is not None:
        fields.append("backtest_run_id = ?")
        params.append(backtest_run_id)
    if result_fingerprint is not None:
        fields.append("result_fingerprint = ?")
        params.append(result_fingerprint)
    if duplicate_of_experiment_id is not None:
        fields.append("duplicate_of_experiment_id = ?")
        params.append(duplicate_of_experiment_id)
    if failure_info is not None:
        fields.append("failure_info = ?")
        params.append(failure_info)
    params.append(experiment_id)
    db.execute(f"UPDATE research_experiments SET {', '.join(fields)} WHERE id = ?", params)


def load_experiment(db: Database, experiment_id: str) -> ExperimentRecord | None:
    row = db.query_one("SELECT * FROM research_experiments WHERE id = ?", (experiment_id,))
    return _experiment_row_to_record(row) if row else None


def find_completed_by_fingerprint(db: Database, fingerprint: str) -> ExperimentRecord | None:
    row = db.query_one(
        "SELECT * FROM research_experiments WHERE fingerprint = ? AND status = 'completed' "
        "AND duplicate_of_experiment_id IS NULL ORDER BY created_at ASC LIMIT 1",
        (fingerprint,),
    )
    return _experiment_row_to_record(row) if row else None


def list_experiments_for_campaign(db: Database, campaign_id: str) -> list[ExperimentRecord]:
    rows = db.query_all(
        "SELECT * FROM research_experiments WHERE campaign_id = ? ORDER BY created_at", (campaign_id,)
    )
    return [_experiment_row_to_record(row) for row in rows]
