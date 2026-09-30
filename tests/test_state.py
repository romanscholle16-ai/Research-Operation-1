from app.config.settings import Settings
from app.database.connection import Database
from app.state.state_manager import StateManager


def _make_state_manager(database: Database, settings: Settings) -> StateManager:
    return StateManager(
        database,
        checkpoints_dir=settings.data.cache_dir / "checkpoints",
        state_dir=settings.data.cache_dir / "state",
    )


def test_set_and_get_component_status(database: Database, settings: Settings) -> None:
    state = _make_state_manager(database, settings)
    state.set_component_status("backtesting_engine", "running", detail="processing experiment 42")

    status = state.get_component_status("backtesting_engine")
    assert status is not None
    assert status.status == "running"
    assert status.detail == "processing experiment 42"


def test_set_component_status_upserts(database: Database, settings: Settings) -> None:
    state = _make_state_manager(database, settings)
    state.set_component_status("worker_1", "starting")
    state.set_component_status("worker_1", "running")

    status = state.get_component_status("worker_1")
    assert status.status == "running"
    all_statuses = state.get_all_component_status()
    assert len([s for s in all_statuses if s.component == "worker_1"]) == 1


def test_get_component_status_missing_returns_none(database: Database, settings: Settings) -> None:
    state = _make_state_manager(database, settings)
    assert state.get_component_status("does-not-exist") is None


def test_create_and_get_latest_checkpoint(database: Database, settings: Settings) -> None:
    state = _make_state_manager(database, settings)
    checkpoint = state.create_checkpoint(
        "research_loop", {"phase": 3, "last_strategy_id": "abc"}, label="pre-restart"
    )

    latest = state.get_latest_checkpoint("research_loop")
    assert latest is not None
    assert latest.id == checkpoint.id
    assert latest.state == {"phase": 3, "last_strategy_id": "abc"}

    checkpoint_file = settings.data.cache_dir / "checkpoints" / f"{checkpoint.id}.json"
    assert checkpoint_file.exists()


def test_latest_checkpoint_is_most_recent(database: Database, settings: Settings) -> None:
    state = _make_state_manager(database, settings)
    state.create_checkpoint("research_loop", {"step": 1})
    second = state.create_checkpoint("research_loop", {"step": 2})

    latest = state.get_latest_checkpoint("research_loop")
    assert latest.id == second.id
    assert latest.state == {"step": 2}


def test_write_and_read_project_state(database: Database, settings: Settings) -> None:
    state = _make_state_manager(database, settings)
    state.write_project_state({"phase": "phase_1_foundation", "status": "running"})

    read_back = state.read_project_state()
    assert read_back == {"phase": "phase_1_foundation", "status": "running"}


def test_read_project_state_missing_returns_none(database: Database, settings: Settings) -> None:
    state = _make_state_manager(database, settings)
    assert state.read_project_state() is None
