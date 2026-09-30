from pathlib import Path

from app.config.settings import Settings, reload_settings


def test_settings_from_env_has_project_relative_defaults() -> None:
    s = Settings.from_env()
    assert s.database.path.is_absolute()
    assert s.logging.root_dir.is_absolute()
    # defaults must live under the real project root, not some other machine path
    assert s.project_root in s.database.path.parents

def test_settings_env_override(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "production")
    monkeypatch.setenv("DASHBOARD_PORT", "9999")
    s = reload_settings()
    assert s.application.environment == "production"
    assert s.dashboard.port == 9999


def test_ensure_directories_creates_expected_dirs(settings: Settings) -> None:
    assert settings.data.raw_dir.exists()
    assert settings.data.processed_dir.exists()
    assert settings.database.path.parent.exists()
    assert settings.logging.root_dir.exists()
    assert settings.research.strategies_discovered_dir.exists()
    assert settings.backtesting.results_reports_dir.exists()


def test_isolated_settings_do_not_touch_real_project_paths(settings: Settings, tmp_path: Path) -> None:
    assert settings.project_root == tmp_path
    assert str(tmp_path) in str(settings.database.path)
