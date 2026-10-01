# Strategy Research Lab

A local, autonomous trading-strategy research laboratory. Runs on Windows,
Python 3.12+, entirely self-contained inside this project folder.

**Current phase:** Phase 6 - Internet & Strategy Research Layer.
See [CURRENT_TASK.md](CURRENT_TASK.md) for the active task,
[PROJECT_STATE.md](PROJECT_STATE.md) for what exists today, and
[ARCHITECTURE.md](ARCHITECTURE.md) for how it fits together.

## Setup (Windows)

```powershell
.\scripts\setup.ps1
```

This creates a project-local virtual environment at `.venv`, installs
dependencies into it, and copies `.env.example` to `.env` if one doesn't
exist yet. Nothing is installed outside this project folder.

Manual equivalent:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

## Running

```powershell
.venv\Scripts\python.exe main.py
```

Loads configuration, initializes logging/database/state, emits
`application_started` / `application_stopped` events, and exits. Phase 1
has no autonomous loop yet - later phases replace the body of
`Application.run()` (`app/core/app.py`) with a supervised long-running
loop.

## AI providers

`app/ai/` can run research sessions through a mock provider (no
credentials needed) or real ones. Select via `.env` (see
`.env.example`): `AI_ACTIVE_PROVIDER=mock|claude|ollama|freebuff`, with
optional `AI_PROVIDER_FALLBACK_CHAIN`/`AI_ALLOW_MOCK_FALLBACK`. Claude
needs `ANTHROPIC_API_KEY`; Ollama needs a server already running at
`OLLAMA_BASE_URL` (not installed by this project); Freebuff is currently
a placeholder only - see ARCHITECTURE.md "Phase 5" for what's untested
and why. No AI provider ever calculates financial results or bypasses
`CampaignRunner` - see `app/ai/policy.py` and ARCHITECTURE.md's safety
sections.

## Internet research

`app/research/` lets an AI agent discover and retrieve publicly
documented trading strategies and turn them into a structured,
auditable `StrategySpecification` - never into executable code. Source
retrieval is plain HTTP(S) only (stdlib `urllib`), respects
`robots.txt`, and never bypasses auth/paywalls/CAPTCHAs. Only a narrow,
explicitly-validated subset of a specification (EMA/SMA comparisons,
percent stop/target) can become a real, runnable strategy via
`app/research/adapter.py`'s safe interpreter - everything else is
reported as `INCOMPLETE`/`AMBIGUOUS`/`UNSUPPORTED`, never guessed at.
See ARCHITECTURE.md "Phase 6" for the full design and its safety
boundaries.

## Testing

```powershell
.venv\Scripts\python.exe -m pytest -v
```

## Project layout

```
app/            Application code: core, config, database, logging, state,
                backtesting (deterministic engine), systems (five research
                systems), ai (AI research layer), research (internet &
                strategy research layer - see ARCHITECTURE.md), and
                placeholder packages for future phases: api, dashboard,
                supervisor, agents
data/           raw / processed / cache (databases, checkpoints) - git-ignored content
strategies/     discovered / active / qualified / rejected - git-ignored content
results/        experiments / reports - git-ignored content
logs/           one subfolder per log category (JSONL) - git-ignored content
tests/          pytest suite
scripts/        setup and maintenance scripts
```

All data, logs, results, the database, and the virtual environment live
under this folder. See `.env.example` for configuration options; secrets
go in a local `.env` file, which is git-ignored.
