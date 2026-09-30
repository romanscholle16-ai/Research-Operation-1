import json

from app.config.settings import Settings
from app.logging.setup import LogCategory, get_logger, setup_logging


def test_setup_logging_creates_category_file(settings: Settings) -> None:
    setup_logging(settings)
    log = get_logger(LogCategory.RESEARCH, "tests.test_logging")
    log.info("strategy scan complete", extra={"event_type": "strategy_scanned", "strategy_id": "abc123"})

    log_path = settings.logging.root_dir / "research" / "research.jsonl"
    assert log_path.exists()

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["level"] == "INFO"
    assert record["component"] == "tests.test_logging"
    assert record["event_type"] == "strategy_scanned"
    assert record["message"] == "strategy scan complete"
    assert record["identifiers"]["strategy_id"] == "abc123"


def test_error_records_are_mirrored_to_errors_category(settings: Settings) -> None:
    setup_logging(settings)
    log = get_logger(LogCategory.DATABASE, "tests.test_logging")
    log.error("connection failed", extra={"event_type": "database_error"})

    db_log = settings.logging.root_dir / "database" / "database.jsonl"
    errors_log = settings.logging.root_dir / "errors" / "errors.jsonl"
    assert db_log.exists()
    assert errors_log.exists()

    db_record = json.loads(db_log.read_text(encoding="utf-8").strip().splitlines()[0])
    err_record = json.loads(errors_log.read_text(encoding="utf-8").strip().splitlines()[0])
    assert db_record["event_type"] == "database_error"
    assert err_record["event_type"] == "database_error"


def test_categories_do_not_cross_contaminate(settings: Settings) -> None:
    setup_logging(settings)
    get_logger(LogCategory.SUPERVISOR, "tests.test_logging").info("supervisor check ok")
    get_logger(LogCategory.EXPERIMENT, "tests.test_logging").info("experiment queued")

    supervisor_log = settings.logging.root_dir / "supervisor" / "supervisor.jsonl"
    experiment_log = settings.logging.root_dir / "experiment" / "experiment.jsonl"

    assert "supervisor check ok" in supervisor_log.read_text(encoding="utf-8")
    assert "experiment queued" not in supervisor_log.read_text(encoding="utf-8")
    assert "experiment queued" in experiment_log.read_text(encoding="utf-8")
