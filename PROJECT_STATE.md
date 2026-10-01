# Project State

**Active phase:** Phase 5 - Real AI Providers + Provider Portability
**Status:** Complete
**Last updated:** 2026-09-30

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

- Five independent research systems (`app/systems/`, 18 modules):
  Parameter Explorer, Rule/Logic Explorer, Risk/Execution Optimizer,
  Market-Condition Tester, and an Adversarial Research System, all
  sharing a common `ResearchSystem`/`ResearchRequest` interface and an
  `ExperimentDefinition` -> `ExperimentRunner`/`CampaignRunner` ->
  `run_backtest()` pipeline. Deterministic parameter generation, explicit
  rule variants, configurable execution/risk variants, basic candle
  segmentation (volatility median-split, day-of-week, session windows,
  chronological chunks/leave-one-out), and adversarial perturbations
  (worse costs, parameter jitter, leave-one-period-out) - none of them
  compute P&L or rank results; all of it flows through Phase 2's
  `run_backtest()`. Deterministic experiment fingerprinting and
  deduplication (an experiment matching an already-completed one's exact
  configuration is marked complete without re-running the engine).
  Campaigns group experiments with live-recomputed counts. Persisted into
  two new tables (schema migration 3): `research_campaigns`,
  `research_experiments`. See ARCHITECTURE.md "Phase 3 - Five Independent
  Research Systems" for the full design, including a
  parameter-propagation bug caught and fixed during development (two
  differently-parameterized experiments were colliding on Phase 2's own
  fingerprint unique index).
- 66 new automated tests (`tests/systems/`, 155 total with Phases 1-2),
  all passing: parameter-space generation and determinism, experiment
  fingerprinting, all five systems' experiment generation, segmentation
  functions, experiment/campaign execution (happy path, deduplication,
  deterministic failure handling, event emission), and database
  persistence/migration compatibility. Synthetic data and mock strategies
  only - no real market data.

- An AI research layer (`app/ai/`, 12 modules): an `AIProvider`
  abstraction (no Claude/Freebuff/Ollama-specific code anywhere) with a
  deterministic `MockAIProvider` as the only implementation; typed,
  validated AI output (`ResearchDecision`/`ExperimentProposal` - no
  free-form text is ever interpreted); a `ResearchCatalog` (strategy,
  market data, execution assumptions, and named rule/execution-variant
  presets the AI can select from but never author); deterministic
  proposal validation and translation into Phase 3's own
  `ResearchRequest` types (no duplication of the Phase 3 experiment
  model); a bounded `ResearchContext` builder (last-10-experiments,
  metrics only, never raw trades or the whole database); and a
  `ResearchAgent` running the Objective -> Hypothesis -> Experiment ->
  Backtest -> Result -> Analysis -> next Hypothesis loop, bounded by a
  human-supplied, frozen `ResearchLimits` the AI cannot alter. The AI
  never calls `run_backtest()` directly - every experiment goes through
  Phase 3's `CampaignRunner`/`ExperimentRunner`, unchanged - and never
  computes P&L or any financial metric. Persisted into three new tables
  (schema migration 4): `ai_research_sessions`, `ai_research_decisions`,
  `ai_research_session_campaigns`; AI invocation audit logging reuses
  Phase 1's `ai_actions` table. See ARCHITECTURE.md "Phase 4 - AI
  Research Layer" for the full design.
- 66 new automated tests (`tests/ai/`, 221 total with Phases 1-3), all
  passing: provider behavior (mock + failure), decision/proposal
  validation and translation for all five research systems, context
  construction, the full agent loop (happy path, each of the four
  limits, AI-requested stop, provider failure, proposal rejection,
  cross-iteration deduplication), persistence, an end-to-end integration
  test of the whole chain, and structural safety checks (AST-verified:
  no file in `app/ai/` imports or calls `run_backtest`; `ResearchLimits`
  is frozen; `ResearchDecision` has no field that could carry limits;
  no `DELETE FROM` anywhere in the package). Synthetic data and mock
  strategies/providers only.

- Real AI provider adapters behind the unchanged Phase 4 `AIProvider`
  interface (`app/ai/providers/`): `ClaudeAIProvider` (real Anthropic
  Messages API adapter, stdlib `urllib` HTTP, forced tool-use for
  structured output, no new dependency); `OllamaAIProvider` (real local
  Ollama `/api/chat` adapter, same stdlib-HTTP approach); `FreebuffAIProvider`
  (an honest structural placeholder only - no verified API contract was
  available, so it is wired into the architecture but `invoke()` always
  raises, clearly explaining why). A shared, strict JSON parser
  (`app/ai/providers/structured_output.py`) is the one place any
  JSON-returning provider's output becomes a `ResearchDecision` -
  rejecting malformed output deterministically rather than guessing. A
  new `AIProviderRouter` (`app/ai/router.py`) itself implements
  `AIProvider`, so `ResearchAgent` needs zero code changes to use it; it
  selects/falls back between providers by configuration
  (`Settings.ai_provider`, extended with a fallback chain and an
  explicit mock-fallback gate) and never silently falls back from a
  failed real provider onto a mock one. Three new `AIProviderError`
  subclasses (auth/rate-limit/unavailable), a `ProviderCapabilities`
  model, usage/cost/request-id tracking on `AIInvocationResponse`, and a
  shared `RESEARCH_POLICY` prompt text complete the picture. See
  ARCHITECTURE.md "Phase 5 - Real AI Providers + Provider Portability"
  for the full design, including exactly what's untested and why
  (no credentials/local server were available in this environment).
