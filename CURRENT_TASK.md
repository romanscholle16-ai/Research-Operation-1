# Current Task

**Phase 3 - Five Independent Research Systems: COMPLETE.**

No task is currently in progress. Per the Phase 3 brief, work stopped
after the phase completion report; Phase 4 has not been started and its
exact scope has not been defined by the human yet.

## Before starting Phase 4

Whoever (human or AI) picks this up next should:

1. Read PROJECT_STATE.md and ARCHITECTURE.md's "Phase 3 - Five
   Independent Research Systems" section (why it's shaped this way,
   including the experiment lineage decision and the parameter-
   propagation bug that was caught and fixed) in full first.
2. Get explicit human direction on Phase 4 scope. Candidates per the
   Phase 1-3 briefs' future-architecture sections: strategy discovery/
   qualification (`app/research/`, still an empty placeholder - not to
   be confused with `app/systems/`, which now holds the five research
   systems), the AI research layer (`app/agents/`), the Supervisor Agent
   (`app/supervisor/`), or the dashboard (`app/dashboard/` +
   `app/api/`) - the briefs do not say which comes first.
3. Not silently resolve ambiguity - the user's stated working style
   (see project memory) is to have ambiguities returned to them rather
   than guessed at.
4. Run `pytest -v` before making changes, to confirm the current
   baseline (155 tests: 30 foundation + 59 backtesting + 66 research
   systems) still passes.

## Known gaps a Phase 4 system will run into

- **`strategies` table is still empty.** Every experiment so far records
  `strategy_name`/`strategy_version` as plain strings, not a real
  `strategies` row. A strategy-discovery phase needs to decide when a
  string identity becomes a first-class row (and what "discovered" vs
  "qualified" actually means operationally).
- **No qualification/comparison logic exists yet.** `app/systems/`
  generates and records experiments; nothing compares one experiment's
  `BacktestResult` to another's or judges robustness. Everything needed
  is already persisted (see ARCHITECTURE.md "Safety against
  overfitting"), but the comparison logic itself is unwritten.
- **`CampaignRunner` runs sequentially.** The architecture supports
  concurrent execution without a rewrite (see ARCHITECTURE.md
  "Concurrency foundation"), but nothing concurrent has been built or
  tested yet.
- **Research systems aren't wired into `Application`'s lifecycle** or any
  CLI/scheduler - they're called directly from Python today.

## Requirements every future phase inherits from Phases 1-3

- Self-contained inside `C:\StrategyResearchLab` - no global installs, no
  machine-specific paths.
- All new persistent facts go through the existing `EventRecorder`
  (`app/core/events.py`) and `StateManager` (`app/state/state_manager.py`)
  rather than ad hoc files, so the dashboard has one place to read from.
- AI-provider independence: new code must not hardcode a dependency on
  Claude/Anthropic specifically; use `Settings.ai_provider` and treat the
  active provider as a string key.
- **The deterministic backtesting engine (`app/backtesting/`) computes
  all financial numbers; AI never does.** A Phase 4 AI/qualification
  system should read `ExperimentRecord`/`BacktestResult` data, never
  recompute P&L/metrics itself.
- **Research systems (`app/systems/`) only ever produce
  `ExperimentDefinition`s and call `ExperimentRunner`/`CampaignRunner`.**
  A Phase 4 AI layer proposing experiments should build a
  `ResearchRequest` and submit it through the existing systems/runner,
  not call `run_backtest()` directly or reimplement experiment
  bookkeeping.
- Update PROJECT_STATE.md, ARCHITECTURE.md, and PHASE_HISTORY.md at the
  end of the phase, the same way Phases 1-3 did.
