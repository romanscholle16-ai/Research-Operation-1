"""Persistent research session state (Phase 4 brief section 12). A
session survives application restart and process interruption because
every field that matters is written to SQLite as it changes - there is
no in-memory-only state `ResearchAgent` depends on to resume correctly
(see `persistence.py` and `agent.py::ResearchAgent.resume`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum


class SessionStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


def new_session_id() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True)
class ResearchSessionRecord:
    id: str
    objective: str
    status: SessionStatus
    iteration: int
    max_iterations: int
    max_experiments: int
    max_failed_experiments: int
    max_consecutive_no_progress: int
    experiments_run: int
    experiments_failed: int
    consecutive_no_progress: int
    stopping_reason: str | None
    provider_name: str | None
    model_name: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
