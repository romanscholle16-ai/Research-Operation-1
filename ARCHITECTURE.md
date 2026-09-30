# Architecture

Status: reflects Phase 1 (Foundation), Phase 2 (Deterministic
Backtesting Engine), Phase 3 (Five Independent Research Systems), and
Phase 4 (AI Research Layer). Updated as later phases land.

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
`app/agents` still exist as empty packages (single docstring
`__init__.py`) so the import structure and directory layout are stable
for later phases to build into, without any code depending on them yet.
`app/backtesting` and `app/systems` are no longer placeholders - see
"Phase 2" and "Phase 3" below.

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

## Phase 3 - Five Independent Research Systems

`app/systems/` builds five independent research systems on top of the
Phase 2 engine. None of them compute P&L, fees, slippage, drawdown,
expectancy, or profit factor - they only ever build `ExperimentDefinition`s
and hand them to `ExperimentRunner`, which is the sole caller of
`app.backtesting.run_backtest()` in this package.

### Experiment lineage

```
Strategy -> Research Campaign -> Experiment -> Backtest Run -> Backtest Result
```

`Strategy` here means "strategy name/version" (still just a string pair -
no `strategies` table row yet, same as Phase 2). "Backtest Run"/"Backtest
Result" are exactly Phase 2's `experiments` table row and `BacktestResult`
- Phase 3 does not touch either concept, it sits *above* them:

- `ExperimentDefinition` (`app/systems/experiment.py`) - the plan for one
  backtest, produced by a research system: strategy factory, resolved
  parameters, rule configuration, candles, and a `BacktestConfig`. Not
  persisted directly; it holds live objects (a `CandleSeries`, a
  `Callable`).
- `ExperimentRecord` - the persisted row (`research_experiments` table)
  after `ExperimentRunner` processes a definition: same facts, but
  serializable only (no live objects), plus status/timestamps/failure
  info/links to the actual backtest run.
- `CampaignRecord` (`app/systems/campaign.py`) - the persisted row
  (`research_campaigns` table) grouping the experiments from one
  `ResearchSystem.generate_experiments()` call submitted to
  `CampaignRunner`.

### Common interface

`ResearchSystem.generate_experiments(request) -> list[ExperimentDefinition]`
(`app/systems/base.py`) is the only method every system implements.
`ResearchRequest` carries the fields every system needs (strategy
factory/name/version, candles, execution config, base parameters); each
concrete request type (`ParameterExplorerRequest`, `RuleExplorerRequest`,
...) adds exactly one more field for what that system varies. A system
never calls `run_backtest()` itself.

```
app/systems/
    experiment.py        ExperimentDefinition, ExperimentRecord, ExperimentStatus
    campaign.py            CampaignRecord, CampaignStatus
    base.py                  ResearchSystem, ResearchRequest
    parameter_space.py         Fixed/ValueList/ValueRange/Categorical + ParameterSpace
    fingerprint.py                compute_experiment_fingerprint()
    persistence.py                   research_campaigns/research_experiments DB access
    runner.py                          ExperimentRunner, CampaignRunner
    parameter_explorer/                  ParameterExplorer
    rule_explorer/                         RuleExplorer, RuleVariant
    risk_execution/                          RiskExecutionOptimizer, ExecutionVariant
    market_conditions/                         MarketConditionTester + segmentation.py
    adversarial/                                 AdversarialResearchSystem, AdversarialConfig
```

### The five systems

- **Parameter Explorer** - `ParameterSpace.generate_combinations()`
  (deterministic Cartesian product, sorted parameter-name order, no
  randomness/AI) produces one experiment per combination. Generic: the
  strategy comes from `request.strategy_factory`, never hardcoded.
