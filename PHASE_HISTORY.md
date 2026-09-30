# Phase History

## Phase 1 - Foundation, Architecture & Project State

**Completed:** 2026-09-29
**Status:** Complete

### Starting point

`C:\StrategyResearchLab` was an empty directory (no prior code, no git
repo). Nothing to preserve.

### What was built

See PROJECT_STATE.md for the full current-state description and
ARCHITECTURE.md for design rationale. Summary: project scaffolding
(`pyproject.toml`, `.venv`, `.gitignore`, `.env.example`), centralized
config, structured JSONL logging, SQLite schema foundation (10 tables,
versioned migrations), a persistent event system, a state/checkpoint
system, a minimal application entry point, four AI hand-off docs, and a
30-test automated suite (all passing).

### Key decisions

- **Config:** stdlib `dataclasses` + `python-dotenv`, not `pydantic`.
  Reasoning: the brief asked for "no unnecessary dependencies"; the
  validation `pydantic` would add isn't needed yet for a handful of typed
  env vars with defaults, and dataclasses keep the dependency list to
  exactly `python-dotenv` (runtime) + `pytest` (dev).
- **Logging categories:** followed the brief's explicit section-3 category
  list (8 categories) over its example directory tree, which listed a
  different, conflicting set (`agent`, `hourly`, plural `experiments`).
  Documented in ARCHITECTURE.md under "Documented deviations."
