# Current Task

**Phase 6 - Internet & Strategy Research Layer: COMPLETE.**

No task is currently in progress. Per the Phase 6 brief, work stopped
after the phase completion report; Phase 7 has not been started and its
exact scope has not been defined by the human yet.

## Before starting Phase 7

Whoever (human or AI) picks this up next should:

1. Read PROJECT_STATE.md and ARCHITECTURE.md's "Phase 6 - Internet &
   Strategy Research Layer" section (why it's shaped this way, including
   the `app/research/` naming reassignment and the four real bugs caught
   and fixed) in full first.
2. Get explicit human direction on Phase 7 scope. Candidates per the
   Phase 1-6 briefs' future-architecture sections: strategy qualification
   (home no longer `app/research/` - see "Documented deviations"; needs
   a new name when scoped), the Supervisor Agent (`app/supervisor/`), the
   dashboard (`app/dashboard/` + `app/api/`), a real source-discovery
   backend, or a working Freebuff/Ollama AI provider - the briefs do not
   say which comes first.
3. Not silently resolve ambiguity - the user's stated working style
   (see project memory) is to have ambiguities returned to them rather
   than guessed at.
4. Run `pytest -v` before making changes, to confirm the current
   baseline (409 tests: 30 foundation + 59 backtesting + 66 research
   systems + 66 AI layer + 69 AI providers + 119 internet research)
   still passes.

## Known gaps a Phase 7 system will run into

- **No real source-discovery backend.** `ManualSourceDiscoveryProvider`
  structures a human-curated URL list; nothing searches the internet
  itself. A real one needs a search API key not available this phase.
- **PDF text extraction doesn't exist** - stdlib has no PDF parser, and
  one wasn't added without being asked. PDFs are tracked (hashed,
  cached) but produce no evidence.
- **`adapter.py`'s interpreter covers a narrow subset**: close/open/
  high/low/volume + EMA/SMA, comparison/logical/crossing operators,
  percent-based stop/target. Anything else (a structural stop placement,
  another indicator) comes back `adaptable=False` with specific reasons -
  extend `adapter.py` deliberately, don't work around it.
- **No AI-authored rule is ever `EXPLICIT`**, only `INTERPRETED` -
  there is no deterministic quote-to-structure mapper in this codebase.
  A future phase wanting that is building something new, not extending
  what's here.
- **`WebResearchAgent`/`ResearchAgent`/`CampaignRunner` all run
  sequentially**, called directly from Python - none are wired into
  `Application`'s lifecycle or a CLI/scheduler yet.
- **No real AI provider has ever actually been called** (carried over
  from Phase 5) - `ClaudeAIProvider`/`OllamaAIProvider` are tested only
  against mocked HTTP.
- **`strategies` table is still empty**; nothing qualifies a strategy yet.

## Requirements every future phase inherits from Phases 1-6

- Self-contained inside `C:\StrategyResearchLab` - no global installs, no
  machine-specific paths. Prefer the standard library over a new
  dependency when the functionality fits (Phases 5 and 6 both added zero
  new dependencies this way).
- All new persistent facts go through the existing `EventRecorder`
  (`app/core/events.py`) and `StateManager` (`app/state/state_manager.py`).
- AI-provider independence: implement `AIProvider` (`app/ai/provider.py`)
  for any new backend/workflow - `app/research/` reused it unchanged
  rather than inventing a parallel abstraction; do the same.
- **The deterministic backtesting engine (`app/backtesting/`) computes
  all financial numbers; AI never does.**
- **Research systems (`app/systems/`) only ever produce
  `ExperimentDefinition`s; the AI layer (`app/ai/`) only ever produces
  `ExperimentProposal`s; the internet research layer (`app/research/`)
  only ever produces `StrategySpecification`s** - none of the three call
  `run_backtest()` directly (AST-verified in each package's own
  `test_safety.py`/`test_security.py`). A `StrategySpecification` only
  ever becomes a `Strategy` through `adapter.py`'s safe, fixed
  interpreter - never through generated/executed code.
- Never let untrusted input (web content, AI output) carry authority by
  convention alone - prefer a closed schema/enum that structurally
  cannot express a dangerous action over a prompt that merely asks the
  model not to do it. `WebResearchDecision`'s `ResearchAction` enum is
  the Phase 6 example; keep doing this.
- Do not pretend something works if it was only built, not tested - say
  so explicitly in the completion report, the way Freebuff, the real AI
  providers, PDF extraction, and search-engine discovery were all called
  out this way.
- Update PROJECT_STATE.md, ARCHITECTURE.md, and PHASE_HISTORY.md at the
  end of the phase, the same way Phases 1-6 did.
