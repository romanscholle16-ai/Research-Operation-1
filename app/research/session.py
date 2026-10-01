"""Persistent web-research session state (Phase 6 brief section 19) -
same pattern as `app/ai/session.py`: every field that matters is written
to SQLite as it changes, so a session can be inspected or reconstructed
at any point without relying on in-memory state surviving a restart.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum


class WebResearchSessionStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


def new_web_session_id() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True)
class WebResearchSessionRecord:
    id: str
    objective: str
    status: WebResearchSessionStatus
    iteration: int
    sources_discovered: int
    sources_retrieved: int
    evidence_count: int
    specification_count: int
    requests_made: int
    stopping_reason: str | None
    final_specification_status: str | None
    provider_name: str | None
    model_name: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
