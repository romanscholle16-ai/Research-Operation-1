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

CURRENT_SCHEMA_VERSION = 5

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

_MIGRATION_3 = """
CREATE TABLE IF NOT EXISTS research_campaigns (
    id                  TEXT PRIMARY KEY,
    strategy_name       TEXT,
    research_system     TEXT NOT NULL,
    purpose             TEXT,
    configuration       TEXT,
    status              TEXT NOT NULL DEFAULT 'created',
    experiment_count    INTEGER NOT NULL DEFAULT 0,
    completed_count     INTEGER NOT NULL DEFAULT 0,
    failed_count        INTEGER NOT NULL DEFAULT 0,
    metadata            TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    started_at          TEXT,
    completed_at        TEXT
);
CREATE INDEX IF NOT EXISTS idx_research_campaigns_status ON research_campaigns(status);

CREATE TABLE IF NOT EXISTS research_experiments (
    id                          TEXT PRIMARY KEY,
    campaign_id                 TEXT REFERENCES research_campaigns(id),
    research_system             TEXT NOT NULL,
    strategy_name                TEXT NOT NULL,
    strategy_version             TEXT NOT NULL,
    parameters                   TEXT,
    rule_configuration           TEXT,
    execution_configuration      TEXT,
    data_identity                 TEXT,
    timeframe                     TEXT,
    data_start                    TEXT,
    data_end                      TEXT,
    parent_experiment_id          TEXT REFERENCES research_experiments(id),
    status                        TEXT NOT NULL DEFAULT 'created',
    fingerprint                   TEXT NOT NULL,
    backtest_run_id               TEXT REFERENCES experiments(id),
    result_fingerprint            TEXT,
    duplicate_of_experiment_id    TEXT REFERENCES research_experiments(id),
    failure_info                  TEXT,
    metadata                      TEXT,
    created_at                    TEXT NOT NULL DEFAULT (datetime('now')),
    started_at                    TEXT,
    completed_at                  TEXT
);
CREATE INDEX IF NOT EXISTS idx_research_experiments_campaign ON research_experiments(campaign_id);
CREATE INDEX IF NOT EXISTS idx_research_experiments_status ON research_experiments(status);
CREATE INDEX IF NOT EXISTS idx_research_experiments_fingerprint ON research_experiments(fingerprint);
CREATE INDEX IF NOT EXISTS idx_research_experiments_parent ON research_experiments(parent_experiment_id);
"""

_MIGRATION_4 = """
CREATE TABLE IF NOT EXISTS ai_research_sessions (
    id                              TEXT PRIMARY KEY,
    objective                       TEXT NOT NULL,
    status                          TEXT NOT NULL DEFAULT 'created',
    iteration                       INTEGER NOT NULL DEFAULT 0,
    max_iterations                  INTEGER NOT NULL,
    max_experiments                 INTEGER NOT NULL,
    max_failed_experiments          INTEGER NOT NULL,
    max_consecutive_no_progress     INTEGER NOT NULL,
    experiments_run                 INTEGER NOT NULL DEFAULT 0,
    experiments_failed              INTEGER NOT NULL DEFAULT 0,
    consecutive_no_progress         INTEGER NOT NULL DEFAULT 0,
    stopping_reason                 TEXT,
    provider_name                   TEXT,
    model_name                      TEXT,
    metadata                        TEXT,
    created_at                      TEXT NOT NULL DEFAULT (datetime('now')),
    started_at                      TEXT,
    completed_at                    TEXT
);
CREATE INDEX IF NOT EXISTS idx_ai_research_sessions_status ON ai_research_sessions(status);

CREATE TABLE IF NOT EXISTS ai_research_decisions (
    id                      TEXT PRIMARY KEY,
    session_id              TEXT NOT NULL REFERENCES ai_research_sessions(id),
    iteration                INTEGER NOT NULL,
    hypothesis                TEXT,
    reasoning_summary          TEXT,
    requested_experiments       TEXT,
    analysis_tasks                TEXT,
    stopping_reason                TEXT,
    confidence                       REAL,
    created_at                        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ai_research_decisions_session ON ai_research_decisions(session_id);

CREATE TABLE IF NOT EXISTS ai_research_session_campaigns (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES ai_research_sessions(id),
    campaign_id     TEXT NOT NULL REFERENCES research_campaigns(id),
    iteration       INTEGER NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ai_research_session_campaigns_session ON ai_research_session_campaigns(session_id);
"""