- 69 new automated tests (`tests/ai/`, 290 total with Phases 1-4), all
  passing: structured-output parsing (strict rejection of malformed
  input), both real providers against a mocked HTTP transport (success,
  auth/rate-limit/server/network/timeout error mapping, secret
  redaction), the Freebuff placeholder's honesty, the router (primary-
  only, real-to-real fallback, mock-fallback gating, invalid provider
  names), a cross-provider contract suite, and security checks (no
  eval/exec/subprocess in `app/ai/`, no secret ever persisted to
  `events`/`ai_actions`, `.env.example`/`.gitignore` still safe). Zero
  real network calls or credentials used; one real-but-expected-to-fail
  call against the confirmed-absent local Ollama server.

## What has been completed

Phase 1 (all 15 requirements), Phase 2 (all 24 requirements), Phase 3
(all 21 requirements), Phase 4 (all 26 requirements), and Phase 5 (all
31 requirements) from their respective briefs: see PHASE_HISTORY.md for
what each phase built and why.

## What remains (explicitly out of Phase 5 scope)

- Actual trading strategies (only mock/scripted ones exist, solely to
  validate the engine and research systems), a working Freebuff
  integration (no verified API contract yet), real-provider smoke
  testing (no credentials were available), a running local model server
  to test `OllamaAIProvider` against, browser automation, autonomous
  strategy discovery, strategy qualification, live trading / exchange
  execution, the full dashboard, the Supervisor Agent, a 24/7 autonomous
  loop, Monte Carlo, sophisticated regime detection, distributed
  workers, and large historical data downloads. See CURRENT_TASK.md and
  ARCHITECTURE.md's "Future expansion points".

## Important technical state

- Real (non-test) database, once `main.py` is run, lives at
  `data/cache/state/strategy_research_lab.db` (git-ignored; recreated
  automatically by `Database.initialize_schema()` if missing).
- `Settings.project_root` and every path derived from it are computed
  relative to the location of `app/config/settings.py`, not hardcoded -
  cloning this repo to a different drive/path requires no config changes.
- Real `AIProvider` adapters now exist (`ClaudeAIProvider`,
  `OllamaAIProvider`) but neither has been exercised against a real
  backend - no `ANTHROPIC_API_KEY` and no reachable Ollama server were
  available while building Phase 5. `Settings.ai_provider.active_provider`
  (`AI_ACTIVE_PROVIDER`) now also accepts `mock`, and
  `app/ai/router.py::build_router_from_settings()` is the config-driven
  way to construct a provider/router from `Settings` - but nothing in
  `app/core`/`main.py` calls it yet; a `ResearchAgent` is still
  constructed directly in Python with an explicit `AIProvider` instance.
  `app/agents/` is still an empty placeholder package - the AI research
  layer was built at `app/ai/` instead; see ARCHITECTURE.md "Documented
  deviations" for why. The backtesting engine has zero AI involvement by
  design - see ARCHITECTURE.md "Core principle" - and nothing in Phase 4
  or 5 changes that: the AI layer reads `BacktestResult` data, never
  computes it.
- `Application.run()` currently just calls `startup()` then `shutdown()`
  with nothing in between - this is intentional (see ARCHITECTURE.md);
  the next phase that needs a long-running process should extend the body
  of `run()`, not rewrite `startup()`/`shutdown()`. The backtesting engine
  is not yet wired into `Application` - it is called directly
  (`app.backtesting.run_backtest`), which is sufficient until a research
  system or CLI needs to trigger runs through the app lifecycle.
- Database schema is now at version 4 (`app/database/schema.py`):
  migration 2 added `experiments.strategy_name`/`fingerprint` (unique
  indexed) and `trades.gross_pnl`/`slippage_cost`/`return_pct`/
  `exit_reason`; migration 3 added `research_campaigns` and
  `research_experiments`; migration 4 added `ai_research_sessions`,
  `ai_research_decisions`, and `ai_research_session_campaigns`.
  Migrations are additive/idempotent - an existing Phase 1/2/3 database
  upgrades automatically on next `initialize_schema()` call.
- Research systems and the AI layer are both invoked directly from
  Python (`ExperimentRunner`/`CampaignRunner`/`ResearchAgent`), same as
  the backtesting engine - none of them are wired into `Application`'s
  lifecycle or any CLI/scheduler yet.
  `strategies` table is still unpopulated; experiments (Phase 3) and
  research sessions (Phase 4) both record `strategy_name`/
  `strategy_version` as plain strings, not a `strategies` row - see
  ARCHITECTURE.md "Future expansion points" for why that's deferred to
  strategy discovery/qualification.
- Database schema is still at version 4 - Phase 5 added no tables
  (provider/router state is entirely in-process; AI invocation audit
  logging reuses Phase 1's `ai_actions` table unchanged, just with more
  metadata keys).
- `pyproject.toml` is unchanged by Phase 5 - both real provider adapters
  use stdlib `urllib.request`, not the `anthropic` package or any Ollama
  client library (see ARCHITECTURE.md "Phase 5 - No new dependency").
