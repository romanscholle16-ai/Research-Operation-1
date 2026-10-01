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

## Phase 4 - AI Research Layer

**Completed:** 2026-09-29
**Status:** Complete

### Starting point

Phase 1-3 baseline (155 tests) re-verified green before any change.
`app/ai/` did not exist; `app/agents/` was (and remains) an empty
placeholder. No changes were made to `app/backtesting/` or
`app/systems/` - only additive database/event extensions elsewhere.

### What was built

An AI research layer (`app/ai/`, 12 modules, 66 new tests in
`tests/ai/`) implementing the Objective -> Hypothesis -> Experiment ->
Backtest -> Result -> Analysis -> next Hypothesis loop from a
provider-agnostic `AIProvider` interface (`MockAIProvider` the only
implementation this phase ships), typed/validated AI output
(`ResearchDecision`/`ExperimentProposal`), a `ResearchCatalog` the AI
can select named rule/execution variants from but never author, a
bounded `ResearchContext` builder, deterministic proposal validation and
translation into Phase 3's own `ResearchRequest` types (zero
duplication of the Phase 3 experiment model), a `ResearchAgent` bounded
by a frozen, human-supplied `ResearchLimits`, three new database tables
(migration 4), and eight new `EventType` members. Full design writeup:
ARCHITECTURE.md "Phase 4 - AI Research Layer".

### Key decisions

- **Built at `app/ai/`, not the Phase-1-earmarked `app/agents/`.** The
  Phase 4 brief explicitly allowed either; `app/ai/` was chosen as
  clearer and less overloaded ("agent" already means something
  different elsewhere in this codebase - a Supervisor-managed worker
  process). `app/agents/` was left untouched rather than deleted or
  repurposed, since that wasn't asked for.
