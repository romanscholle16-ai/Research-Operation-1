# Architecture

Status: reflects Phase 1 (Foundation) only. Updated as later phases land.

## Goals driving the design

- **AI-provider independent.** Nothing in `app/` imports Claude, Anthropic,
  or any specific AI SDK. `app/config/settings.py` models AI providers as
  a string key (`AI_ACTIVE_PROVIDER`) plus per-provider credentials read
  from environment variables. `app/agents/` is a placeholder package for
  the future AI research layer.
- **Recoverable.** All state that matters survives a process restart:
  SQLite database (`system_status`, `checkpoints`, `events`, ...) plus a
  redundant JSON checkpoint file per checkpoint and a small
  `current_state.json` snapshot, so recovery does not depend on the
  database file being readable.
- **Self-contained.** Virtual environment, database, logs, cache, and
  config all live under the project folder. No global installs, no
  machine-specific absolute paths - every path in `Settings` is computed
  relative to `PROJECT_ROOT` (`app/config/settings.py`), which is derived
  from the location of the source file itself, not hardcoded.
- **Observable.** Every component logs through the same structured,
  category-based JSONL logging system, and every notable occurrence is
  additionally recorded as a durable row in the `events` table - the same
  data model the future dashboard's Event Timeline will read from
  directly.
- **Deterministic core, AI at the edges.** Not yet applicable in Phase 1
  (no backtesting or AI code exists yet), but it constrains schema and
  package boundaries: `app/backtesting/` will own all P&L/metric
  calculation; `app/agents/` will only ever read results and propose next
  steps, never compute financial numbers itself.

## Components (Phase 1)

```
app/config      Settings dataclasses, one per concern (application,
                database, logging, data, research, backtesting,
                experiment, ai_provider, supervisor, dashboard, risk).
                Loaded once from environment variables (+ optional local
                .env) via Settings.from_env(), cached by get_settings().

app/logging     Structured JSONL logging. One category = one logger =
                one file (logs/<category>/<category>.jsonl). ERROR+
                records from any category are mirrored into
                logs/errors/errors.jsonl. get_logger(category, component)
                is the only entry point application code should use.

app/database    SQLite connection management (app/database/connection.py)
                and schema (app/database/schema.py). Schema is versioned
                via a schema_migrations table so future phases can add
                tables/columns without a destructive reset.

app/core        Cross-cutting infrastructure that doesn't belong to one
                subsystem:
                  - events.py: EventRecorder, the single writer to the
                    `events` table, and EventType, the enum of event
                    kinds the dashboard's Event Timeline will render.
                  - app.py: Application, which owns the startup/shutdown
                    lifecycle of config -> logging -> database -> state
                    -> events.

app/state       StateManager: component status (system_status table),
                checkpoints (checkpoints table + redundant JSON file
                under data/cache/checkpoints/), and a lightweight
                current_state.json snapshot under data/cache/state/ for
                fast, DB-independent inspection.
```

### Placeholder packages (not implemented in Phase 1)

`app/api`, `app/dashboard`, `app/supervisor`, `app/research`,
`app/backtesting`, `app/systems`, `app/agents` exist as empty packages
(single docstring `__init__.py`) so the import structure and directory
layout are stable for later phases to build into, without any Phase 1
code depending on them.

## Data flow (Phase 1)

```
main.py -> Application.startup()
             1. Settings.from_env() (+ ensure_directories())
             2. setup_logging(settings)
             3. Database.connect() + initialize_schema()
             4. StateManager(db, ...)
             5. EventRecorder(db)
             6. state.set_component_status("application", "running")
             7. events.record(APPLICATION_STARTED)
             8. state.write_project_state({...})
           -> [Phase 1: nothing runs here yet]
           -> Application.shutdown()
             1. events.record(APPLICATION_STOPPED)
             2. state.set_component_status("application", "stopped")
             3. state.write_project_state({...})
             4. db.close()
```

Every `events.record(...)` call both inserts a row into the `events`
table and emits a structured log line via `app.logging` - the dashboard
(a later phase) can read either the DB or the log files and see the same
facts.

## Database schema (foundation)

Defined in `app/database/schema.py`, versioned via `schema_migrations`.
Extensible via a `metadata` JSON TEXT column on every table, so later
phases can attach structured fields without a migration for every new
attribute:

`strategies`, `experiments`, `experiment_results`, `trades`, `events`,
`system_status`, `ai_actions`, `supervisor_issues`, `hourly_reports`,
`checkpoints`.

None of these tables have business logic behind them yet - Phase 1 only
creates the schema and proves it works (see `tests/test_database.py`).

## Documented deviations from the Phase 1 brief's example tree

- **`logs/` subfolders.** The brief's example tree lists
  `logs/{application,experiments,supervisor,agent,hourly,errors}`, but
  section 3 of the same brief requires the logging system to support
  categories `application, research, backtesting, experiment, supervisor,
  AI, database, errors` (8 categories, singular `experiment`, no `agent`/
  `hourly`). These two lists conflict. The functional requirement (the
  explicit category list) was treated as authoritative: `logs/` has one
  subfolder per `LogCategory` enum value (`app/logging/setup.py`) -
  `application, research, backtesting, experiment, supervisor, ai,
  database, errors`. `agent` and `hourly` were dropped as log categories;
  "hourly" reporting is instead a row shape in the `hourly_reports` table,
  and per-agent logging (if ever needed) can go through the `ai` category
  with `related_id`/identifiers rather than its own top-level folder.
- **`app/` future-phase subpackages** (`api`, `dashboard`, `supervisor`,
  `research`, `backtesting`, `systems`, `agents`) are present as directed,
  but intentionally contain nothing beyond a docstring - no speculative
  interfaces or base classes, since Phase 1 has no evidence yet of what
  those phases will actually need.

## Future expansion points

- **Five research systems** (`app/research/` + `app/systems/`): Parameter
  Explorer, Rule/Logic Explorer, Risk/Execution Optimizer, Market-Condition
  Tester, Adversarial/Research System. Each should write `experiments` /
  `experiment_results` / `trades` rows and `events` through the existing
  `EventRecorder` - no schema change anticipated for the basic case.
- **AI research layer** (`app/agents/`): reads `experiment_results`,
  proposes new experiments, records via `ai_actions` +
  `EventType.AI_INVOKED` / `AI_PATCH_CREATED`. Must never write to
  `trades` or compute P&L - that stays in `app/backtesting/`.
- **Supervisor Agent** (`app/supervisor/`): polls `system_status`, writes
  `supervisor_issues`, drives deterministic recovery first, AI-assisted
  diagnosis only after that fails, records via
  `SUPERVISOR_DETECTED_ISSUE` / `_ATTEMPTED_RECOVERY` / `_FIXED_ISSUE`.
  Restart/patch actions should go through `StateManager.create_checkpoint`
  before anything destructive.
- **Dashboard** (`app/dashboard/` + `app/api/`): reads `events`,
  `system_status`, and the `logs/*.jsonl` files. Nothing in Phase 1
  assumes a particular API framework; `DashboardConfig` only carries
  host/port so that choice stays deferred.
