# Current Task

**Phase 4 - AI Research Layer: COMPLETE.**

No task is currently in progress. Per the Phase 4 brief, work stopped
after the phase completion report; Phase 5 has not been started and its
exact scope has not been defined by the human yet.

## Before starting Phase 5

Whoever (human or AI) picks this up next should:

1. Read PROJECT_STATE.md and ARCHITECTURE.md's "Phase 4 - AI Research
   Layer" section (why it's shaped this way, including the `app/ai/` vs
   `app/agents/` naming decision and the AST-based safety-check gotcha)
   in full first.
2. Get explicit human direction on Phase 5 scope. Candidates per the
   Phase 1-4 briefs' future-architecture sections: a real AI provider
   (Claude/Freebuff/Ollama) behind the existing `AIProvider` interface,
   strategy discovery/qualification (`app/research/`), the Supervisor
   Agent (`app/supervisor/`), or the dashboard (`app/dashboard/` +
   `app/api/`) - the briefs do not say which comes first.
3. Not silently resolve ambiguity - the user's stated working style
   (see project memory) is to have ambiguities returned to them rather
   than guessed at.
4. Run `pytest -v` before making changes, to confirm the current
   baseline (221 tests: 30 foundation + 59 backtesting + 66 research
   systems + 66 AI layer) still passes.

## Known gaps a Phase 5 system will run into

- **No real AI provider exists.** `MockAIProvider` is the only
  `AIProvider` implementation. Adding a real one means implementing
  `AIProvider.invoke()` (`app/ai/provider.py`) - `ResearchAgent` should
  not need to change at all.
- **`market_conditions`'s "session" (time-of-day window) segmentation
  isn't reachable through an `ExperimentProposal`** - `time` objects
  aren't simply JSON-safe the way the other three segmentation methods'
  parameters are. The other Phase 3 systems still support it when called
  directly; only the AI-proposal path is missing it.
- **`ResearchAgent`/`CampaignRunner` both run sequentially**, called
  directly from Python - neither is wired into `Application`'s lifecycle
  or a CLI/scheduler yet.
- **`strategies` table is still empty.** Every experiment and research
  session records `strategy_name`/`strategy_version` as plain strings.
- **No qualification/comparison logic exists.** An `ai_research_sessions`
  row plus its linked `research_experiments` already carries everything
  needed (see ARCHITECTURE.md "Safety against overfitting" and "Future
  expansion points"), but nothing compares results or judges robustness
  yet.

## Requirements every future phase inherits from Phases 1-4

- Self-contained inside `C:\StrategyResearchLab` - no global installs, no
  machine-specific paths.
- All new persistent facts go through the existing `EventRecorder`
  (`app/core/events.py`) and `StateManager` (`app/state/state_manager.py`)
  rather than ad hoc files, so the dashboard has one place to read from.
- AI-provider independence: new code must not hardcode a dependency on
  Claude/Anthropic specifically; implement `AIProvider` (`app/ai/
  provider.py`) rather than special-casing a vendor inside `ResearchAgent`.
- **The deterministic backtesting engine (`app/backtesting/`) computes
  all financial numbers; AI never does.** A real AI provider should slot
  into the existing `AIProvider` interface and read `BacktestResult`
  data through `ResearchContext`, never recompute it.
- **Research systems (`app/systems/`) only ever produce
  `ExperimentDefinition`s and call `ExperimentRunner`/`CampaignRunner`.**
  The AI layer (`app/ai/`) only ever produces `ExperimentProposal`s and
  calls `CampaignRunner` - neither layer calls `run_backtest()` directly.
  A Phase 5 system should preserve this: propose through the existing
  layers, don't bypass them.
- Update PROJECT_STATE.md, ARCHITECTURE.md, and PHASE_HISTORY.md at the
  end of the phase, the same way Phases 1-4 did.
