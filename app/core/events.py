"""Persistent event system foundation.

The future dashboard's Event Timeline reads from the `events` table. This
module is the only place that writes to it, so event shape stays
consistent. It intentionally does not interpret events - it just records
them durably and mirrors them into the structured log.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.database.connection import Database
from app.logging.setup import LogCategory, get_logger


def _get_log() -> Any:
    # Lazy: avoids configuring the global logging system as a side effect
    # of merely importing this module.
    return get_logger(LogCategory.APPLICATION, "app.core.events")


class EventType(str, Enum):
    """Known event types. Extend as later phases need new ones - this is a
    foundation list covering everything Phase 1 documentation commits to."""

    APPLICATION_STARTED = "application_started"
    APPLICATION_STOPPED = "application_stopped"
    STRATEGY_DISCOVERED = "strategy_discovered"
    STRATEGY_REJECTED = "strategy_rejected"
    STRATEGY_QUALIFIED = "strategy_qualified"
    EXPERIMENT_STARTED = "experiment_started"
    EXPERIMENT_COMPLETED = "experiment_completed"
    WORKER_STARTED = "worker_started"
    WORKER_STOPPED = "worker_stopped"
    WORKER_CRASHED = "worker_crashed"
    SUPERVISOR_DETECTED_ISSUE = "supervisor_detected_issue"
    SUPERVISOR_ATTEMPTED_RECOVERY = "supervisor_attempted_recovery"
    SUPERVISOR_FIXED_ISSUE = "supervisor_fixed_issue"
    AI_INVOKED = "ai_invoked"
    AI_PATCH_CREATED = "ai_patch_created"
    CHECKPOINT_CREATED = "checkpoint_created"
    CHECKPOINT_RESTORED = "checkpoint_restored"
    HOURLY_REPORT_GENERATED = "hourly_report_generated"


@dataclass(frozen=True)
class Event:
    id: str
    event_type: str
    category: str
    message: str | None
    payload: dict[str, Any]
    related_id: str | None
    created_at: str


class EventRecorder:
    """Records events to SQLite and mirrors them into the structured log."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def record(
        self,
        event_type: EventType,
        *,
        category: str = "application",
        message: str | None = None,
        payload: dict[str, Any] | None = None,
        related_id: str | None = None,
    ) -> Event:
        event_id = str(uuid.uuid4())
        payload = payload or {}
        created_at = datetime.now(timezone.utc).isoformat()

        self._db.execute(
            """
            INSERT INTO events (id, event_type, category, message, payload, related_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, event_type.value, category, message, json.dumps(payload, default=str), related_id),
        )

        _get_log().info(
            message or event_type.value,
            extra={"event_type": event_type.value, "related_id": related_id, **payload},
        )

        return Event(
            id=event_id,
            event_type=event_type.value,
            category=category,
            message=message,
            payload=payload,
            related_id=related_id,
            created_at=created_at,
        )

    def list_recent(self, limit: int = 50) -> list[Event]:
        rows = self._db.query_all(
            "SELECT id, event_type, category, message, payload, related_id, created_at "
            "FROM events ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (limit,),
        )
        return [
            Event(
                id=row["id"],
                event_type=row["event_type"],
                category=row["category"],
                message=row["message"],
                payload=json.loads(row["payload"]) if row["payload"] else {},
                related_id=row["related_id"],
                created_at=row["created_at"],
            )
            for row in rows
        ]
