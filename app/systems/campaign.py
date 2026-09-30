"""Research campaigns: the grouping concept above individual experiments
(Phase 3 brief section 7). A campaign is created once per
`ResearchSystem.generate_experiments()` call submitted to
`CampaignRunner`, and tracks aggregate progress across its experiments.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any


class CampaignStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"


def new_campaign_id() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True)
class CampaignRecord:
    id: str
    strategy_name: str | None
    research_system: str
    purpose: str
    configuration: dict[str, Any]
    status: CampaignStatus
    experiment_count: int
    completed_count: int
    failed_count: int
    created_at: str
    started_at: str | None
    completed_at: str | None
