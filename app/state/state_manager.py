"""State and checkpoint foundation.

Two complementary mechanisms, both project-local:

1. Component status lives in the `system_status` SQLite table - the
   source of truth for "what is running and how is it doing".
2. Checkpoints are point-in-time JSON snapshots, written to both the
   `checkpoints` table *and* a plain file under
   `data/cache/checkpoints/`, so a snapshot can still be read even if the
   database itself is the thing that needs recovering.

This is deliberately simple: a full autonomous-recovery system (deciding
*when* to checkpoint, *when* to restore, retry policy, etc.) is out of
scope for Phase 1 and belongs to the future Supervisor Agent.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.database.connection import Database


@dataclass(frozen=True)
class ComponentStatus:
    component: str
    status: str
    detail: str | None
    metadata: dict[str, Any]
    updated_at: str


@dataclass(frozen=True)
class Checkpoint:
    id: str
    label: str | None
    component: str
    state: dict[str, Any]
    metadata: dict[str, Any]
    created_at: str


class StateManager:
    def __init__(self, database: Database, checkpoints_dir: Path, state_dir: Path) -> None:
        self._db = database
        self._checkpoints_dir = checkpoints_dir
        self._state_dir = state_dir
        self._checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self._state_dir.mkdir(parents=True, exist_ok=True)

    # -- component status -------------------------------------------------

    def set_component_status(
        self,
        component: str,
        status: str,
        *,
        detail: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        metadata = metadata or {}
        self._db.execute(
            """
            INSERT INTO system_status (component, status, detail, metadata, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(component) DO UPDATE SET
                status = excluded.status,
                detail = excluded.detail,
                metadata = excluded.metadata,
                updated_at = excluded.updated_at
            """,
            (component, status, detail, json.dumps(metadata, default=str)),
        )

    def get_component_status(self, component: str) -> ComponentStatus | None:
        row = self._db.query_one(
            "SELECT component, status, detail, metadata, updated_at FROM system_status WHERE component = ?",
            (component,),
        )
        if row is None:
            return None
        return ComponentStatus(
            component=row["component"],
            status=row["status"],
            detail=row["detail"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            updated_at=row["updated_at"],
        )

    def get_all_component_status(self) -> list[ComponentStatus]:
        rows = self._db.query_all(
            "SELECT component, status, detail, metadata, updated_at FROM system_status ORDER BY component"
        )
        return [
            ComponentStatus(
                component=row["component"],
                status=row["status"],
                detail=row["detail"],
                metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    # -- checkpoints --------------------------------------------------------

    def create_checkpoint(
        self,
        component: str,
        state: dict[str, Any],
        *,
        label: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Checkpoint:
        checkpoint_id = str(uuid.uuid4())
        metadata = metadata or {}
        created_at = datetime.now(timezone.utc).isoformat()
        state_json = json.dumps(state, default=str)

        self._db.execute(
            """
            INSERT INTO checkpoints (id, label, component, state_snapshot, metadata)
            VALUES (?, ?, ?, ?, ?)
            """,
            (checkpoint_id, label, component, state_json, json.dumps(metadata, default=str)),
        )

        # Redundant file copy, so a checkpoint survives even if the DB file
        # itself is corrupt or missing at recovery time.
        file_path = self._checkpoints_dir / f"{checkpoint_id}.json"
        file_path.write_text(
            json.dumps(
                {
                    "id": checkpoint_id,
                    "label": label,
                    "component": component,
                    "state": state,
                    "metadata": metadata,
                    "created_at": created_at,
                },
                default=str,
                indent=2,
            ),
            encoding="utf-8",
        )

        return Checkpoint(
            id=checkpoint_id,
            label=label,
            component=component,
            state=state,
            metadata=metadata,
            created_at=created_at,
        )

    def get_latest_checkpoint(self, component: str) -> Checkpoint | None:
        row = self._db.query_one(
            """
            SELECT id, label, component, state_snapshot, metadata, created_at
            FROM checkpoints WHERE component = ?
            ORDER BY created_at DESC, rowid DESC LIMIT 1
            """,
            (component,),
        )
        if row is None:
            return None
        return Checkpoint(
            id=row["id"],
            label=row["label"],
            component=row["component"],
            state=json.loads(row["state_snapshot"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=row["created_at"],
        )

    # -- lightweight project-state snapshot ---------------------------------

    def write_project_state(self, state: dict[str, Any]) -> Path:
        """Write a small JSON snapshot describing overall project state -
        e.g. active phase, last startup time - for fast, DB-independent
        inspection during recovery or debugging."""
        path = self._state_dir / "current_state.json"
        path.write_text(json.dumps(state, default=str, indent=2), encoding="utf-8")
        return path

    def read_project_state(self) -> dict[str, Any] | None:
        path = self._state_dir / "current_state.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
