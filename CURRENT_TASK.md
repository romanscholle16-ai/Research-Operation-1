# Current Task

**Phase 1 - Foundation, Architecture & Project State: COMPLETE.**

No task is currently in progress. Per the Phase 1 brief, work stopped
after the phase completion report; Phase 2 has not been started and its
exact scope has not been defined by the human yet.

## Before starting Phase 2

Whoever (human or AI) picks this up next should:

1. Read PROJECT_STATE.md (what exists today) and ARCHITECTURE.md (why it's
   shaped this way) in full first.
2. Get explicit human direction on Phase 2 scope. The original brief's
   "Future Architecture Requirements" section (now summarized in
   ARCHITECTURE.md's "Future expansion points") sketches the five research
   systems, the AI research layer, the Supervisor Agent, and the
   dashboard, but does not say which one comes first.
3. Not silently resolve ambiguity - the user's stated working style
   (see project memory) is to have ambiguities returned to them rather
   than guessed at.
4. Run `pytest -v` before making changes, to confirm the Phase 1 baseline
   (30 tests) still passes in the current environment.

## Requirements every future phase inherits from Phase 1

- Self-contained inside `C:\StrategyResearchLab` - no global installs, no
  machine-specific paths (see ARCHITECTURE.md, "Goals driving the
  design").
- All new persistent facts go through the existing `EventRecorder`
  (`app/core/events.py`) and `StateManager` (`app/state/state_manager.py`)
  rather than ad hoc files, so the dashboard has one place to read from.
- AI-provider independence: new code must not hardcode a dependency on
  Claude/Anthropic specifically; use `Settings.ai_provider` and treat the
  active provider as a string key.
- The deterministic backtesting engine (once built) computes all
  financial numbers; AI never does.
- Update PROJECT_STATE.md, ARCHITECTURE.md, and PHASE_HISTORY.md at the
  end of the phase, the same way Phase 1 did.
