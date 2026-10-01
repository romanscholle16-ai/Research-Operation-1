# Current Task

**Phase 5 - Real AI Providers + Provider Portability: COMPLETE.**

No task is currently in progress. Per the Phase 5 brief, work stopped
after the phase completion report; Phase 6 has not been started and its
exact scope has not been defined by the human yet.

## Before starting Phase 6

Whoever (human or AI) picks this up next should:

1. Read PROJECT_STATE.md and ARCHITECTURE.md's "Phase 5 - Real AI
   Providers + Provider Portability" section (why it's shaped this way,
   including the Freebuff-as-honest-placeholder decision and exactly
   what was and wasn't tested) in full first.
2. Get explicit human direction on Phase 6 scope. Candidates per the
   Phase 1-5 briefs' future-architecture sections: strategy discovery/
   qualification (`app/research/`), the Supervisor Agent
   (`app/supervisor/`), the dashboard (`app/dashboard/` + `app/api/`),
   or finishing Freebuff/testing against a real Ollama server - the
   briefs do not say which comes first.
3. Not silently resolve ambiguity - the user's stated working style
   (see project memory) is to have ambiguities returned to them rather
   than guessed at.
4. Run `pytest -v` before making changes, to confirm the current
   baseline (290 tests: 30 foundation + 59 backtesting + 66 research
   systems + 66 AI layer + 69 AI providers) still passes.

## Known gaps a Phase 6 system will run into

- **No real AI provider has ever actually been called.** `ClaudeAIProvider`
  and `OllamaAIProvider` are tested only against mocked HTTP. The first
  real session should start small: construct the provider directly, set
  conservative `ResearchLimits`, and watch it closely - see
  ARCHITECTURE.md "Phase 5 - Verification performed" for the exact
  env vars needed (`ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`) and what a
  minimal smoke test looks like.
- **Freebuff is not real.** `FreebuffAIProvider.invoke()` always raises.
  Completing it requires a verified Freebuff API contract (base URL,
  auth scheme, request/response shape) that was not available during
  Phase 5 - don't guess at one; get it from the human first.
- **Nothing in `Application`/`main.py` constructs a `ResearchAgent` or a
  provider.** `app/ai/router.py::build_router_from_settings()` exists
  and is config-driven, but nothing calls it outside tests/manual use.
- **`ResearchAgent`/`CampaignRunner` both still run sequentially**,
  called directly from Python.
- **`strategies` table is still empty**; research sessions still record
  `strategy_name`/`strategy_version` as plain strings.

## Requirements every future phase inherits from Phases 1-5

- Self-contained inside `C:\StrategyResearchLab` - no global installs, no
  machine-specific paths. Prefer the standard library over a new
  dependency when the functionality fits (Phase 5's real providers added
  zero new dependencies).
- All new persistent facts go through the existing `EventRecorder`
  (`app/core/events.py`) and `StateManager` (`app/state/state_manager.py`)
  rather than ad hoc files, so the dashboard has one place to read from.
- AI-provider independence: implement `AIProvider` (`app/ai/provider.py`)
  for any new backend; never special-case a vendor inside `ResearchAgent`
  or `AIProviderRouter`. Never hardcode or log a secret - route it
  through `Settings.ai_provider` and redact it the way `claude.py` does.
- **The deterministic backtesting engine (`app/backtesting/`) computes
  all financial numbers; AI never does.**
- **Research systems (`app/systems/`) only ever produce
  `ExperimentDefinition`s and call `ExperimentRunner`/`CampaignRunner`.
  The AI layer (`app/ai/`) only ever produces `ExperimentProposal`s and
  calls `CampaignRunner`** - neither layer calls `run_backtest()`
  directly, and this is AST-verified in `tests/ai/test_safety.py`, not
  just conventional.
- Do not pretend something works if it was only built, not tested - say
  so explicitly in the completion report (Freebuff and real-provider
  calls were called out this way in Phase 5; keep doing that).
- Update PROJECT_STATE.md, ARCHITECTURE.md, and PHASE_HISTORY.md at the
  end of the phase, the same way Phases 1-5 did.
