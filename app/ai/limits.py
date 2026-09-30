"""Human-controlled research limits (Phase 4 brief section 8).

`ResearchLimits` is a frozen dataclass constructed once by whoever starts
a `ResearchAgent` run - a human, a config file, a future scheduler. It is
passed to the agent by reference and never regenerated, mutated, or
re-derived from anything the AI produced. `ResearchAgent` only ever
*reads* it to decide when to stop; nothing in `app/ai/` writes to it.
This is the concrete mechanism behind "the AI must never modify these
limits itself" / "must not expand its own research budget" - there is
simply no code path that constructs a new `ResearchLimits` from AI
output.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StoppingReason(str, Enum):
    MAX_ITERATIONS = "max_iterations"
    MAX_EXPERIMENTS = "max_experiments"
    MAX_FAILED_EXPERIMENTS = "max_failed_experiments"
    MAX_CONSECUTIVE_NO_PROGRESS = "max_consecutive_no_progress"
    AI_REQUESTED_STOP = "ai_requested_stop"
    PROVIDER_ERROR = "provider_error"


@dataclass(frozen=True)
class ResearchLimits:
    max_iterations: int = 10
    max_experiments: int = 50
    max_failed_experiments: int = 5
    max_consecutive_no_progress: int = 3

    def __post_init__(self) -> None:
        for name in (
            "max_iterations",
            "max_experiments",
            "max_failed_experiments",
            "max_consecutive_no_progress",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"ResearchLimits.{name} must be >= 1")