_MIGRATION_5 = """
CREATE TABLE IF NOT EXISTS web_research_sessions (
    id                          TEXT PRIMARY KEY,
    objective                   TEXT NOT NULL,
    status                      TEXT NOT NULL DEFAULT 'created',
    iteration                   INTEGER NOT NULL DEFAULT 0,
    max_iterations              INTEGER NOT NULL,
    max_sources_per_session     INTEGER NOT NULL,
    max_requests_per_session    INTEGER NOT NULL,
    sources_discovered          INTEGER NOT NULL DEFAULT 0,
    sources_retrieved           INTEGER NOT NULL DEFAULT 0,
    evidence_count              INTEGER NOT NULL DEFAULT 0,
    specification_count         INTEGER NOT NULL DEFAULT 0,
    requests_made               INTEGER NOT NULL DEFAULT 0,
    stopping_reason             TEXT,
    final_specification_status  TEXT,
    provider_name                TEXT,
    model_name                    TEXT,
    metadata                        TEXT,
    created_at                        TEXT NOT NULL DEFAULT (datetime('now')),
    started_at                        TEXT,
    completed_at                      TEXT
);
CREATE INDEX IF NOT EXISTS idx_web_research_sessions_status ON web_research_sessions(status);

CREATE TABLE IF NOT EXISTS web_sources (
    id                  TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL REFERENCES web_research_sessions(id),
    url                 TEXT NOT NULL,
    normalized_url      TEXT NOT NULL,
    source_type         TEXT NOT NULL DEFAULT 'unknown',
    status              TEXT NOT NULL,
    title               TEXT,
    domain              TEXT,
    publisher           TEXT,
    author              TEXT,
    published_at        TEXT,
    last_modified_at    TEXT,
    retrieved_at        TEXT,
    content_hash        TEXT,
    content_type        TEXT,
    byte_size           INTEGER,
    http_status         INTEGER,
    trust_metadata      TEXT,
    discovery_query     TEXT,
    failure_reason      TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_web_sources_session ON web_sources(session_id);
CREATE INDEX IF NOT EXISTS idx_web_sources_normalized_url ON web_sources(normalized_url);

CREATE TABLE IF NOT EXISTS web_evidence (
    id                      TEXT PRIMARY KEY,
    session_id              TEXT NOT NULL REFERENCES web_research_sessions(id),
    source_id               TEXT NOT NULL REFERENCES web_sources(id),
    claim                   TEXT NOT NULL,
    status                  TEXT NOT NULL,
    location_reference      TEXT,
    quoted_text             TEXT,
    extraction_timestamp    TEXT NOT NULL,
    created_at              TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_web_evidence_session ON web_evidence(session_id);
CREATE INDEX IF NOT EXISTS idx_web_evidence_source ON web_evidence(source_id);

CREATE TABLE IF NOT EXISTS web_strategy_specifications (
    id                  TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL REFERENCES web_research_sessions(id),
    name                TEXT NOT NULL,
    status              TEXT NOT NULL,
    specification       TEXT NOT NULL,
    validation_errors   TEXT,
    unknowns            TEXT,
    ambiguities         TEXT,
    source_evidence_ids TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_web_strategy_specifications_session ON web_strategy_specifications(session_id);

CREATE TABLE IF NOT EXISTS web_research_decisions (
    id                  TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL REFERENCES web_research_sessions(id),
    iteration           INTEGER NOT NULL,
    action              TEXT NOT NULL,
    reasoning_summary   TEXT,
    details             TEXT,
    stopping_reason     TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_web_research_decisions_session ON web_research_decisions(session_id);
"""

# Ordered list of (version, sql) migrations. Add new entries here in future
# phases; never edit an already-released migration in place.
MIGRATIONS: list[tuple[int, str]] = [
    (1, _MIGRATION_1),
    (2, _MIGRATION_2),
    (3, _MIGRATION_3),
    (4, _MIGRATION_4),
    (5, _MIGRATION_5),
]
