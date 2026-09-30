"""Structured logging setup.

Every log record is written as one JSON object per line (JSONL) so the
future dashboard can tail and parse the same files the application writes,
without a separate export step. Records include: timestamp, level,
component, event_type, message, and any extra identifiers passed by the
caller.

Categories map 1:1 to subdirectories under `logs/`:
application, research, backtesting, experiment, supervisor, ai, database,
errors. `errors` additionally receives a copy of every ERROR/CRITICAL
record from any category, so operators have one place to look first.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

_RESERVED_LOG_RECORD_FIELDS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName", "message",
}


class LogCategory(str, Enum):
    APPLICATION = "application"
    RESEARCH = "research"
    BACKTESTING = "backtesting"
    EXPERIMENT = "experiment"
    SUPERVISOR = "supervisor"
    AI = "ai"
    DATABASE = "database"
    ERRORS = "errors"


class _JsonLinesFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "component": getattr(record, "component", record.name),
            "event_type": getattr(record, "event_type", None),
            "message": record.getMessage(),
        }
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_LOG_RECORD_FIELDS
            and key not in ("component", "event_type")
            and not key.startswith("_")
        }
        if extras:
            payload["identifiers"] = extras
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _make_file_handler(path: Path, level: int, max_bytes: int, backup_count: int) -> logging.Handler:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        filename=str(path), maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    handler.setLevel(level)
    handler.setFormatter(_JsonLinesFormatter())
    return handler


_configured = False


def setup_logging(settings: Any | None = None) -> None:
    """Configure the logging system. Idempotent - safe to call more than once.

    `settings` is an `app.config.settings.Settings` instance. Imported lazily
    (via duck typing on the passed object) to avoid a circular import between
    config and logging at module load time.
    """
    global _configured

    if settings is None:
        from app.config.settings import get_settings

        settings = get_settings()

    log_cfg = settings.logging
    level = getattr(logging, log_cfg.level.upper(), logging.INFO)

    root_logger = logging.getLogger("app")
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.propagate = False

    for category in LogCategory:
        if category == LogCategory.ERRORS:
            continue
        category_logger = logging.getLogger(f"app.{category.value}")
        category_logger.setLevel(level)
        category_logger.propagate = True

    # One handler per category directory, attached via a filter on logger name.
    for category in LogCategory:
        if category == LogCategory.ERRORS:
            continue
        log_path = log_cfg.root_dir / category.value / f"{category.value}.jsonl"
        handler = _make_file_handler(log_path, level, log_cfg.max_bytes, log_cfg.backup_count)
        handler.addFilter(_CategoryFilter(f"app.{category.value}"))
        root_logger.addHandler(handler)

    # Errors category: mirrors ERROR+ records from any app.* logger.
    errors_path = log_cfg.root_dir / LogCategory.ERRORS.value / f"{LogCategory.ERRORS.value}.jsonl"
    errors_handler = _make_file_handler(errors_path, logging.ERROR, log_cfg.max_bytes, log_cfg.backup_count)
    root_logger.addHandler(errors_handler)

    if log_cfg.console_output:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        root_logger.addHandler(console_handler)

    _configured = True


class _CategoryFilter(logging.Filter):
    def __init__(self, logger_name: str) -> None:
        super().__init__()
        self._logger_name = logger_name

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name == self._logger_name


class _ComponentLoggerAdapter(logging.LoggerAdapter):
    """LoggerAdapter that merges its own `extra` with any per-call `extra`.

    The stdlib LoggerAdapter overwrites kwargs["extra"] with self.extra,
    which would silently drop per-call fields like `event_type`. This
    merges instead, with per-call fields taking precedence.
    """

    def process(self, msg: Any, kwargs: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        call_extra = kwargs.get("extra") or {}
        kwargs["extra"] = {**self.extra, **call_extra}
        return msg, kwargs


def get_logger(category: LogCategory, component: str) -> logging.LoggerAdapter:
    """Return a logger adapter scoped to `category`, tagging records with `component`.

    Usage:
        log = get_logger(LogCategory.APPLICATION, "app.core.app")
        log.info("application started", extra={"event_type": "application_started"})
    """
    if not _configured:
        setup_logging()
    base_logger = logging.getLogger(f"app.{category.value}")
    return _ComponentLoggerAdapter(base_logger, {"component": component})
