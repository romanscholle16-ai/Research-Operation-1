"""Centralized configuration for Strategy Research Lab.

All configuration is derived from environment variables (optionally loaded
from a local `.env` file) with safe, project-relative defaults. No
machine-specific absolute paths are hardcoded anywhere in this module -
every path is computed relative to `PROJECT_ROOT`, which is the directory
containing this project (three levels up from this file).

Secrets (API keys, tokens) must only ever come from environment variables
or `.env` (both are git-ignored). See `.env.example` for the documented
list of supported variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Root of the project (C:\StrategyResearchLab in a normal checkout, but
# computed relative to this file so the project stays portable).
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    """Load a project-local `.env` file if present. Never overrides real env vars."""
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)


def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw not in (None, "") else default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw not in (None, "") else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class ApplicationConfig:
    name: str = "Strategy Research Lab"
    environment: str = "development"  # development | production
    debug: bool = True

    @classmethod
    def from_env(cls) -> "ApplicationConfig":
        return cls(
            name=_env_str("APP_NAME", cls.name),
            environment=_env_str("APP_ENVIRONMENT", cls.environment),
            debug=_env_bool("APP_DEBUG", cls.debug),
        )


@dataclass(frozen=True)
class DatabaseConfig:
    path: Path = PROJECT_ROOT / "data" / "cache" / "state" / "strategy_research_lab.db"
    busy_timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        raw_path = os.environ.get("DATABASE_PATH")
        path = Path(raw_path) if raw_path else cls.path
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return cls(
            path=path,
            busy_timeout_seconds=_env_float("DATABASE_BUSY_TIMEOUT_SECONDS", cls.busy_timeout_seconds),
        )


@dataclass(frozen=True)
class LoggingConfig:
    root_dir: Path = PROJECT_ROOT / "logs"
    level: str = "INFO"
    max_bytes: int = 5_000_000
    backup_count: int = 5
    console_output: bool = True

    @classmethod
    def from_env(cls) -> "LoggingConfig":
        raw_dir = os.environ.get("LOGGING_ROOT_DIR")
        root_dir = Path(raw_dir) if raw_dir else cls.root_dir
        if not root_dir.is_absolute():
            root_dir = PROJECT_ROOT / root_dir
        return cls(
            root_dir=root_dir,
            level=_env_str("LOGGING_LEVEL", cls.level),
            max_bytes=_env_int("LOGGING_MAX_BYTES", cls.max_bytes),
            backup_count=_env_int("LOGGING_BACKUP_COUNT", cls.backup_count),
            console_output=_env_bool("LOGGING_CONSOLE_OUTPUT", cls.console_output),
        )


@dataclass(frozen=True)
class DataConfig:
    raw_dir: Path = PROJECT_ROOT / "data" / "raw"
    processed_dir: Path = PROJECT_ROOT / "data" / "processed"
    cache_dir: Path = PROJECT_ROOT / "data" / "cache"

    @classmethod
    def from_env(cls) -> "DataConfig":
        return cls()


@dataclass(frozen=True)
class ResearchConfig:
    strategies_discovered_dir: Path = PROJECT_ROOT / "strategies" / "discovered"
    strategies_active_dir: Path = PROJECT_ROOT / "strategies" / "active"
    strategies_qualified_dir: Path = PROJECT_ROOT / "strategies" / "qualified"
    strategies_rejected_dir: Path = PROJECT_ROOT / "strategies" / "rejected"

    @classmethod
    def from_env(cls) -> "ResearchConfig":
        return cls()


@dataclass(frozen=True)
class BacktestingConfig:
    results_experiments_dir: Path = PROJECT_ROOT / "results" / "experiments"
    results_reports_dir: Path = PROJECT_ROOT / "results" / "reports"
    default_starting_capital: float = 10_000.0

    @classmethod
    def from_env(cls) -> "BacktestingConfig":
        return cls(
            default_starting_capital=_env_float(
                "BACKTESTING_DEFAULT_STARTING_CAPITAL", cls.default_starting_capital
            ),
        )


@dataclass(frozen=True)
class ExperimentConfig:
    max_concurrent_experiments: int = 1
    max_experiments_per_hour: int = 20

    @classmethod
    def from_env(cls) -> "ExperimentConfig":
        return cls(
            max_concurrent_experiments=_env_int(
                "EXPERIMENT_MAX_CONCURRENT", cls.max_concurrent_experiments
            ),
            max_experiments_per_hour=_env_int(
                "EXPERIMENT_MAX_PER_HOUR", cls.max_experiments_per_hour
            ),
        )


@dataclass(frozen=True)
class AIProviderConfig:
    """AI-provider settings. Provider-agnostic: the active provider is a
    string key, and provider-specific API keys are read from environment
    variables only - never hardcoded, never committed."""

    active_provider: str = "none"  # none | mock | anthropic (alias: claude) | freebuff | ollama
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    freebuff_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    # Comma-separated provider names tried in order if active_provider fails
    # (Phase 5 brief section 10). Empty = no fallback.
    fallback_chain: str = ""
    # A fallback entry of "mock" is only ever used if this is explicitly
    # true - never silently, so a "real" research session can't end up
    # quietly running on fake data (Phase 5 brief section 10).
    allow_mock_fallback: bool = False

    @classmethod
    def from_env(cls) -> "AIProviderConfig":
        return cls(
            active_provider=_env_str("AI_ACTIVE_PROVIDER", cls.active_provider),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
            anthropic_model=_env_str("ANTHROPIC_MODEL", cls.anthropic_model),
            freebuff_api_key=os.environ.get("FREEBUFF_API_KEY") or None,
            ollama_base_url=_env_str("OLLAMA_BASE_URL", cls.ollama_base_url),
            fallback_chain=_env_str("AI_PROVIDER_FALLBACK_CHAIN", cls.fallback_chain),
            allow_mock_fallback=_env_bool("AI_ALLOW_MOCK_FALLBACK", cls.allow_mock_fallback),
        )


@dataclass(frozen=True)
class SupervisorConfig:
    enabled: bool = False
    check_interval_seconds: int = 60
    max_auto_restart_attempts: int = 3

    @classmethod
    def from_env(cls) -> "SupervisorConfig":
        return cls(
            enabled=_env_bool("SUPERVISOR_ENABLED", cls.enabled),
            check_interval_seconds=_env_int(
                "SUPERVISOR_CHECK_INTERVAL_SECONDS", cls.check_interval_seconds
            ),
            max_auto_restart_attempts=_env_int(
                "SUPERVISOR_MAX_AUTO_RESTART_ATTEMPTS", cls.max_auto_restart_attempts
            ),
        )


@dataclass(frozen=True)
class DashboardConfig:
    host: str = "127.0.0.1"
    port: int = 8765

    @classmethod
    def from_env(cls) -> "DashboardConfig":
        return cls(
            host=_env_str("DASHBOARD_HOST", cls.host),
            port=_env_int("DASHBOARD_PORT", cls.port),
        )


@dataclass(frozen=True)
class RiskConfig:
    max_risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 5.0
    live_trading_enabled: bool = False

    @classmethod
    def from_env(cls) -> "RiskConfig":
        return cls(
            max_risk_per_trade_pct=_env_float("RISK_MAX_PER_TRADE_PCT", cls.max_risk_per_trade_pct),
            max_daily_loss_pct=_env_float("RISK_MAX_DAILY_LOSS_PCT", cls.max_daily_loss_pct),
            live_trading_enabled=_env_bool("RISK_LIVE_TRADING_ENABLED", cls.live_trading_enabled),
        )


@dataclass(frozen=True)
class Settings:
    """Top-level, immutable settings bundle for the whole application."""

    project_root: Path = PROJECT_ROOT
    application: ApplicationConfig = field(default_factory=ApplicationConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    data: DataConfig = field(default_factory=DataConfig)
    research: ResearchConfig = field(default_factory=ResearchConfig)
    backtesting: BacktestingConfig = field(default_factory=BacktestingConfig)
    experiment: ExperimentConfig = field(default_factory=ExperimentConfig)
    ai_provider: AIProviderConfig = field(default_factory=AIProviderConfig)
    supervisor: SupervisorConfig = field(default_factory=SupervisorConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv()
        return cls(
            project_root=PROJECT_ROOT,
            application=ApplicationConfig.from_env(),
            database=DatabaseConfig.from_env(),
            logging=LoggingConfig.from_env(),
            data=DataConfig.from_env(),
            research=ResearchConfig.from_env(),
            backtesting=BacktestingConfig.from_env(),
            experiment=ExperimentConfig.from_env(),
            ai_provider=AIProviderConfig.from_env(),
            supervisor=SupervisorConfig.from_env(),
            dashboard=DashboardConfig.from_env(),
            risk=RiskConfig.from_env(),
        )

    def ensure_directories(self) -> None:
        """Create all project-local directories this config references, if missing."""
        dirs = [
            self.data.raw_dir,
            self.data.processed_dir,
            self.data.cache_dir,
            self.database.path.parent,
            self.logging.root_dir,
            self.research.strategies_discovered_dir,
            self.research.strategies_active_dir,
            self.research.strategies_qualified_dir,
            self.research.strategies_rejected_dir,
            self.backtesting.results_experiments_dir,
            self.backtesting.results_reports_dir,
        ]
        for directory in dirs:
            directory.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the process-wide cached Settings instance, loading it on first use."""
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def reload_settings() -> Settings:
    """Force a fresh reload of Settings from the environment. Mainly for tests."""
    global _settings
    _settings = Settings.from_env()
    return _settings
