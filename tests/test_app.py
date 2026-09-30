from app.config.settings import Settings
from app.core.app import Application


def test_startup_initializes_all_components(settings: Settings) -> None:
    app = Application(settings)
    app.startup()
    try:
        assert app.is_running
        assert settings.database.path.exists()

        status = app.state.get_component_status("application")
        assert status is not None
        assert status.status == "running"

        events = app.events.list_recent(limit=10)
        event_types = [e.event_type for e in events]
        assert "application_started" in event_types
    finally:
        app.shutdown()


def test_shutdown_is_clean_and_recorded(settings: Settings) -> None:
    app = Application(settings)
    app.startup()
    app.shutdown()

    assert not app.is_running

    # shutdown closed our handle, so reopen read-only to verify persisted state
    from app.database.connection import Database

    db = Database(settings.database.path, settings.database.busy_timeout_seconds)
    db.connect()
    try:
        row = db.query_one("SELECT status FROM system_status WHERE component = 'application'")
        assert row["status"] == "stopped"

        event_rows = db.query_all(
            "SELECT event_type FROM events WHERE event_type IN ('application_started', 'application_stopped')"
        )
        event_types = {row["event_type"] for row in event_rows}
        assert event_types == {"application_started", "application_stopped"}
    finally:
        db.close()


def test_shutdown_without_startup_is_a_no_op(settings: Settings) -> None:
    app = Application(settings)
    app.shutdown()  # must not raise
    assert not app.is_running


def test_startup_is_idempotent(settings: Settings) -> None:
    app = Application(settings)
    app.startup()
    try:
        app.startup()  # second call should be a no-op, not raise or duplicate events
        events = app.events.list_recent(limit=10)
        started_count = sum(1 for e in events if e.event_type == "application_started")
        assert started_count == 1
    finally:
        app.shutdown()


def test_run_executes_full_lifecycle(settings: Settings) -> None:
    app = Application(settings)
    app.run()
    assert not app.is_running


def test_context_manager_starts_and_stops(settings: Settings) -> None:
    with Application(settings) as app:
        assert app.is_running
    assert not app.is_running


def test_project_state_file_reflects_lifecycle(settings: Settings) -> None:
    app = Application(settings)
    app.startup()
    running_state = app.state.read_project_state()
    assert running_state["status"] == "running"
    app.shutdown()

    from app.state.state_manager import StateManager
    from app.database.connection import Database

    db = Database(settings.database.path, settings.database.busy_timeout_seconds)
    db.connect()
    try:
        state = StateManager(
            db,
            checkpoints_dir=settings.data.cache_dir / "checkpoints",
            state_dir=settings.data.cache_dir / "state",
        )
        stopped_state = state.read_project_state()
        assert stopped_state["status"] == "stopped"
    finally:
        db.close()
