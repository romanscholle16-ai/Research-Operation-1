# Project State

**Active phase:** Phase 2 - Deterministic Backtesting Engine
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

- A deterministic backtesting engine (`app/backtesting/`, 15 modules):
  candle/timeframe model with UTC-canonical, close-time timestamps;
  look-ahead-safe multi-timeframe access; a generic `Strategy` interface;
  signal -> order -> fill -> position -> trade execution with configurable
  fee/slippage models and an explicit, configurable intrabar stop/target
  ambiguity policy; long and short support (no leverage - deferred and
  documented); trade recording; performance metrics and an equity curve
  computed purely from completed trades; a structured, serializable
  `BacktestResult` with a reproducibility fingerprint; and persistence
  into the Phase 1 database (schema migration 2). See ARCHITECTURE.md
  "Phase 2 - Deterministic Backtesting Engine" for the full design,
  including the gross-vs-net P&L double-counting bug that was caught and
  fixed during development.
- 59 new automated tests (`tests/backtesting/`, 89 total with Phase 1),
  all passing: candle validation/ordering, long/short execution, fees,
  slippage, order/fill sequencing, LIMIT order handling, stop-loss/
  take-profit including the ambiguous-candle policy, P&L/equity/drawdown/
  metrics accounting (including degenerate no-trade cases), look-ahead
  protection (signal timestamp enforcement, history bounds, multi-
  timeframe synchronization), reproducibility (identical inputs ->
  identical fingerprint; changed inputs -> changed fingerprint), and
  database persistence/migration compatibility. Synthetic data only - no
  real market data downloaded.

## What has been completed

Phase 1 (all 15 requirements) plus Phase 2 (all 24 requirements) from
their respective briefs: see PHASE_HISTORY.md for what each phase built
and why.

## What remains (explicitly out of Phase 2 scope)

- Actual trading strategies (only mock/scripted ones exist, solely to
  validate the engine), the five research systems, autonomous strategy
  discovery/experiment loops, the full AI research layer, the full
  Supervisor Agent, the full dashboard, live trading / exchange
  execution, and large historical data downloads. See CURRENT_TASK.md and
  ARCHITECTURE.md's "Future expansion points".

## Important technical state

- Real (non-test) database, once `main.py` is run, lives at
  `data/cache/state/strategy_research_lab.db` (git-ignored; recreated
  automatically by `Database.initialize_schema()` if missing).
- `Settings.project_root` and every path derived from it are computed
  relative to the location of `app/config/settings.py`, not hardcoded -
  cloning this repo to a different drive/path requires no config changes.
- No AI provider is wired up yet (`AI_ACTIVE_PROVIDER=none` by default).
  `app/agents/` is an empty placeholder package. The backtesting engine
  has zero AI involvement by design - see ARCHITECTURE.md "Core principle".
- `Application.run()` currently just calls `startup()` then `shutdown()`
  with nothing in between - this is intentional (see ARCHITECTURE.md);
  the next phase that needs a long-running process should extend the body
  of `run()`, not rewrite `startup()`/`shutdown()`. The backtesting engine
  is not yet wired into `Application` - it is called directly
  (`app.backtesting.run_backtest`), which is sufficient until a research
  system or CLI needs to trigger runs through the app lifecycle.
- Database schema is now at version 2 (`app/database/schema.py`):
  migration 2 added `experiments.strategy_name`/`fingerprint` (unique
  indexed) and `trades.gross_pnl`/`slippage_cost`/`return_pct`/
  `exit_reason`. Migrations are additive/idempotent - an existing Phase 1
  database upgrades automatically on next `initialize_schema()` call.
