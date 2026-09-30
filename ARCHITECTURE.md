# Architecture

Status: reflects Phase 1 (Foundation) and Phase 2 (Deterministic
Backtesting Engine). Updated as later phases land.

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

### Placeholder packages (not yet implemented)

`app/api`, `app/dashboard`, `app/supervisor`, `app/research`,
`app/systems`, `app/agents` still exist as empty packages (single
docstring `__init__.py`) so the import structure and directory layout are
stable for later phases to build into, without any code depending on
them yet. `app/backtesting` is no longer a placeholder - see "Phase 2"
below.

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

Migration 2 (Phase 2) extended `experiments` (added `strategy_name`,
`fingerprint` with a unique index) and `trades` (added `gross_pnl`,
`slippage_cost`, `return_pct`, `exit_reason`) rather than introducing
parallel backtesting-only tables - see "Phase 2 - Database integration"
below.

## Phase 2 - Deterministic Backtesting Engine

`app/backtesting/` is the quantitative source of truth: given the same
market data, strategy, parameters, and execution assumptions,
`run_backtest()` always produces the same `BacktestResult`. No AI
involvement anywhere in this package - see the package docstring
(`app/backtesting/__init__.py`).

### Module map

```
market_data.py      Candle, CandleSeries, Timeframe. Candle.timestamp is
                     the bar's CLOSE time (see "Time handling" below) and
                     is always normalized to UTC. CandleSeries enforces
                     strictly increasing timestamps at construction.
multi_timeframe.py   MultiTimeframeView: the only sanctioned way a
                     strategy reads a timeframe other than its primary
                     one, look-ahead safe by construction.
signals.py            Signal, SignalAction, OrderType - a strategy's
                     output. Pure intent, no execution details.
strategy.py            Strategy (ABC) + StrategyContext - everything a
                     strategy is allowed to see when producing signals.
orders.py / fills.py   Order (engine-internal, execution-ready) and Fill
                     (what an order becomes once resolved against a
                     candle). signal -> order -> fill -> position -> trade.
positions.py            Side, Position (single open position per symbol).
costs.py                 FeeModel / SlippageModel protocols + Zero and
                     simple (percentage / fixed-bps) implementations.
                     Independently configurable, no exchange defaults.
intrabar.py               IntrabarPolicy + resolve_exit(): the explicit,
                     configurable answer to "stop and target both fall
                     inside one candle's range - which hit first?"
execution.py               process_candle(): turns pending orders +
                     open-position stop/target levels into fills against
                     one candle, and applies them to the Portfolio.
portfolio.py                 Portfolio: cash/equity + open positions.
                     Equity changes only at trade close.
equity.py, metrics.py          Equity curve / drawdown and the Phase-2
                     brief's performance-metric list, computed purely
                     from completed trades.
result.py                       BacktestResult, ExecutionAssumptions,
                     and the reproducibility fingerprint.
engine.py                         run_backtest(): orchestrates the above
                     into the candle-by-candle loop; owns look-ahead
                     protection (see below).
persistence.py                     Saves a BacktestResult into the
                     Phase 1 database foundation.
```

No real trading strategy lives in this package - `tests/fixtures/
mock_strategies.py` has the minimal strategies (`ScriptedStrategy`,
`NoOpStrategy`, `RecordingStrategy`) used to validate the engine itself.

### Time handling

Canonical internal timezone is UTC. `Candle.__post_init__` rejects naive
timestamps and converts any tz-aware timestamp to UTC, so DST and
local-time ambiguity never reach comparison/ordering logic.

`Candle.timestamp` is the bar's **close** time, not its open time. This
is the anchor the whole look-ahead protection design rests on: a candle
"exists" to the engine only once its close time has passed, i.e. once all
of its OHLCV data is actually known. This will matter for session/
killzone logic in later phases (London/New York opens, ORB, etc.) -
converting an exchange's open-time-labeled data into this convention is
each future data-ingestion component's responsibility, not the engine's.

### Look-ahead bias protection (brief section 9)

For candle index `i` in `engine.run_backtest()`:

1. Orders queued from candle `i-1`'s close are executed against candle
   `i` (market orders fill at `i.open`). Existing positions'
   stop-loss/take-profit are checked against candle `i`'s range in this
   same step, *before* any entry from this step is applied - so a
   position cannot be stopped out on the very candle it was opened on.
2. `strategy.on_bar()` receives a `StrategyContext` whose `history` is
   `candles[0:i+1]` - never candle `i+1` or later, and whose
   `higher_timeframes` (`MultiTimeframeView`) exposes only higher-TF
   candles that had already closed at or before candle `i`'s timestamp.
3. Any `Signal`s returned become `Order`s queued for candle `i+1`, not
   `i`. `Signal.timestamp` must equal candle `i`'s timestamp; a mismatch
   raises `LookAheadError` rather than being silently trusted - this
   catches a strategy that (accidentally or otherwise) fabricates a
   different point in time than the one it was actually given.