- **Rule/Logic Explorer** - takes a tuple of `RuleVariant`s, each an
  explicit, pre-authored `(name, strategy_factory, description)`. One
  experiment per variant; `rule_configuration` on the resulting
  experiment names exactly which variant produced it. Deliberately does
  NOT generate or synthesize logic itself (brief: "explicit strategy
  variants rather than allowing arbitrary uncontrolled code generation").
- **Risk/Execution Optimizer** - takes a tuple of `ExecutionVariant`s,
  each overriding a subset of `BacktestConfig`'s fee/slippage/intrabar-
  policy/starting-capital fields (`dataclasses.replace`, unset fields
  inherit the request's base config). No leverage/margin - Phase 2 was
  not extended to add it, per the brief's explicit instruction not to
  unless a concrete test requires it.
- **Market-Condition Tester** - takes pre-built `Segment`s
  (`app/systems/market_conditions/segmentation.py`) and runs one
  experiment per segment. Segmentation is deliberately basic and
  explainable: a median split on candle range (volatility), calendar
  day-of-week, fixed time-of-day session windows, and equal-sized
  chronological chunks - no regime-detection ML. A `Segment`'s candles
  need not be contiguous; `CandleSeries` only requires strictly
  increasing timestamps (Phase 2), so a filtered, non-contiguous subset
  (e.g. "every Tuesday") is a valid series.
- **Adversarial Research System** - generates a baseline plus perturbed
  variants: worse fees, worse slippage, one-parameter-at-a-time jitter,
  and leave-one-chronological-chunk-out (reusing the Market-Condition
  Tester's segmentation module via a new
  `segment_leave_one_out_chronological()` helper). Every non-baseline
  experiment's `parent_experiment_id` points at the baseline. This
  system only *generates* the perturbed experiments - it has no
  "best result" concept and nothing here judges whether a strategy
  survived them; that comparison is the future qualification system's
  job (brief section 14, explicitly deferred).

### Experiment execution and deduplication

`ExperimentRunner.execute(definition, campaign_id=None)`
(`app/systems/runner.py`):

1. Computes `(fingerprint, data_identity) = compute_experiment_fingerprint
   (definition)` - a hash over research system, strategy name/version,
   resolved parameters, rule configuration, execution assumptions
   (reusing Phase 2's own `ExecutionAssumptions.to_dict()`), data identity
   (reusing Phase 2's `compute_data_identity()`), and timeframe. The
   experiment's own `id`/campaign/timestamps are excluded on purpose -
   the fingerprint identifies the *configuration*, not the *request*.
2. Inserts a `CREATED` row and emits `EXPERIMENT_CREATED`.
3. Looks up an existing `COMPLETED`, non-duplicate experiment with the
   same fingerprint (`find_completed_by_fingerprint`, which excludes rows
   that are themselves marked as duplicates, so lookups always resolve to
   the original - no duplicate-of-duplicate chains). If found: marks this
   experiment `COMPLETED` pointing at the existing `backtest_run_id`,
   emits `EXPERIMENT_SKIPPED_DUPLICATE`, and returns WITHOUT calling
   `run_backtest()`.
4. Otherwise: `RUNNING` + `EXPERIMENT_STARTED`, builds the strategy
   (`definition.build_strategy()`), calls `run_backtest()`, persists via
   Phase 2's `app.backtesting.persistence.save_backtest_result()`, marks
   `COMPLETED` + `EXPERIMENT_COMPLETED` with `backtest_run_id`/
   `result_fingerprint` set.
5. Any exception during step 4 is caught, recorded as `FAILED` with
   `failure_info` (type, message, traceback), `EXPERIMENT_FAILED` is
   emitted, and **the exception is not re-raised** - so one bad
   experiment in a campaign of many does not abort the rest (brief
   section 5's "records errors deterministically").

A bug caught during development here: `definition.parameters` must be
copied into `BacktestConfig.strategy_params` before calling
`run_backtest()` - Phase 2's own fingerprint (`app/backtesting/
engine.py`) hashes `config.strategy_params`, and `experiments.fingerprint`
is Phase-2-unique-indexed. Without the copy, two Phase-3 experiments that
only differed by `definition.parameters` (e.g. a Parameter Explorer qty
sweep) produced the SAME Phase-2 fingerprint and the second `INSERT`
raised `sqlite3.IntegrityError: UNIQUE constraint failed: experiments.
fingerprint` - caught by a manual smoke test before the automated test
suite was written. Fixed in `ExperimentRunner.execute()`:
`config = dataclasses.replace(definition.execution_config,
strategy_params=definition.parameters)`. This also fixed a second,
related gap: `StrategyContext.params` would otherwise have been empty
for every Phase 3 experiment.

`CampaignRunner.run(definitions, ...)` creates a campaign row, emits
`CAMPAIGN_CREATED`/`_STARTED`, calls `ExperimentRunner.execute()` for each
definition in order, recomputes `experiment_count`/`completed_count`/
`failed_count` from the `research_experiments` rows themselves
(`refresh_campaign_counts` - a fresh `COUNT(*)` each time rather than
incrementing counters, so it can't drift and stays correct under future
concurrent execution), then emits `CAMPAIGN_COMPLETED`.

### Concurrency foundation (brief section 11)

No multiprocessing/threading was added this phase. What was designed for
it: `ExperimentRunner.execute()` is a pure function of `(definition,
campaign_id, db)` with no state held between calls, so it's safe to call
from a worker pool today without modification. `CampaignRunner.run()`'s
`for definition in definitions: self._experiment_runner.execute(...)`
loop is the one line a future concurrent executor would replace (e.g.
`ThreadPoolExecutor.map`) - `ExperimentRunner` itself would not need to
change. The real constraint for later: a single `sqlite3.Connection`
(`app.database.connection.Database`) is not thread-safe, so parallel
execution would need one `Database`/connection per worker - already
possible today since Phase 1 enabled WAL mode, which supports multiple
connections to the same file.

### Database additions (migration 3)

Two new tables (`app/database/schema.py`), extending Phase 1/2's schema
rather than replacing any of it:

- `research_campaigns` - id, strategy_name, research_system, purpose,
  configuration (JSON), status, experiment_count/completed_count/
  failed_count, timestamps.
- `research_experiments` - id, campaign_id (FK), research_system,
  strategy_name/version, parameters/rule_configuration/
  execution_configuration (JSON), data_identity, timeframe, data range,
  parent_experiment_id (self-FK), status, fingerprint,
  backtest_run_id (FK into Phase 2's `experiments` table),
  result_fingerprint, duplicate_of_experiment_id (self-FK),
  failure_info, timestamps.

`research_experiments.fingerprint` is indexed but **not** unique -
unlike `experiments.fingerprint` (Phase 2, genuinely one row per
backtest run), multiple `research_experiments` rows are expected to
share a fingerprint whenever deduplication kicks in (each duplicate gets
its own identity/row, per the brief: "do not unnecessarily rerun it,
reference the existing result" - it says reference, not "don't create a
row").

### Events and logging

New `EventType` members (additive, `app/core/events.py`):
`EXPERIMENT_CREATED`, `EXPERIMENT_FAILED`, `EXPERIMENT_SKIPPED_DUPLICATE`,
`CAMPAIGN_CREATED`, `CAMPAIGN_STARTED`, `CAMPAIGN_COMPLETED` (Phase 1
already had `EXPERIMENT_STARTED`/`EXPERIMENT_COMPLETED`, reused as-is).
Logging uses the existing `LogCategory.EXPERIMENT` (per-experiment
lifecycle) and `LogCategory.RESEARCH` (campaign-level) categories from
Phase 1 - no new logging framework. Every log call carries `system=...`,
`experiment_id=...`, and (where applicable) `campaign_id=...` via the
`extra=` dict, matching the brief's example exactly.

### Safety against overfitting (brief section 14)

No system here picks a "best" configuration, and none is even capable of
ranking results - `generate_experiments()` returns a plain list, and
`ExperimentRunner`/`CampaignRunner` never compare one experiment's
metrics to another's. Everything a future qualification system will need
is already preserved per experiment: parameters, rule configuration,
execution assumptions, data range, and (via `backtest_run_id`) the full
`BacktestResult` - trades, equity curve, and every Phase 2 metric.

## Phase 4 - AI Research Layer

`app/ai/` lets an AI agent run iterative research - propose experiments,
see their results, propose more - entirely through Phase 3's existing
`CampaignRunner`/`ExperimentRunner`. It is deliberately a thin layer:
reasoning and hypothesis-forming are the AI's job; generating,
validating, executing, and scoring experiments stays exactly where
Phases 2-3 put it.

```
AI Research Layer (app/ai/)
        v
ResearchRequest             <- Phase 3, unchanged
        v
CampaignRunner               <- Phase 3, unchanged
        v
ExperimentRunner               <- Phase 3, unchanged
        v
Deterministic Backtesting Engine <- Phase 2, unchanged
        v
BacktestResult / Experiment Result
        v
AI Research Layer (next iteration)
```

### Why `app/ai/` never touches `app/backtesting/` or `app/systems/`

Nothing in this phase modified either package - `git diff` for this
phase touches only `app/core/events.py` (additive `EventType` members)
and `app/database/schema.py` (additive migration 4), plus the new
`app/ai/` and `tests/ai/` trees. `app/ai/translation.py` builds Phase
3's own `ResearchRequest` subtypes and calls the matching
`ResearchSystem.generate_experiments()` unchanged; `app/ai/agent.py`
calls `CampaignRunner.run()` unchanged. `tests/ai/test_safety.py`
enforces this structurally (not just by convention): it parses every
file in `app/ai/` with `ast` and fails if anything imports or calls
`run_backtest` - AST-based specifically so the module docstrings
explaining this rule (which necessarily *mention* `run_backtest` in
prose) can't trip a naive substring check.

### Why the AI can't just hand over Python objects

A `ResearchRequest` needs live objects - a `CandleSeries`, a `Callable`
strategy factory - that an AI cannot produce as structured output. The
AI instead produces an `ExperimentProposal` (`app/ai/decision.py`): a
research-system name plus JSON-safe values (parameter lists, segment
specs, simple cost-model numbers). Anything that requires actual
Python logic - a rule variant's strategy factory, an execution variant's
`FeeModel`/`SlippageModel` instances - the AI can only select **by
name** from a `ResearchCatalog` (`app/ai/catalog.py`) that a human
assembled ahead of time. The AI can pick from a pre-approved menu; it
cannot write the menu.

`app/ai/translation.py::proposal_to_experiment_definitions()` is the
only place a proposal becomes real `ExperimentDefinition`s, always via
the unmodified Phase 3 request/system pair:

| `ExperimentProposal.research_system` | built request | source of "what varies" |
|---|---|---|
| `parameter_explorer` | `ParameterExplorerRequest` | `parameter_space: dict[str, list]` -> `ParameterSpace(ValueList(...))` |
| `rule_explorer` | `RuleExplorerRequest` | `rule_variant_names` -> looked up in `catalog.rule_variants` |
| `risk_execution` | `RiskExecutionRequest` | `execution_variant_names` -> looked up in `catalog.execution_variants` |
| `market_conditions` | `MarketConditionRequest` | `segment_specs` (`chronological_chunks`/`volatility`/`day_of_week`) -> `app.systems.market_conditions.segmentation` functions |
| `adversarial` | `AdversarialRequest` | `adversarial` dict (`worse_fee_rate`, `worse_slippage_bps`, `parameter_jitter`, `leave_out_chunk_count`) -> `AdversarialConfig` |

`market_conditions`'s `session` segmentation (time-of-day windows) is
NOT exposed to proposals - a UTC `datetime.time` pair isn't simply
JSON-safe the way the other three methods' parameters are; deferred
until there's an actual need, not built speculatively.

### Validation (brief section 16)

`app/ai/validation.py::validate_proposal()` runs BEFORE translation and
returns a plain list of error strings (empty = valid) - `ResearchAgent`
never repairs or guesses at a malformed proposal, it rejects it, logs
the specific errors, and counts it toward `max_failed_experiments`
(same budget as an experiment that failed for a real reason - a
research session that only ever produces invalid proposals should stop,
same as one whose experiments keep failing).

### Provider abstraction and the mock provider (brief section 5/17)

`AIProvider` (`app/ai/provider.py`) is one method: `invoke(request) ->
AIInvocationResponse`. No Claude/Anthropic/Freebuff/Ollama-specific code
exists anywhere in `app/ai/` - Phase 5+ can add a real provider without
touching `ResearchAgent`. `MockAIProvider` (`app/ai/providers/mock.py`)
is the only implementation this phase ships, following the same
"scripted by index" pattern as `ScriptedStrategy` (Phase 2) and the
`RuleVariant`/`ExecutionVariant` catalogs (Phase 3): `dict[int,
ResearchDecision]` keyed by iteration. It is a real deliverable, not
just a test double - it is the only way to actually run a
`ResearchAgent` session until a real provider exists.

### Structured decisions (brief section 6)

`ResearchDecision` (`app/ai/decision.py`) is the entire AI/agent
protocol - no free-form text is interpreted anywhere. It has no field
that could express "change my limits" (verified directly:
`tests/ai/test_safety.py::test_research_decision_has_no_way_to_carry_limits`
inspects its dataclass fields).

### Research context (brief section 11)

`build_research_context()` (`app/ai/context.py`) is deliberately bounded:
at most the last 10 experiments for this session (configurable), each
reduced to its key metrics (net profit, trade count, win rate, max
drawdown, profit factor, costs - via Phase 2's own
`load_experiment_metrics()`), never full trade lists, never the whole
database. `ResearchContext.summary()` is the only thing actually logged
to `ai_actions` (see below) - a further-bounded, human-readable string,
never the structured object or raw trade data.

### `ResearchAgent`'s loop and stopping (brief sections 7-9)

One iteration of `ResearchAgent.run()` (`app/ai/agent.py`):

1. Check limits (below) - stop first if any are already exceeded.
2. Build a `ResearchContext` from the current session state.
3. Invoke the provider; `AIProviderError` -> stop immediately with
   `PROVIDER_ERROR` (a session whose AI can't be reached cannot
   meaningfully continue - see "Session status" below).
4. Persist the `ResearchDecision`, emit `RESEARCH_DECISION_CREATED`.
5. Validate + translate each `ExperimentProposal` -> `ExperimentDefinition`s;
   invalid ones count toward `max_failed_experiments` and are skipped.
6. Submit everything from this iteration as ONE `CampaignRunner.run()`
   call (so a decision maps to exactly one campaign), trimmed to
   whatever's left of the `max_experiments` budget.
7. "Progress" = at least one experiment this iteration reached
   `COMPLETED` with `duplicate_of_experiment_id IS NULL` (i.e. a
   genuinely new result, not a dedup hit) - a simple, deterministic,
   auditable definition, not sentiment analysis on the AI's own text.
8. If the AI's decision carried a `stopping_reason`, honor it - AFTER
   this iteration's experiments already ran, never instead of them.

The AI request to stop is honored (Phase 4 brief: nothing says the AI
can't stop itself early) but it can only ever shorten a session, never
lengthen one past `ResearchLimits` - there is no code path from
`ResearchDecision` back into `ResearchLimits` at all (see "Safety
boundaries" below).

### Human-controlled limits (brief section 8)

`ResearchLimits` (`app/ai/limits.py`) is a frozen dataclass
(`max_iterations=10`, `max_experiments=50`, `max_failed_experiments=5`,
`max_consecutive_no_progress=3` by default). `ResearchAgent` takes one
by constructor argument and only ever reads it - nowhere in `app/ai/`
is a `ResearchLimits` constructed from AI output (verified: `tests/ai/
test_safety.py::test_agent_never_constructs_researchlimits_from_ai_output`
greps `agent.py` for a bare `ResearchLimits(` call and finds none).

### Session status: COMPLETED vs FAILED

A session that stops for any reason EXCEPT a provider error is marked
`COMPLETED` - hitting `max_iterations`, `max_experiments`,
`max_failed_experiments`, or `max_consecutive_no_progress`, or the AI
asking to stop, are all normal, successful endings of a bounded research
process. Only `PROVIDER_ERROR` marks a session `FAILED` - the session
couldn't continue for a reason outside the research logic itself.

### Persistence and resumability (brief section 12)

Three new tables (migration 4, `app/database/schema.py`):

- `ai_research_sessions` - objective, status, iteration, the four limit
  values (denormalized onto the row for easy inspection), running
  counters (`experiments_run`/`experiments_failed`/
  `consecutive_no_progress`), stopping reason, provider/model, timestamps.
- `ai_research_decisions` - one row per iteration: hypothesis, reasoning
  summary, the full `ExperimentProposal` list (JSON), analysis tasks,
  stopping reason, confidence.
- `ai_research_session_campaigns` - links each iteration's `research_
  campaigns` row (Phase 3) to the session, so "which experiments did
  this session run" is reconstructable via a join (`app.ai.persistence.
  list_session_experiments()`).

AI invocation audit logging (brief section 13) reuses Phase 1's
existing `ai_actions` table rather than adding a fourth - its columns
(`provider`, `action_type`, `related_id`, `prompt_summary`,
`result_summary`, `metadata`) already match what section 13 asks for.
`prompt_summary`/`result_summary` are always the bounded
`ResearchContext.summary()`/`AIInvocationResponse.raw_summary` strings,
never a raw prompt/response dump.

Because every field that matters is written to SQLite as it changes
(not accumulated in memory and flushed at the end), a session's state
can be inspected or reconstructed at any point via `app.ai.persistence`
- the mechanism, not a separately-implemented "resume" code path, is
what makes a session survive interruption within this phase's scope.

### Safety boundaries (brief section 15)

Concretely, not just by policy:

- **Can't bypass `CampaignRunner`.** No file in `app/ai/` imports or
  calls `run_backtest` (AST-verified, see above).
- **Can't expand its own budget.** `ResearchDecision` has no field for
  limits; `ResearchLimits` is frozen; nothing constructs one from AI
  output (all three verified in `tests/ai/test_safety.py`).
- **Can't delete anything.** No file in `app/ai/` contains a `DELETE
  FROM` statement (grepped) - there is no delete method anywhere in the
  package, structurally, not just by discipline.
- **Can't modify Phase 1-3 code or global config, install software, touch
  Git, or run arbitrary shell commands** - trivially true: nothing in
  `app/ai/` does any of these things; it only reads context, calls an
  `AIProvider`, and calls `CampaignRunner`.
- **Can't reach live trading/exchange systems** - none exist in this
  codebase at all yet, and `tests/ai/test_safety.py` greps for common
  markers (`place_order`, `live_trading`, `broker`, ...) as a tripwire
  for if one is ever added carelessly near this package.
- **Can't alter a `BacktestResult` or historical data** - the AI only
  ever *reads* metrics through `ResearchContext`; nothing in `app/ai/`
  writes to `trades`, `experiment_results`, or `experiments`
  (`tests/ai/test_integration.py::test_ai_analysis_never_alters_
  backtest_results` checks a prior run's `trades` rows are byte-identical
  after a second, unrelated session runs).

### Concurrency and determinism (brief sections 11/19)

`ResearchAgent.run()` executes one session sequentially - the AI itself
may be nondeterministic against a real provider, but everything
downstream of a `ResearchDecision` (validation, translation,
fingerprinting, execution, persistence) is exactly Phase 2/3's existing
deterministic code, unmodified. "AI-generated experiment configurations
must be normalized before fingerprinting" is satisfied structurally,
not by a separate normalization step: a proposal becomes a real
`ResearchRequest` and flows through Phase 3's `generate_experiments()`
+ Phase 2's `compute_fingerprint()`/`compute_experiment_fingerprint()`
exactly as if a human had typed the equivalent request by hand - there
is no AI-specific fingerprinting code path to diverge.

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
- **The AI research layer was built at `app/ai/`, not `app/agents/`.**
  Phase 1's ARCHITECTURE.md originally earmarked `app/agents/` for it;
  the Phase 4 brief explicitly allowed `app/ai/` "or another clearly
  separated package if the existing architecture suggests a better
  location," and `app/ai/` was chosen as the clearer, less overloaded
  name (an "agent" in this codebase could otherwise be confused with a
  Supervisor-restarted worker process). `app/agents/` remains an empty,
  unused placeholder - not deleted or repurposed, since removing an
  existing placeholder package wasn't asked for and a future phase may
  still want it for something else (e.g. non-research AI use, like
  Supervisor's AI-assisted diagnosis).

## Future expansion points

- **Strategy discovery/qualification** (`app/research/` - still an empty
  placeholder; not the same thing as `app/systems/`, which now holds the
  five research systems themselves, see "Phase 3" above): turning a
  `Strategy` + a set of `ExperimentRecord`s into a qualification verdict
  (robust / not robust, pass / fail out-of-sample, ...) and finally a row
  in the `strategies` table. This is the "complete qualification system"
  Phase 3 explicitly deferred (its brief section 14) - `app/systems/` was
  built so nothing about it needs to change to support this: every
  `ExperimentRecord` already carries parameters, rule/execution
  configuration, data range, and a `backtest_run_id` pointing at the full
  `BacktestResult`.
- **Real AI providers** (`app/ai/providers/`): Phase 4 built the
  provider abstraction and `MockAIProvider` only. Claude/Freebuff/Ollama-
  backed providers, and switching between them, are Phase 5+ - see
  "Phase 4 - AI Research Layer" above. Adding one means implementing
  `AIProvider.invoke()`; nothing in `ResearchAgent` should need to change.
- **Strategy qualification consuming AI research sessions**: an
  `ai_research_sessions` row plus its linked `research_experiments`
  already carries everything a qualification system (see "Strategy
  discovery/qualification" above) would want to know about how a
  strategy was investigated, not just what its best result was.
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