- **The AI never produces `ResearchRequest`s or `ExperimentDefinition`s
  directly - only `ExperimentProposal`s, translated by deterministic
  code.** A `ResearchRequest` needs live Python objects (a
  `CandleSeries`, a `Callable` strategy factory) that structured AI
  output cannot carry. Anything requiring real logic (a rule variant's
  strategy factory, an execution variant's cost-model instances) the AI
  can only select **by name** from a human-assembled `ResearchCatalog` -
  it has a menu, not a pen. `app/ai/translation.py` then builds the
  exact same Phase 3 request/system pair a human would, so
  fingerprinting/deduplication/execution never diverge by who produced
  the request (the brief's "AI-generated experiment configurations must
  be normalized before fingerprinting" - satisfied structurally, not by
  a separate normalization step).
- **A session is `COMPLETED` unless it stopped on `PROVIDER_ERROR`,
  which is `FAILED`.** Hitting any of the four limits, or the AI asking
  to stop, are all normal, successful endings of a bounded process;
  only an unreachable/broken AI provider represents an actual failure
  to complete the work.
- **"Progress" is defined as "at least one experiment this iteration
  reached `COMPLETED` with no `duplicate_of_experiment_id`"** - simple,
  deterministic, and auditable, deliberately not an attempt to have the
  agent judge its own research quality (that judgment - qualification -
  is explicitly out of scope, per the brief's section 9: the AI reasons
  about robustness across many metrics, it does not optimize one).
- **`ResearchLimits` is a frozen dataclass passed once by the caller;
  nothing in `app/ai/` ever constructs one from AI output, and
  `ResearchDecision` has no field that could express new limits at all.**
  This is what makes "the AI cannot expand its own research budget" true
  by construction rather than by convention - verified directly in
  `tests/ai/test_safety.py` (frozen-ness, absent fields, and an
  `agent.py`-source grep for a bare `ResearchLimits(` call).
- **AI invocation audit logging reuses Phase 1's `ai_actions` table**
  rather than adding a fourth new one - its columns already matched the
  brief's section 13 requirements exactly, and `prompt_summary`/
  `result_summary` are always the already-bounded
  `ResearchContext.summary()`/`AIInvocationResponse.raw_summary`
  strings, never a raw dump.
- **The "AI cannot bypass `CampaignRunner`" safety test is AST-based,
  not a substring search.** A naive `"run_backtest" not in source` check
  over `app/ai/`'s files false-positived on the module docstrings
  themselves, which legitimately explain (in prose) that the package
  must never call `run_backtest` - the explanation mentions the
  forbidden word. Parsing with `ast` and checking only real `Call`/
  `ImportFrom` nodes fixed it without weakening what the check actually
  proves; `tests/ai/test_translation.py`'s companion check uses bytecode
  `co_names` introspection for the same reason.

### Verification performed

- `pytest -v`: 221/221 passed (155 from Phases 1-3 unchanged + 66 new),
  run before starting (baseline check) and after every module was wired
  together.
- Three manual end-to-end smoke tests via the real venv interpreter
  (outside pytest): (1) a full `ResearchAgent` session with
  `MockAIProvider` proposing a 2-value parameter sweep then stopping
  itself - confirmed decisions/campaigns/experiments/events all
  persisted and linked correctly on the first attempt; (2) an
  `AlwaysFailingAIProvider` session - confirmed `FAILED` status,
  `provider_error` stopping reason, zero iterations attempted; (3) a
  `max_iterations=3` session with a provider that never requests a stop
  - confirmed the agent stopped after exactly 3 provider invocations,
  never a 4th.

### Deferred to later phases

Everything in the Phase 4 brief's "DO NOT IMPLEMENT YET" section: real
Claude/Freebuff/Ollama provider integration, automatic provider
switching, browser automation, internet strategy discovery, autonomous
strategy discovery, strategy qualification, Monte Carlo, ML regime
detection, live trading, exchange APIs, large historical data downloads,
the professional dashboard, a Windows `.exe`, the Supervisor Agent, 24/7
autonomous operation, Windows services, distributed workers, and
sophisticated multi-agent systems. Also not built (future scope, not
prohibited): wiring `ResearchAgent` into `Application`'s lifecycle or a
CLI/scheduler, and the `market_conditions` "session" (time-of-day
window) segmentation method for AI proposals specifically (not simply
JSON-safe the way the other three segmentation methods are - the other
Phase 3 systems still support it when called directly, just not yet
through an `ExperimentProposal`).

## Phase 5 - Real AI Providers + Provider Portability

**Completed:** 2026-09-30
**Status:** Complete

### Starting point

Phase 1-4 baseline (221 tests) re-verified green before any change.
Environment checked directly (not assumed) for real-provider
credentials/servers: no `ANTHROPIC_API_KEY`, no `FREEBUFF_API_KEY`, no
`.env` file, and no Ollama server reachable at the default
`localhost:11434` - all confirmed absent before writing any provider
code, which shaped what could honestly be tested (see "Verification
performed" below).

### What was built

Real `AIProvider` adapters behind Phase 4's unchanged interface:
`ClaudeAIProvider` (Anthropic Messages API via stdlib `urllib`, forced
tool-use for structured output) and `OllamaAIProvider` (local Ollama
`/api/chat` via the same stdlib approach), plus `FreebuffAIProvider`, an
explicit structural placeholder. A shared strict JSON parser
(`structured_output.py`) is the one path from any provider's raw output
to a `ResearchDecision`. A new `AIProviderRouter` implements `AIProvider`
itself and selects/falls back between providers by configuration,
reusing and extending Phase 1's `Settings.ai_provider`. Three new error
subclasses, a `ProviderCapabilities` model, usage/cost/id tracking on
`AIInvocationResponse`, a shared `RESEARCH_POLICY` prompt, and a secret-
redaction helper round out the picture. 69 new tests in `tests/ai/`
(290 total). Full design writeup: ARCHITECTURE.md "Phase 5 - Real AI
Providers + Provider Portability".

### Key decisions

- **No new dependency - both real adapters use stdlib `urllib.request`**,
  not the `anthropic` package or an Ollama client library. Both target
  APIs are documented, stable JSON-over-HTTPS/HTTP contracts well within
  stdlib's reach, and this project has stated a "no unnecessary
  dependencies" preference since Phase 1. `pyproject.toml` is unchanged.
- **Freebuff was built as an honest placeholder, not a guess.** No
  verified API contract (base URL, auth scheme, request/response shape)
  was available. The brief was explicit that improvising one was worse
  than not building it - a wrong guess could silently call the wrong
  thing in the wrong shape and look "done" while being completely
  disconnected from reality. `FreebuffAIProvider` is a real
  `AIProvider` subclass (proving the interface doesn't need to change
  for a real one later) whose `invoke()` always raises, explaining
  exactly what's missing.
- **Ollama was not installed.** It is ordinary desktop software with its
  own system installer; installing it would mean adding something
  outside the project's self-contained `.venv` without being asked.
  `OllamaAIProvider`'s code exists and is unit-tested against a mocked
  transport, including one test that makes a REAL call against the
  confirmed-absent default endpoint to prove the "unavailable" path
  without faking it.
- **One shared JSON parser for every provider, not one per vendor.**
  `structured_output.py::research_decision_from_dict()` is strict:
  a missing/wrong-typed required field raises immediately rather than
  being defaulted or guessed at, per the brief's "do not silently 'fix'
  invalid AI instructions when doing so could alter intent or safety."
  Both real adapters extract their vendor's raw dict (Claude: a forced
  tool-use block's `input`; Ollama: `json.loads()` of `message.content`)
  and hand it to the exact same function.
- **`AIProviderRouter` implements `AIProvider` itself**, rather than
  being a separate concept `ResearchAgent` would need to know about -
  this is what makes "ResearchAgent must not need to know which provider
  is being used" literally true: it receives a router exactly as it
  would receive any single provider.
- **Mock-as-primary is unrestricted; mock-as-fallback requires an
  explicit flag.** `AIProviderRouter` only gates chain positions after
  the first - deliberately choosing mock as your provider is
  unambiguous configuration, but a REAL provider silently degrading to
  mock on failure would let a "real" research session look successful
  while running on fake data. `AI_ALLOW_MOCK_FALLBACK` must be set
  explicitly for the latter to ever happen.
- **"claude" and "anthropic" both select the same provider.** The Phase
  5 brief's router example uses "claude"; Phase 1's `AI_ACTIVE_PROVIDER`
  convention (already shipped, already documented) used "anthropic" for
  the same vendor. Rather than picking one and quietly breaking
  compatibility with the other, `build_provider()` accepts both.
- **Provider usage/cost/diagnostics reuse Phase 1's `ai_actions` table**
  via its existing `metadata` JSON column - no new table, no new
  persistence code path. `ResearchAgent._invoke_provider()`'s control
  flow is unchanged from Phase 4; it now additionally times each call
  and forwards the response's usage/cost/id fields into that same
  `record_ai_action()` call.
- **No estimated cost is invented.** Anthropic's Messages API doesn't
  return a dollar figure and local inference has no per-call provider
  cost, so `estimated_cost` stays `None` for both real adapters, per the
  brief's explicit "store null rather than inventing a value."

### Verification performed

- `pytest -v`: 290/290 passed (221 from Phases 1-4 unchanged + 69 new),
  run before starting (baseline check) and after every module was wired
  together.
- Manual smoke tests via the real venv interpreter (outside pytest,
  mirroring the discipline from every prior phase): the router's
  primary/fallback/mock-gating logic; `ClaudeAIProvider` against a
  hand-built fake HTTP response (successful parse + token usage, then
  401/429/malformed-response cases, confirming the configured API key
  never appeared in a raised exception's message); `OllamaAIProvider`
  against the real, confirmed-absent `localhost:11434` (correctly raised
  `AIProviderUnavailableError`) and against a mocked successful
  response; a full `ResearchAgent` session driven by an
  `AIProviderRouter` wrapping `MockAIProvider`, confirming zero
  `ResearchAgent` code changes were needed for the router to work;
  `FreebuffAIProvider.invoke()` confirmed to raise with a clear
  explanation.
- Every automated test exercising `ClaudeAIProvider`/`OllamaAIProvider`
  mocks the HTTP transport (`_http_post_json`) rather than using real
  network access or credentials, per brief section 21/22 - no API key
  was required anywhere in the test suite.

### Deferred to later phases

Everything in the Phase 5 brief's "DO NOT ADD YET" section: browser
research, web scraping, internet strategy discovery, autonomous
strategy qualification, the dashboard, a Windows `.exe`, the Supervisor
Agent, 24/7 operation, live trading, exchange APIs, Monte Carlo, ML
regime detection, distributed execution, large historical data
downloads, and sophisticated multi-agent collaboration. Also not built
(future scope, explicitly flagged rather than faked): a working Freebuff
integration (no verified API contract), a real-provider smoke test (no
credentials available), and confirmation that `OllamaAIProvider` works
against an actual running Ollama server (none installed). `main.py`/
`Application` still do not construct or use a `ResearchAgent`/provider
of any kind - that wiring remains open for whichever future phase
actually needs the AI layer to run as part of the application lifecycle.
