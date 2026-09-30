# Current Task

**Phase 2 - Deterministic Backtesting Engine: COMPLETE.**

No task is currently in progress. Per the Phase 2 brief, work stopped
after the phase completion report; Phase 3 has not been started and its
exact scope has not been defined by the human yet.

## Before starting Phase 3

Whoever (human or AI) picks this up next should:

1. Read PROJECT_STATE.md (what exists today) and ARCHITECTURE.md's
   "Phase 2 - Deterministic Backtesting Engine" section (why it's shaped
   this way, including the order-model simplifications and the gross/net
   P&L bug that was caught and fixed) in full first.
2. Get explicit human direction on Phase 3 scope. Candidates per the
   Phase 1/2 briefs' future-architecture sections: the five research
   systems (Parameter Explorer, Rule/Logic Explorer, Risk/Execution
   Optimizer, Market-Condition Tester, Adversarial/Research System), the
   AI research layer, the Supervisor Agent, or the dashboard - the briefs
   do not say which comes first.
3. Not silently resolve ambiguity - the user's stated working style
   (see project memory) is to have ambiguities returned to them rather
   than guessed at.
4. Run `pytest -v` before making changes, to confirm the current baseline
   (89 tests: 30 foundation + 59 backtesting) still passes.

## Known simplifications a Phase 3 research system will run into

See ARCHITECTURE.md "Order model simplifications" for the full list and
rationale. In short: one open position per symbol at a time (no
scaling/reversal in a single order), LIMIT orders don't rest past the
next candle, no leverage/margin, and the engine is currently invoked
directly (`app.backtesting.run_backtest`) rather than through
`Application`'s lifecycle. None of these block a first research system,
but a system that needs one of them should extend the engine rather than
work around it from outside.

## Requirements every future phase inherits from Phase 1 & 2

- Self-contained inside `C:\StrategyResearchLab` - no global installs, no
  machine-specific paths.
- All new persistent facts go through the existing `EventRecorder`
  (`app/core/events.py`) and `StateManager` (`app/state/state_manager.py`)
  rather than ad hoc files, so the dashboard has one place to read from.
- AI-provider independence: new code must not hardcode a dependency on
  Claude/Anthropic specifically; use `Settings.ai_provider` and treat the
  active provider as a string key.
- **The deterministic backtesting engine (`app/backtesting/`) computes
  all financial numbers; AI never does.** This is no longer aspirational
  - the engine exists and is tested. A Phase 3 research/AI system should
  call `run_backtest()` and read its `BacktestResult`, never recompute
  P&L/metrics itself.
- Update PROJECT_STATE.md, ARCHITECTURE.md, and PHASE_HISTORY.md at the
  end of the phase, the same way Phases 1 and 2 did.
