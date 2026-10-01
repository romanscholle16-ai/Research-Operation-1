"""The ONE parser from "JSON-ish dict a real provider handed back" to
Phase 4's `ResearchDecision`/`ExperimentProposal` (Phase 5 brief section
13: "Do not create a second competing AI decision schema"). Every
JSON-returning provider adapter (Claude, Ollama, and any future one)
calls `research_decision_from_dict()` - nothing adapter-specific about
decision shape lives anywhere else.

Deliberately strict: a missing or wrong-typed required field raises
`AIProviderResponseError` immediately rather than being defaulted or
guessed at (brief section 12: "Do not silently 'fix' invalid AI
instructions when doing so could alter intent or safety"). This is the
PARSING layer only - it checks "is this well-formed input for our
schema," not "is this an experiment our catalog allows." The latter is
`app/ai/validation.py::validate_proposal()`, unchanged, applied
afterward by `ResearchAgent` exactly as it is to any other provider.
"""

from __future__ import annotations

from typing import Any

from app.ai.decision import ExperimentProposal, ResearchDecision
from app.ai.provider import AIProviderResponseError


def _require_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise AIProviderResponseError(f"missing or empty required string field {key!r}")
    return value


def _optional_str(data: dict[str, Any], key: str, default: str = "") -> str:
    value = data.get(key, default)
    if value is None:
        return default
    if not isinstance(value, str):
        raise AIProviderResponseError(f"field {key!r} must be a string if present")
    return value


def _optional_dict(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise AIProviderResponseError(f"field {key!r} must be an object if present")
    return value


def _optional_str_tuple(data: dict[str, Any], key: str) -> tuple[str, ...] | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise AIProviderResponseError(f"field {key!r} must be a list of strings if present")
    return tuple(value)


def _optional_dict_tuple(data: dict[str, Any], key: str) -> tuple[dict[str, Any], ...] | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(v, dict) for v in value):
        raise AIProviderResponseError(f"field {key!r} must be a list of objects if present")
    return tuple(value)


def experiment_proposal_from_dict(data: Any) -> ExperimentProposal:
    if not isinstance(data, dict):
        raise AIProviderResponseError(f"each requested experiment must be an object, got {type(data).__name__}")

    parameter_space_raw = data.get("parameter_space")
    if parameter_space_raw is not None:
        if not isinstance(parameter_space_raw, dict) or not all(
            isinstance(v, list) for v in parameter_space_raw.values()
        ):
            raise AIProviderResponseError("parameter_space must be an object mapping names to lists")

    return ExperimentProposal(
        research_system=_require_str(data, "research_system"),
        reason=_optional_str(data, "reason"),
        base_parameters=_optional_dict(data, "base_parameters"),
        parameter_space=parameter_space_raw,
        rule_variant_names=_optional_str_tuple(data, "rule_variant_names"),
        execution_variant_names=_optional_str_tuple(data, "execution_variant_names"),
        segment_specs=_optional_dict_tuple(data, "segment_specs"),
        adversarial=_optional_dict(data, "adversarial") or None,
    )


def research_decision_from_dict(data: Any) -> ResearchDecision:
    if not isinstance(data, dict):
        raise AIProviderResponseError(f"provider response must be a JSON object, got {type(data).__name__}")

    requested_raw = data.get("requested_experiments", [])
    if not isinstance(requested_raw, list):
        raise AIProviderResponseError("requested_experiments must be a list")
    proposals = tuple(experiment_proposal_from_dict(item) for item in requested_raw)

    analysis_tasks = _optional_str_tuple(data, "analysis_tasks") or ()

    stopping_reason = data.get("stopping_reason")
    if stopping_reason is not None and not isinstance(stopping_reason, str):
        raise AIProviderResponseError("stopping_reason must be a string or null")

    confidence = data.get("confidence")
    if confidence is not None and not isinstance(confidence, (int, float)):
        raise AIProviderResponseError("confidence must be a number or null")

    return ResearchDecision(
        objective=_require_str(data, "objective"),
        hypothesis=_require_str(data, "hypothesis"),
        reasoning_summary=_require_str(data, "reasoning_summary"),
        requested_experiments=proposals,
        analysis_tasks=analysis_tasks,
        stopping_reason=stopping_reason,
        confidence=float(confidence) if confidence is not None else None,
    )
