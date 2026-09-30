"""Structural safety checks (Phase 4 brief section 15/20). Some of these
are source-level checks rather than behavioral ones: the safety property
being verified is "there is no code path", which a runtime test can't
prove by calling APIs - grepping the actual shipped source is the
correct tool here, not a weaker one.
"""

from __future__ import annotations

import ast
import dataclasses
import pathlib

import pytest

import app.ai as ai_package
from app.ai.decision import ResearchDecision
from app.ai.limits import ResearchLimits

AI_PACKAGE_DIR = pathlib.Path(ai_package.__file__).parent


def _all_ai_source() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in AI_PACKAGE_DIR.rglob("*.py"))


def _uses_run_backtest(path: pathlib.Path) -> bool:
    """AST-based, not a substring search: module docstrings legitimately
    explain (in prose) that this package must never call `run_backtest`,
    which would false-positive a naive `"run_backtest" not in source`
    check. Parsing means comments/docstrings (not part of the AST as
    statements) can never trigger this - only a real import or call can.

    Deliberately narrow to the name `run_backtest` itself - importing
    other names FROM `app.backtesting.engine` (e.g. `BacktestConfig`,
    which is legitimately defined there) is fine and expected.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if any(a.name == "run_backtest" for a in node.names):
                return True
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "run_backtest":
                return True
            if isinstance(func, ast.Attribute) and func.attr == "run_backtest":
                return True
    return False


def test_ai_package_never_imports_or_calls_run_backtest_directly() -> None:
    offenders = [p for p in AI_PACKAGE_DIR.rglob("*.py") if _uses_run_backtest(p)]
    assert offenders == [], (
        "app/ai must submit experiments through CampaignRunner/ExperimentRunner only - "
        f"these files import or call run_backtest directly: {offenders}"
    )


def test_ai_package_never_deletes_database_rows() -> None:
    source = _all_ai_source()
    assert "DELETE FROM" not in source.upper()


def test_research_limits_is_frozen() -> None:
    limits = ResearchLimits()
    with pytest.raises(dataclasses.FrozenInstanceError):
        limits.max_iterations = 999  # type: ignore[misc]


def test_research_decision_has_no_way_to_carry_limits() -> None:
    # The AI's output type structurally cannot express "change my own
    # budget" - there is no field for it, so no provider response can
    # ever be interpreted as new limits.
    decision_fields = {f.name for f in dataclasses.fields(ResearchDecision)}
    assert not (decision_fields & {"limits", "max_iterations", "max_experiments", "research_limits"})


def test_agent_never_constructs_researchlimits_from_ai_output() -> None:
    agent_source = (AI_PACKAGE_DIR / "agent.py").read_text(encoding="utf-8")
    # ResearchLimits() with no args only ever appears in this assertion's
    # own string, never in agent.py - the agent must only ever receive an
    # already-built ResearchLimits via its constructor.
    assert "ResearchLimits(" not in agent_source


def test_ai_package_has_no_live_trading_or_exchange_code() -> None:
    source = _all_ai_source().lower()
    for forbidden in ("place_order", "live_trading", "exchange_api", "binance", "broker"):
        assert forbidden not in source
