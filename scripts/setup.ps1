# Sets up the project on a fresh Windows machine: creates the project-local
# virtual environment and installs dependencies into it. Nothing is
# installed outside C:\StrategyResearchLab (or wherever this checkout lives).

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment at .venv ..."
    python -m venv .venv
}

Write-Host "Upgrading pip ..."
& ".venv\Scripts\python.exe" -m pip install --upgrade pip

Write-Host "Installing project (with dev dependencies) ..."
& ".venv\Scripts\python.exe" -m pip install -e ".[dev]"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example - edit it to add any secrets."
}

Write-Host "Done. Activate with: .venv\Scripts\Activate.ps1"
