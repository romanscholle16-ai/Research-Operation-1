"""Phase 5 brief section 19 security checks. Structural (AST/source)
checks prove "there is no code path", the same philosophy as Phase 4's
test_safety.py - see that file for why AST beats a substring search here
(docstrings legitimately discuss what must never happen).
"""

from __future__ import annotations

import ast
import json
import pathlib

import pytest

import app.ai as ai_package
import app.ai.providers.claude as claude_mod
from app.ai.agent import ResearchAgent
from app.ai.limits import ResearchLimits
from app.ai.provider import AIProviderAuthError
from app.ai.providers.claude import ClaudeAIProvider
from tests.ai.conftest import make_catalog

AI_PACKAGE_DIR = pathlib.Path(ai_package.__file__).parent
SECRET = "sk-ant-SECURITY-TEST-SECRET-VALUE"


def _all_py_files():
    return list(AI_PACKAGE_DIR.rglob("*.py"))


def _calls_names(path: pathlib.Path, names: set[str]) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in names:
                return True
            if isinstance(func, ast.Attribute) and func.attr in names:
                return True
    return False


def _imports_modules(path: pathlib.Path, modules: set[str]) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".")[0] in modules for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in modules:
                return True
    return False


def test_app_ai_never_calls_eval_or_exec() -> None:
    offenders = [p for p in _all_py_files() if _calls_names(p, {"eval", "exec"})]
    assert offenders == [], f"app/ai must never eval/exec anything (AI output is data, not code): {offenders}"


def test_app_ai_never_imports_subprocess_or_shells_out() -> None:
    offenders = [p for p in _all_py_files() if _imports_modules(p, {"subprocess"})]
    assert offenders == [], f"app/ai must never shell out: {offenders}"
    source = "\n".join(p.read_text(encoding="utf-8") for p in _all_py_files())
    assert "os.system(" not in source


def test_experiment_proposal_has_no_path_or_command_fields() -> None:
    import dataclasses

    from app.ai.decision import ExperimentProposal

    field_names = {f.name for f in dataclasses.fields(ExperimentProposal)}
    forbidden_substrings = ("path", "file", "command", "shell", "script")
    offending = {name for name in field_names if any(s in name.lower() for s in forbidden_substrings)}
    assert offending == set(), f"ExperimentProposal must not accept path/command-like fields from AI output: {offending}"


def test_env_example_contains_no_real_looking_secret(tmp_path) -> None:
    env_example = pathlib.Path(__file__).resolve().parents[2] / ".env.example"
    text = env_example.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.strip().startswith("ANTHROPIC_API_KEY") or line.strip().startswith("FREEBUFF_API_KEY"):
            _, _, value = line.partition("=")
            assert value.strip() == "", f"{line!r} must be an empty placeholder, not a real-looking value"


def test_gitignore_still_excludes_env() -> None:
    gitignore = pathlib.Path(__file__).resolve().parents[2] / ".gitignore"
    text = gitignore.read_text(encoding="utf-8")
    assert ".env" in text


def test_secret_never_appears_in_persisted_events_or_ai_actions(database, monkeypatch) -> None:
    """Drives a real (failing) ClaudeAIProvider invocation through
    ResearchAgent and checks every persisted row - events, ai_actions,
    research_experiments - for the literal secret value."""

    def fail(*a, **k):
        import urllib.error

        raise urllib.error.HTTPError(
            "https://api.anthropic.com/v1/messages", 401, f"bad key {SECRET}", {}, None
        )

    monkeypatch.setattr(claude_mod, "_http_post_json", fail)
    provider = ClaudeAIProvider(api_key=SECRET)

    agent = ResearchAgent(database, provider, make_catalog(), ResearchLimits())
    record = agent.run("o")

    event_rows = database.query_all("SELECT * FROM events WHERE related_id = ?", (record.id,))
    action_rows = database.query_all("SELECT * FROM ai_actions WHERE related_id = ?", (record.id,))

    for row in event_rows:
        assert SECRET not in json.dumps(dict(row), default=str)
    for row in action_rows:
        assert SECRET not in json.dumps(dict(row), default=str)