This one-candle delay between decision and execution is the entire
mechanism - there is no separate "look-ahead checker" bolted on
afterward. Tests: `tests/backtesting/test_lookahead.py`.

### Intrabar execution assumptions (brief section 8)

OHLC data does not record the order in which price levels were touched
within a candle. `IntrabarPolicy` (`intrabar.py`) makes the ambiguous
case - both stop-loss and take-profit inside one candle's range -
explicit and configurable (`STOP_FIRST` default, or `TARGET_FIRST`)
instead of silently picking one. A position's stop/target are only
checked starting the candle *after* it was opened (see look-ahead
section above) - this was chosen specifically to avoid a second,
separate ambiguity (did the entry happen before or after the stop was
touched, on the very same candle) rather than adding another policy knob
for a case that's rare in practice once trading on closed bars.

### Gross vs net P&L

`Trade.gross_pnl` is computed from the **theoretical** (pre-slippage)
fill prices; `fees` and `slippage_cost` are then both subtracted to get
`net_pnl`. This was a deliberate fix during development: an earlier
version computed `gross_pnl` from the *actual* (already slippage-adjusted)
fill prices and then subtracted `slippage_cost` again on top, silently
double-counting slippage's cost. `Trade.entry_price`/`exit_price` are
still the actual executed (post-slippage) prices, for realistic
reporting - see `portfolio.py`'s `close_position()` for the exact
derivation and `tests/backtesting/test_execution.py::
test_fees_and_slippage_combined_do_not_double_count` for the regression
test (it independently re-derives net P&L from raw executed prices minus
fees and checks it matches).

### Order model simplifications

To keep Phase 2 an honest foundation rather than a half-built exchange
simulator, a few things were deliberately simplified and documented
rather than silently assumed:

- **At most one open position per symbol.** A signal to open while
  already in a position is cancelled (with a warning), not queued or
  used to reverse/scale in. A strategy that wants to flip must close
  first, which (per the look-ahead rule) takes a separate candle.
- **LIMIT orders don't rest.** A LIMIT order fills if the very next
  candle's `[low, high]` touches its price; otherwise it's cancelled,
  not carried forward indefinitely. A real resting order book is future
  scope if a strategy ever needs it.
- **No leverage/margin.** `quantity * price` is the full notional
  everywhere; there is no margin multiplier. See `positions.py`'s module
  docstring. A future phase needing leverage should add it as an
  explicit multiplier in the portfolio layer.
- **A position still open at the end of the data is force-closed** at
  the last candle's close, tagged `ExitReason.END_OF_DATA`, with a
  warning - so a backtest never silently drops an open position from the
  results.

### Multi-timeframe foundation (brief section 10)

`MultiTimeframeView.as_of(timeframe, timestamp)` returns only the
candles of that timeframe whose own timestamp (close time) is `<=` the
given timestamp - i.e. only candles that have actually closed. A
strategy never touches a raw `CandleSeries` for a non-primary timeframe
directly; it only ever goes through this view (reachable from
`StrategyContext.higher_timeframes`), which is what makes higher-TF
look-ahead structurally impossible rather than merely convention.

### Reproducibility (brief section 15)

`compute_fingerprint()` hashes strategy name/version, parameters, a data
identity hash (`compute_data_identity()` - symbol, timeframe, count,
span, and a hash of closes; a cheap identity check, not full data
lineage/versioning, which is out of scope), the execution assumptions
(starting capital, fee/slippage model type + params, intrabar policy),
and `ENGINE_VERSION`. `ENGINE_VERSION` must be bumped whenever a code
change could change a backtest's numeric output for the same inputs, so
a changed engine can never silently masquerade as reproducing an old
result. `run_id` is a fresh UUID per run (so re-running the same
backtest doesn't collide identities); `fingerprint` is what should be
checked for "is this the same experiment" (see `experiments.fingerprint`,
unique-indexed).

### Database integration (Phase 2)

Reuses the Phase 1 `experiments` / `trades` / `experiment_results`
tables (migration 2 in `app/database/schema.py`) rather than adding a
parallel `backtest_runs` table - one experiment row per backtest run
(`system_name = "backtesting_engine"`), one trades row per `Trade`, and
performance metrics as `experiment_results` rows (metric name/value),
which already fit the "at minimum: total trades, win rate, ..." list
without any new table. `app/backtesting/persistence.py` is the only
writer. `strategies.id` / `trades.strategy_id` are left `NULL` for
Phase-2 runs - wiring a `ScriptedStrategy`/mock into the `strategies`
table would misrepresent it as a real discovered strategy; that
association is Phase 3+'s concern once strategies are actually
discovered and tracked as first-class rows.

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
  Tester, Adversarial/Research System. Each should call
  `app/backtesting/run_backtest()` with a real `Strategy` and persist via
  `app/backtesting/persistence.py`, plus `events` through the existing
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
