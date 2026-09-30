"""Database access for AI research sessions/decisions (migration 4).
AI invocation audit logging (Phase 4 brief section 13) reuses Phase 1's
existing `ai_actions` table rather than adding a fourth new table - its
columns (provider, action_type, related_id, prompt_summary,
result_summary, metadata, created_at) already match what section 13
asks for exactly.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.database.connection import Database
from app.ai.session import ResearchSessionRecord, SessionStatus

_now = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


def _session_row_to_record(row: Any) -> ResearchSessionRecord:
    return ResearchSessionRecord(
        id=row["id"],
        objective=row["objective"],
        status=SessionStatus(row["status"]),
        iteration=row["iteration"],
        max_iterations=row["max_iterations"],
        max_experiments=row["max_experiments"],
        max_failed_experiments=row["max_failed_experiments"],
        max_consecutive_no_progress=row["max_consecutive_no_progress"],
        experiments_run=row["experiments_run"],
        experiments_failed=row["experiments_failed"],
        consecutive_no_progress=row["consecutive_no_progress"],
        stopping_reason=row["stopping_reason"],
        provider_name=row["provider_name"],
        model_name=row["model_name"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
    )


def create_session(
    db: Database,
    *,
    session_id: str,
    objective: str,
    limits: Any,  # app.ai.limits.ResearchLimits - typed loosely to avoid a cycle
    provider_name: str,
    model_name: str,
) -> None:
    db.execute(
        """
        INSERT INTO ai_research_sessions (
            id, objective, status, max_iterations, max_experiments,
            max_failed_experiments, max_consecutive_no_progress,
            provider_name, model_name
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            objective,
            SessionStatus.CREATED.value,
            limits.max_iterations,
            limits.max_experiments,
            limits.max_failed_experiments,
            limits.max_consecutive_no_progress,
            provider_name,
            model_name,
        ),
    )


def update_session_progress(
    db: Database,
    session_id: str,
    *,
    iteration: int,
    experiments_run: int,
    experiments_failed: int,
    consecutive_no_progress: int,
) -> None:
    db.execute(
        """
        UPDATE ai_research_sessions SET
            iteration = ?, experiments_run = ?, experiments_failed = ?,
            consecutive_no_progress = ?
        WHERE id = ?
        """,
        (iteration, experiments_run, experiments_failed, consecutive_no_progress, session_id),
    )


def set_session_status(
    db: Database,
    session_id: str,
    status: SessionStatus,
    *,
    started: bool = False,
    completed: bool = False,
    stopping_reason: str | None = None,
) -> None:
    fields = ["status = ?"]
    params: list[Any] = [status.value]
    if started:
        fields.append("started_at = ?")
        params.append(_now())
    if completed:
        fields.append("completed_at = ?")
        params.append(_now())
    if stopping_reason is not None:
        fields.append("stopping_reason = ?")
        params.append(stopping_reason)
    params.append(session_id)
    db.execute(f"UPDATE ai_research_sessions SET {', '.join(fields)} WHERE id = ?", params)


def load_session(db: Database, session_id: str) -> ResearchSessionRecord | None:
    row = db.query_one("SELECT * FROM ai_research_sessions WHERE id = ?", (session_id,))
    return _session_row_to_record(row) if row else None


def record_decision(
    db: Database,
    *,
    session_id: str,
    iteration: int,
    decision: Any,  # app.ai.decision.ResearchDecision
) -> str:
    decision_id = str(uuid.uuid4())
    db.execute(
        """
        INSERT INTO ai_research_decisions (
            id, session_id, iteration, hypothesis, reasoning_summary,
            requested_experiments, analysis_tasks, stopping_reason, confidence
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            decision_id,
            session_id,
            iteration,
            decision.hypothesis,
            decision.reasoning_summary,
            json.dumps(decision.to_dict()["requested_experiments"], default=str),
            json.dumps(list(decision.analysis_tasks), default=str),
            decision.stopping_reason,
            decision.confidence,
        ),
    )
    return decision_id


def list_decisions(db: Database, session_id: str) -> list[dict[str, Any]]:
    rows = db.query_all(
        "SELECT * FROM ai_research_decisions WHERE session_id = ? ORDER BY iteration", (session_id,)
    )
    return [dict(row) for row in rows]


def link_campaign_to_session(db: Database, *, session_id: str, campaign_id: str, iteration: int) -> None:
    db.execute(
        "INSERT INTO ai_research_session_campaigns (id, session_id, campaign_id, iteration) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), session_id, campaign_id, iteration),
    )


def list_session_campaign_ids(db: Database, session_id: str) -> list[str]:
    rows = db.query_all(
        "SELECT campaign_id FROM ai_research_session_campaigns WHERE session_id = ? ORDER BY iteration",
        (session_id,),
    )
    return [row["campaign_id"] for row in rows]


def list_session_experiments(db: Database, session_id: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    """All research_experiments rows belonging to any campaign linked to
    this session, most recent first. Used by context.py to build a
    bounded "previous experiments" summary - never the whole table."""
    sql = """
        SELECT re.* FROM research_experiments re
        JOIN ai_research_session_campaigns sc ON sc.campaign_id = re.campaign_id
        WHERE sc.session_id = ?
        ORDER BY re.created_at DESC
    """
    params: list[Any] = [session_id]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    rows = db.query_all(sql, params)
    return [dict(row) for row in rows]


def record_ai_action(
    db: Database,
    *,
    provider: str,
    action_type: str,
    related_id: str,
    prompt_summary: str,
    result_summary: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Audit-log one AI invocation, reusing Phase 1's `ai_actions` table.
    `prompt_summary`/`result_summary` must already be bounded by the
    caller - this function does not truncate."""
    db.execute(
        """
        INSERT INTO ai_actions (id, provider, action_type, related_id, prompt_summary, result_summary, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            provider,
            action_type,
            related_id,
            prompt_summary,
            result_summary,
            json.dumps(metadata or {}, default=str),
        ),
    )
