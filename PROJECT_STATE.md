# Project State

**Active phase:** Phase 1 - Foundation, Architecture & Project State
**Status:** Complete
**Last updated:** 2026-09-29

This file is written for another AI (or human) with no access to prior
conversation history. It describes what actually exists and has been
tested - not intended future functionality. See ARCHITECTURE.md for how
the pieces fit together and PHASE_HISTORY.md for what happened in past
phases.

## What currently exists

- A Python 3.12 project at `C:\StrategyResearchLab`, self-contained: `.venv`
  virtual environment, `pyproject.toml`, all dependencies installed
  project-locally (`python-dotenv` runtime, `pytest` dev).
- Centralized configuration (`app/config/settings.py`): one dataclass per
  concern, loaded from environment variables / `.env`, no hardcoded
  machine-specific paths, no secrets in source. See `.env.example` for the
  full list of supported variables.
- Structured JSONL logging (`app/logging/setup.py`): 8 categories
  (application, research, backtesting, experiment, supervisor, ai,
  database, errors), one file per category under `logs/`, errors mirrored
  into `logs/errors/errors.jsonl`.
- SQLite database foundation (`app/database/`): versioned schema
  (`schema_migrations`), 10 tables (`strategies`, `experiments`,
  `experiment_results`, `trades`, `events`, `system_status`,
  `ai_actions`, `supervisor_issues`, `hourly_reports`, `checkpoints`),
  each extensible via a `metadata` JSON column. No business logic
  populates these tables yet - Phase 1 only proves the schema works.
- Persistent event system (`app/core/events.py`): `EventRecorder` writes
  to the `events` table and mirrors to the log; `EventType` enum covers
  every event named in the Phase 1 brief (application/strategy/experiment/
  worker/supervisor/AI/checkpoint/hourly-report lifecycle events).
- State & checkpoint foundation (`app/state/state_manager.py`):
  component status in `system_status`, checkpoints in both the
  `checkpoints` table and a redundant JSON file under
  `data/cache/checkpoints/`, plus a `current_state.json` snapshot under
  `data/cache/state/` for fast, DB-independent inspection.
- Minimal application entry point (`app/core/app.py`, `main.py`):
  `Application.startup()` wires config -> logging -> database -> state ->
  events, emits `application_started`, and `Application.shutdown()`
  emits `application_stopped` and closes cleanly. No autonomous loop.
- 30 automated tests (`tests/`), all passing, covering config, logging,
  database, events, state/checkpoints, and the application lifecycle.
  Every test runs against an isolated `tmp_path`-based `Settings`
  instance - none touch the real project's `data/`, `logs/`, or database.
- Git repository initialized with a `.gitignore` that excludes the
  virtual environment, the database, logs, generated data/results/
  strategy artifacts, and `.env`.

## What has been completed

All 15 Phase 1 requirements from the brief: Python environment, central
configuration, structured logging, event system foundation, SQLite
foundation, state & checkpoint foundation, the four hand-off docs (this
file, ARCHITECTURE.md, PHASE_HISTORY.md, CURRENT_TASK.md), git setup, the
minimal entry point, and the automated test suite (written and run, all
passing).

## What remains (explicitly out of Phase 1 scope)

- Actual trading strategies, the five research systems, the AI research
  layer, the Supervisor Agent, the dashboard, live trading / exchange
  execution, and large historical data downloads. See CURRENT_TASK.md and
  ARCHITECTURE.md's "Future expansion points" for how these are expected
  to attach to the Phase 1 foundation.

## Important technical state

- Real (non-test) database, once `main.py` is run, lives at
  `data/cache/state/strategy_research_lab.db` (git-ignored; recreated
  automatically by `Database.initialize_schema()` if missing).
- `Settings.project_root` and every path derived from it are computed
  relative to the location of `app/config/settings.py`, not hardcoded -
  cloning this repo to a different drive/path requires no config changes.
- No AI provider is wired up yet (`AI_ACTIVE_PROVIDER=none` by default).
  `app/agents/` is an empty placeholder package.
- `Application.run()` currently just calls `startup()` then `shutdown()`
  with nothing in between - this is intentional (see ARCHITECTURE.md);
  the next phase that needs a long-running process should extend the body
  of `run()`, not rewrite `startup()`/`shutdown()`.
