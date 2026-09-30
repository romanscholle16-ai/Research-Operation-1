"""SQLite connection management and schema initialization."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from app.database.schema import MIGRATIONS


class Database:
    """Thin wrapper around a single SQLite connection.

    Uses WAL journal mode (safer for a process that may be interrupted) and
    foreign key enforcement. Not thread-safe by itself; a later phase that
    needs concurrent access should either serialize writes through one
    owner (e.g. the Supervisor) or open one `Database` per thread.
    """

    def __init__(self, db_path: Path, busy_timeout_seconds: float = 30.0) -> None:
        self.db_path = db_path
        self.busy_timeout_seconds = busy_timeout_seconds
        self._conn: sqlite3.Connection | None = None

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._conn

    def connect(self) -> None:
        if self._conn is not None:
            return
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=self.busy_timeout_seconds,
            isolation_level=None,  # autocommit; explicit transactions via context manager
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(f"PRAGMA busy_timeout = {int(self.busy_timeout_seconds * 1000)}")
        self._conn = conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def initialize_schema(self) -> None:
        """Apply any migrations not yet recorded in `schema_migrations`."""
        conn = self.connection
        conn.executescript(MIGRATIONS[0][1])  # migration 1 creates schema_migrations itself
        applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
        for version, sql in MIGRATIONS:
            if version in applied:
                continue
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
            )
            applied.add(version)

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self.connection
        conn.execute("BEGIN")
        try:
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        return self.connection.execute(sql, params)

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        return self.connection.execute(sql, params).fetchone()

    def query_all(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        return self.connection.execute(sql, params).fetchall()

    def __enter__(self) -> "Database":
        self.connect()
        self.initialize_schema()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


_database: Database | None = None


def get_database() -> Database:
    """Return the process-wide cached, connected Database instance."""
    global _database
    if _database is None:
        from app.config.settings import get_settings

        settings = get_settings()
        _database = Database(settings.database.path, settings.database.busy_timeout_seconds)
        _database.connect()
        _database.initialize_schema()
    return _database


def reset_database_singleton() -> None:
    """Close and clear the cached Database instance. Mainly for tests."""
    global _database
    if _database is not None:
        _database.close()
        _database = None
