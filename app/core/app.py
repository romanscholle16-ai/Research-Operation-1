"""Minimal application entry point / lifecycle.

Phase 1 scope only: load config, init logging, init database, init state,
emit start/stop events, shut down cleanly. There is no autonomous research
loop yet - `run()` executes this bounded lifecycle once. A future phase
will replace `run()`'s body with a long-running supervised loop without
changing `startup()` / `shutdown()`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.config.settings import Settings, get_settings
from app.core.events import EventRecorder, EventType
from app.database.connection import Database
from app.logging.setup import LogCategory, get_logger, setup_logging
from app.state.state_manager import StateManager

PROJECT_PHASE = "phase_1_foundation"


class Application:
    """Owns the lifecycle of the foundation components: config, logging,
    database, state, and the event recorder."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._db: Database | None = None
        self._state: StateManager | None = None
        self._events: EventRecorder | None = None
        self._log = None
        self._started = False

    @property
    def db(self) -> Database:
        if self._db is None:
            raise RuntimeError("Application not started. Call startup() first.")
        return self._db

    @property
    def state(self) -> StateManager:
        if self._state is None:
            raise RuntimeError("Application not started. Call startup() first.")
        return self._state

    @property
    def events(self) -> EventRecorder:
        if self._events is None:
            raise RuntimeError("Application not started. Call startup() first.")
        return self._events

    @property
    def is_running(self) -> bool:
        return self._started

    def startup(self) -> None:
        if self._started:
            return

        self.settings.ensure_directories()
        setup_logging(self.settings)
        self._log = get_logger(LogCategory.APPLICATION, "app.core.app")

        self._db = Database(self.settings.database.path, self.settings.database.busy_timeout_seconds)
        self._db.connect()
        self._db.initialize_schema()

        self._state = StateManager(
            self._db,
            checkpoints_dir=self.settings.data.cache_dir / "checkpoints",
            state_dir=self.settings.data.cache_dir / "state",
        )
        self._events = EventRecorder(self._db)

        self._state.set_component_status("application", "starting")
        self._events.record(
            EventType.APPLICATION_STARTED,
            category="application",
            message="Application started",
            payload={"phase": PROJECT_PHASE, "environment": self.settings.application.environment},
        )
        self._state.set_component_status("application", "running")
        self._state.write_project_state(
            {
                "phase": PROJECT_PHASE,
                "status": "running",
                "environment": self.settings.application.environment,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        self._started = True
        self._log.info("application startup complete", extra={"event_type": "application_startup_complete"})

    def shutdown(self) -> None:
        if not self._started:
            return

        assert self._log is not None and self._events is not None and self._state is not None and self._db is not None

        self._events.record(
            EventType.APPLICATION_STOPPED,
            category="application",
            message="Application stopped",
            payload={"phase": PROJECT_PHASE},
        )
        self._state.set_component_status("application", "stopped")
        self._state.write_project_state(
            {
                "phase": PROJECT_PHASE,
                "status": "stopped",
                "stopped_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._log.info("application shutdown complete", extra={"event_type": "application_shutdown_complete"})

        self._db.close()
        self._started = False

    def run(self) -> None:
        """Execute the bounded Phase-1 lifecycle: start up, then shut down.

        Does NOT implement an autonomous research loop - that belongs to a
        later phase. Kept as a single method so a future phase can extend
        the body between startup() and shutdown() without touching either.
        """
        self.startup()
        try:
            pass  # no autonomous work in Phase 1
        finally:
            self.shutdown()

    def __enter__(self) -> "Application":
        self.startup()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.shutdown()


def main() -> None:
    app = Application()
    app.run()


if __name__ == "__main__":
    main()
