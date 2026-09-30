"""SQLite schema for Strategy Research Lab.

This is a *foundation* schema: it defines extensible tables for the
entities later phases will need (strategies, experiments, results, trades,
events, system status, AI actions, supervisor issues, hourly reports,
checkpoints) without implementing the business logic that will populate
them. Each table carries a `metadata` JSON TEXT column so later phases can
attach structured extra fields without a migration.

`schema_migrations` tracks which numbered migrations have been applied, so
future phases can add tables/columns without breaking existing databases.
"""

from __future__ import annotations

CURRENT_SCHEMA_VERSION = 2

_MIGRATION_1 = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS strategies (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'discovered',
    source_system   TEXT,
    description     TEXT,
    metadata        TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_strategies_status ON strategies(status);

CREATE TABLE IF NOT EXISTS experiments (
    id              TEXT PRIMARY KEY,
    strategy_id     TEXT REFERENCES strategies(id),
    system_name     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    parameters      TEXT,
    metadata        TEXT,
    started_at      TEXT,
    completed_at    TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_experiments_strategy ON experiments(strategy_id);
CREATE INDEX IF NOT EXISTS idx_experiments_status ON experiments(status);

CREATE TABLE IF NOT EXISTS experiment_results (
    id              TEXT PRIMARY KEY,
    experiment_id   TEXT NOT NULL REFERENCES experiments(id),
    metric_name     TEXT NOT NULL,
    metric_value    REAL,
    metric_text     TEXT,
    metadata        TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_experiment_results_experiment ON experiment_results(experiment_id);

CREATE TABLE IF NOT EXISTS trades (
    id              TEXT PRIMARY KEY,
    experiment_id   TEXT REFERENCES experiments(id),
    strategy_id     TEXT REFERENCES strategies(id),
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,
    entry_time      TEXT,
    exit_time       TEXT,
    entry_price     REAL,
    exit_price      REAL,
    quantity        REAL,
    pnl             REAL,
    fees            REAL,
    metadata        TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_trades_experiment ON trades(experiment_id);
CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy_id);

CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY,
    event_type      TEXT NOT NULL,
    category        TEXT NOT NULL,
    message         TEXT,
    payload         TEXT,
    related_id      TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_category ON events(category);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at);

CREATE TABLE IF NOT EXISTS system_status (
    component       TEXT PRIMARY KEY,
    status          TEXT NOT NULL,
    detail          TEXT,
    metadata        TEXT,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ai_actions (
    id              TEXT PRIMARY KEY,
    provider        TEXT NOT NULL,
    action_type     TEXT NOT NULL,
    related_id      TEXT,
    prompt_summary  TEXT,
    result_summary  TEXT,
    metadata        TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ai_actions_type ON ai_actions(action_type);

CREATE TABLE IF NOT EXISTS supervisor_issues (
    id              TEXT PRIMARY KEY,
    component       TEXT NOT NULL,
    issue_type      TEXT NOT NULL,
    severity        TEXT NOT NULL DEFAULT 'warning',
    description     TEXT,
    resolution      TEXT,
    status          TEXT NOT NULL DEFAULT 'open',
    metadata        TEXT,
    detected_at     TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_supervisor_issues_status ON supervisor_issues(status);

CREATE TABLE IF NOT EXISTS hourly_reports (
    id              TEXT PRIMARY KEY,
    period_start    TEXT NOT NULL,
    period_end      TEXT NOT NULL,
    summary         TEXT,
    metrics         TEXT,
    metadata        TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id              TEXT PRIMARY KEY,
    label           TEXT,
    component       TEXT NOT NULL,
    state_snapshot  TEXT NOT NULL,
    metadata        TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_checkpoints_component ON checkpoints(component);
"""

_MIGRATION_2 = """
ALTER TABLE experiments ADD COLUMN strategy_name TEXT;
ALTER TABLE experiments ADD COLUMN fingerprint TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_experiments_fingerprint ON experiments(fingerprint);

ALTER TABLE trades ADD COLUMN gross_pnl REAL;
ALTER TABLE trades ADD COLUMN slippage_cost REAL;
ALTER TABLE trades ADD COLUMN return_pct REAL;
ALTER TABLE trades ADD COLUMN exit_reason TEXT;
"""

# Ordered list of (version, sql) migrations. Add new entries here in future
# phases; never edit an already-released migration in place.
MIGRATIONS: list[tuple[int, str]] = [
    (1, _MIGRATION_1),
    (2, _MIGRATION_2),
]
