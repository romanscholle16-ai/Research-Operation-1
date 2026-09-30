# Strategy Research Lab

A local, autonomous trading-strategy research laboratory. Runs on Windows,
Python 3.12+, entirely self-contained inside this project folder.

**Current phase:** Phase 2 - Deterministic Backtesting Engine.
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

## Testing

```powershell
.venv\Scripts\python.exe -m pytest -v
```

## Project layout

```
app/            Application code: core, config, database, logging, state,
                backtesting (deterministic engine - see ARCHITECTURE.md),
                and placeholder packages for future phases: api, dashboard,
                supervisor, research, systems, agents
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
