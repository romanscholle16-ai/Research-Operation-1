import uuid

from app.database.connection import Database
from app.database.schema import CURRENT_SCHEMA_VERSION


def test_initialize_schema_creates_tables(database: Database) -> None:
    tables = {
        row["name"]
        for row in database.query_all("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    expected = {
        "schema_migrations", "strategies", "experiments", "experiment_results",
        "trades", "events", "system_status", "ai_actions", "supervisor_issues",
        "hourly_reports", "checkpoints",
    }
    assert expected.issubset(tables)


def test_schema_migrations_recorded(database: Database) -> None:
    rows = database.query_all("SELECT version FROM schema_migrations")
    versions = {row["version"] for row in rows}
    assert CURRENT_SCHEMA_VERSION in versions


def test_initialize_schema_is_idempotent(database: Database) -> None:
    database.initialize_schema()
    database.initialize_schema()
    rows = database.query_all("SELECT version FROM schema_migrations")
    assert len(rows) == len(set(row["version"] for row in rows))


def test_insert_and_query_strategy(database: Database) -> None:
    strategy_id = str(uuid.uuid4())
    database.execute(
        "INSERT INTO strategies (id, name, status) VALUES (?, ?, ?)",
        (strategy_id, "test-strategy", "discovered"),
    )
    row = database.query_one("SELECT * FROM strategies WHERE id = ?", (strategy_id,))
    assert row is not None
    assert row["name"] == "test-strategy"
    assert row["status"] == "discovered"


def test_transaction_rolls_back_on_error(database: Database) -> None:
    strategy_id = str(uuid.uuid4())
    try:
        with database.transaction() as conn:
            conn.execute(
                "INSERT INTO strategies (id, name, status) VALUES (?, ?, ?)",
                (strategy_id, "rollback-me", "discovered"),
            )
            raise ValueError("boom")
    except ValueError:
        pass

    row = database.query_one("SELECT * FROM strategies WHERE id = ?", (strategy_id,))
    assert row is None


def test_transaction_commits_on_success(database: Database) -> None:
    strategy_id = str(uuid.uuid4())
    with database.transaction() as conn:
        conn.execute(
            "INSERT INTO strategies (id, name, status) VALUES (?, ?, ?)",
            (strategy_id, "commit-me", "discovered"),
        )

    row = database.query_one("SELECT * FROM strategies WHERE id = ?", (strategy_id,))
    assert row is not None