- **Checkpoints stored twice:** once in SQLite (`checkpoints` table, for
  querying) and once as a plain JSON file under
  `data/cache/checkpoints/<id>.json` (for recovery even if the database
  file itself is the thing that's broken).
- **No ORM.** Raw `sqlite3` + hand-written SQL in `app/database/schema.py`.
  Reasoning: schema is still small and will change shape as later phases
  land; an ORM's migration machinery would be premature.
- **`Application.run()` is a bounded startup/shutdown cycle, not a loop.**
  The brief explicitly forbids implementing the autonomous research loop
  in Phase 1; `run()` was written so a future phase can insert a
  long-running loop between `startup()` and `shutdown()` without changing
  either of those methods' contracts.
- **Placeholder packages contain only a docstring.** `app/api`,
  `app/dashboard`, `app/supervisor`, `app/research`, `app/backtesting`,
  `app/systems`, `app/agents` were created empty rather than with
  speculative base classes/interfaces, per the "avoid unnecessary
  complexity" / "don't design for hypothetical future requirements"
  guidance.

### Verification performed

- `pytest -v`: 30/30 passed (config, logging, database, events, state,
  app lifecycle - each against an isolated `tmp_path` `Settings`
  instance).
- `main.py` run manually end-to-end against the real project paths:
  confirmed `application_started`/`application_stopped` events recorded,
  `system_status` row transitions `starting -> running -> stopped`,
  `current_state.json` reflects the same, and all 8 log category files
  are created under `logs/`.

### Deferred to later phases

Everything listed in the Phase 1 brief's "DO NOT BUILD YET" section: the
five research systems, autonomous strategy discovery/experiment loops,
the full AI research layer, the full Supervisor Agent, the full
dashboard, live trading, and large historical data downloads.

## Phase 2 - Deterministic Backtesting Engine

**Completed:** 2026-09-29
**Status:** Complete

### Starting point

Phase 1 foundation, unmodified except where this phase's brief
explicitly required a database extension (see below). No backtesting
code existed yet - `app/backtesting/` was an empty placeholder package.

### What was built

A 15-module deterministic backtesting engine (`app/backtesting/`) plus
59 new tests (`tests/backtesting/`, all synthetic data) and a database
schema migration. Full design writeup: ARCHITECTURE.md "Phase 2 -
Deterministic Backtesting Engine". Summary: candle/timeframe model with
UTC-canonical close-time timestamps; look-ahead-safe multi-timeframe
access (`MultiTimeframeView`); a generic `Strategy` interface; a full
signal -> order -> fill -> position -> trade execution pipeline with
independently configurable fee/slippage models; an explicit, configurable
intrabar stop/target ambiguity policy; long and short support; trade
recording, performance metrics, and an equity curve computed strictly
from completed trades; a structured, JSON-serializable `BacktestResult`
with a reproducibility fingerprint; and persistence into the existing
Phase 1 `experiments`/`trades`/`experiment_results` tables.

### Key decisions

- **`Candle.timestamp` = bar close time, not open time.** Chosen
  specifically so "has this candle's data become available yet" is a
  single timestamp comparison - the entire look-ahead-protection
  mechanism in `engine.py` rests on this convention. Documented as a
  load-bearing decision because most raw market-data feeds label candles
  by open time, so any future data-ingestion code must convert.
- **One-candle delay between signal and fill**, enforced structurally
  (orders queued at candle `i`'s close only execute at candle `i+1`),
  not by a bolted-on look-ahead checker. `Signal.timestamp` mismatch
  raises `LookAheadError` rather than being trusted.
- **`gross_pnl` computed from theoretical (pre-slippage) prices, not
  actual fill prices.** An earlier version computed it from actual
  (already-slipped) prices and then subtracted `slippage_cost` again,
  double-counting slippage in `net_pnl`. Caught before any test was
  written against the wrong formula, by hand-deriving the expected
  numbers for a slippage test case and finding they didn't reconcile
  with the "real economics" (raw executed-price P&L minus fees). Fixed
  in `portfolio.py::close_position` by storing `entry_theoretical_price`
  on `Position` separately from the actual (reported) `entry_price`. See
  `tests/backtesting/test_execution.py::
  test_fees_and_slippage_combined_do_not_double_count` for the
  regression test, which independently re-derives net P&L from raw
  executed prices as a cross-check.
- **Stop-loss/take-profit checks skip a position's own opening candle.**
  Sidesteps a second intrabar-ambiguity question (did the entry happen
  before or after the stop was touched, within the same candle) rather
  than adding another policy knob for it. Structural, not a special
  case: the stop-check step runs before that candle's entry orders are
  applied, so the position simply doesn't exist yet when the check runs.
- **At most one open position per symbol; a duplicate open signal is
  cancelled with a warning rather than queued, scaled-in, or used to
  reverse.** A strategy wanting to flip must close first (which, by the
  look-ahead rule, takes a separate candle). Kept the execution model
  simple for a first engine; resting/scaling order books are future
  scope if a strategy actually needs them.
- **LIMIT orders don't rest across candles** - filled if the very next
  candle's range touches the price, cancelled otherwise. Satisfies the
  brief's "limit orders where practical" without building a resting
  order book.
- **No leverage/margin anywhere** (`positions.py`). Explicitly deferred
  per the brief; `quantity * price` is the full notional throughout.
- **Reused Phase 1's `experiments`/`trades`/`experiment_results` tables**
  (migration 2: added `experiments.strategy_name`/`fingerprint`,
  `trades.gross_pnl`/`slippage_cost`/`return_pct`/`exit_reason`) instead
  of a parallel `backtest_runs` table - the brief said "extend only where
  necessary," and the Phase 1 schema's generic shape (esp.
  `experiment_results`' metric-name/value rows) already covered
  performance metrics with zero new tables.
- **Undefined metrics return `None`, not `inf`/`nan`/an exception** (e.g.
  `profit_factor` with no losing trades) - keeps `BacktestResult`
  losslessly JSON-serializable and keeps equality checks in
  reproducibility tests well-defined.
- **Mock strategies for engine validation live in `tests/fixtures/`, not
  `app/backtesting/`** - keeps production code free of anything that
  isn't a real interface, consistent with the "no speculative code"
  stance carried over from Phase 1.

### Verification performed

- `pytest -v`: 89/89 passed (30 from Phase 1 unchanged + 59 new), run
  after every module was wired together, not just at the end.
- Manual end-to-end smoke test via the real venv interpreter (outside
  pytest): built a 4-candle synthetic series, ran a scripted long
  trade through `run_backtest`, and printed the resulting trade P&L,
  fingerprint, and JSON serialization - confirmed the public
  `app.backtesting` import surface and `BacktestResult.to_json()` work
  end to end, not just through test fixtures.
- Hand-traced the exact expected numbers (fill prices, gross/net P&L,
  fees, slippage, drawdown) for every accounting/execution/intrabar test
  before running them, specifically to catch formula bugs like the
  gross/net double-counting one above rather than relying on the code
  to grade its own homework.

### Deferred to later phases

Everything in the Phase 2 brief's "SAFETY / SCOPE" section: live
trading, exchange order execution, autonomous strategy discovery, AI
strategy generation, the five research systems, the full dashboard, the
Supervisor Agent, and large historical data downloads. Also not yet
built (in scope for later, not prohibited, just not needed yet): a
resting/scaling order book, leverage/margin, multi-symbol concurrent
portfolios (the engine supports the data model but `Portfolio`/`engine.py`
assume one symbol per run), and wiring the engine into `Application`'s
lifecycle.

## Phase 3 - Five Independent Research Systems

**Completed:** 2026-09-29
**Status:** Complete

### Starting point

Phase 1 + Phase 2 baseline (89 tests) re-verified green before any
change. `app/systems/` was an empty placeholder package; `app/research/`
likewise. No changes were made to `app/backtesting/`'s public behavior -
only additive database/event extensions elsewhere.

### What was built

Five independent research systems (`app/systems/`, 18 modules, 66 new
tests in `tests/systems/`) sharing a common `ResearchSystem`/
`ResearchRequest` interface: Parameter Explorer, Rule/Logic Explorer,
Risk/Execution Optimizer, Market-Condition Tester, and an Adversarial
Research System. An experiment/campaign model
(`ExperimentDefinition`/`ExperimentRecord`, `CampaignRecord`) implementing
the brief's lineage (Strategy -> Campaign -> Experiment -> Backtest Run
-> Backtest Result), deterministic experiment fingerprinting and
deduplication, an `ExperimentRunner`/`CampaignRunner` that call Phase 2's
`run_backtest()` and never compute financial metrics themselves, two new
database tables (migration 3), and six new `EventType` members. Full
design writeup: ARCHITECTURE.md "Phase 3 - Five Independent Research
Systems".

### Key decisions

- **`app/systems/` is the new, higher-level concept; Phase 2's
  `experiments` table stays exactly what it was ("Backtest Run" in the
  lineage), not renamed or repurposed.** The brief's lineage diagram
  (Strategy -> Campaign -> Experiment -> Backtest Run -> Backtest Result)
  put a NEW "Experiment" concept above the thing Phase 1/2 already called
  `experiments` - so two new tables (`research_campaigns`,
  `research_experiments`) were added rather than overloading the
  existing one, keeping Phase 2 untouched.
- **`research_experiments.fingerprint` is indexed but not unique**,
  unlike Phase 2's `experiments.fingerprint`. Deduplication in this phase
  means "don't re-run the engine for a matching configuration," not "only
  one row may ever exist for a configuration" - the brief explicitly says
  to *reference* the existing result, which requires a row per request
  even when it's a duplicate.
- **A parameter-propagation bug was caught by a manual smoke test before
  the automated suite was written**, the same discipline Phase 2 used to
  catch its gross/net P&L bug: `ExperimentDefinition.parameters` was
  never copied into `BacktestConfig.strategy_params`, so two experiments
  that only differed by resolved parameters (e.g. a Parameter Explorer
  qty sweep) hashed to the SAME Phase-2 fingerprint and the second
  `save_backtest_result()` call raised `sqlite3.IntegrityError: UNIQUE
  constraint failed: experiments.fingerprint`. Fixed in
  `ExperimentRunner.execute()` with `dataclasses.replace(definition.
  execution_config, strategy_params=definition.parameters)` before
  calling `run_backtest()`. This also fixed a second gap noticed while
  investigating: `StrategyContext.params` would otherwise have been
  empty for every Phase 3 experiment, contrary to Phase 2's own
  documented strategy-parameter channel.
- **Rule Explorer and Risk/Execution Optimizer variants are pre-built by
  the caller** (`RuleVariant`/`ExecutionVariant`), not generated by the
  system itself - consistent with the brief's "explicit strategy variants
  rather than allowing arbitrary uncontrolled code generation" and kept
  the same design language across systems (Market-Condition Tester's
  `Segment`s and Adversarial's use of the same segmentation module follow
  the identical pattern).
- **Segmentation lives in `market_conditions/segmentation.py` and is
  reused by the Adversarial system** (`segment_leave_one_out_chronological`)
  rather than duplicated - "does performance depend on one tiny market
  period" (Adversarial) and "how does the strategy behave in different
  conditions" (Market-Condition Tester) are the same underlying operation
  (slice the candles), just asked for different reasons.
- **Campaign counts are recomputed from `research_experiments` rows on
  every update (`refresh_campaign_counts`), never incremented.** Removes
  an entire class of drift/race bugs and is naturally correct under the
  concurrent execution a future phase may add.
- **No AI, no randomness, no "best result" anywhere in `app/systems/`.**
  `ParameterSpace.generate_combinations()` is a deterministic Cartesian
  product; the Adversarial system's public surface has no ranking/
  optimization method at all - verified directly in
  `tests/systems/test_adversarial.py::
  test_never_computes_a_best_result_it_only_generates_experiments`.

### Verification performed

- `pytest -v`: 155/155 passed (89 from Phases 1-2 unchanged + 66 new),
  run both before starting (baseline check) and after every module was
  wired together.
- Manual end-to-end smoke test via the real venv interpreter (outside
  pytest, twice - before and after the parameter-propagation fix):
  built a Parameter Explorer request over a 2-value parameter space, ran
  it through `CampaignRunner`, and inspected the resulting `experiments`/
  `research_experiments` rows directly. The first run surfaced the
  `IntegrityError` above; the second confirmed the fix (2/2 experiments
  completed, `context.params` correctly populated, and a repeat campaign
  run correctly deduplicated both experiments with zero new backtest
  runs).

### Deferred to later phases

Everything in the Phase 3 brief's "DO NOT IMPLEMENT YET" section: AI
strategy discovery (Claude/Freebuff/Ollama), browser research,
autonomous strategy discovery, strategy qualification, live trading,
exchange APIs, large historical data downloads, the full dashboard, the
Supervisor Agent, a 24/7 autonomous loop, Monte Carlo, and sophisticated
ML regime detection. Also not built (future scope, not prohibited): any
actual concurrent/parallel experiment execution (the architecture
supports it - see ARCHITECTURE.md "Concurrency foundation" - but
`CampaignRunner` still runs sequentially), wiring research systems into
`Application`'s lifecycle or a CLI/scheduler, and populating the
`strategies` table (experiments still record strategy name/version as
plain strings).
