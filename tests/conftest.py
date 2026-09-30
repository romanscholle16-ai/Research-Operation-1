"""Shared pytest fixtures.

Every fixture here builds a fully project-isolated `Settings` instance
pointed at a pytest `tmp_path`, so tests never touch the real
`C:\\StrategyResearchLab\\data`, `logs`, etc., and never depend on
execution order or global singleton state.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config.settings import (
    ApplicationConfig,
    BacktestingConfig,
    DatabaseConfig,
    DataConfig,
    LoggingConfig,
    ResearchConfig,
    Settings,
)
from app.database.connection import Database
from app.logging.setup import setup_logging


def make_isolated_settings(tmp_path: Path) -> Settings:
    settings = Settings(
        project_root=tmp_path,
        application=ApplicationConfig(environment="test", debug=True),
        database=DatabaseConfig(path=tmp_path / "data" / "cache" / "state" / "test.db"),
        logging=LoggingConfig(root_dir=tmp_path / "logs", console_output=False),
        data=DataConfig(
            raw_dir=tmp_path / "data" / "raw",
            processed_dir=tmp_path / "data" / "processed",
            cache_dir=tmp_path / "data" / "cache",
        ),
        research=ResearchConfig(
            strategies_discovered_dir=tmp_path / "strategies" / "discovered",
            strategies_active_dir=tmp_path / "strategies" / "active",
            strategies_qualified_dir=tmp_path / "strategies" / "qualified",
            strategies_rejected_dir=tmp_path / "strategies" / "rejected",
        ),
        backtesting=BacktestingConfig(
            results_experiments_dir=tmp_path / "results" / "experiments",
            results_reports_dir=tmp_path / "results" / "reports",
        ),
    )
    settings.ensure_directories()
    return settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_isolated_settings(tmp_path)


@pytest.fixture(autouse=True)
def _isolated_logging(settings: Settings) -> None:
    """Point the global logging system at this test's tmp_path.

    Without this, the first `get_logger()` call in any test would lazily
    configure logging against the *real* project's `logs/` directory
    (whatever `get_settings()` resolves to), leaking test log files into
    the real project. Autouse so every test gets isolated logging even if
    it never touches `settings` directly.
    """
    setup_logging(settings)


@pytest.fixture
def database(settings: Settings):
    db = Database(settings.database.path, settings.database.busy_timeout_seconds)
    db.connect()
    db.initialize_schema()
    yield db
    db.close()
