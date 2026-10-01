"""The one parser from "JSON-ish dict a provider handed back" to
`WebResearchDecision` - same role and same strictness discipline as
`app/ai/providers/structured_output.py` for the experiment-research
workflow (Phase 5 brief section 13's "do not create a second competing
schema" applied here too: this is the ONLY place web-research AI output
becomes a typed decision). Reuses `app.ai.provider.AIProviderResponseError`
rather than inventing a parallel error type, so `WebResearchAgent` can
catch exactly the same exception class Phase 4/5's `ResearchAgent` does.

Strict: a missing/wrong-typed required field raises immediately. Never
guesses at what a malformed proposal "probably meant" (brief section 12,
applied here to the web-research decision the same way it applies to
`ResearchDecision`).
"""

from __future__ import annotations

from typing import Any

from app.ai.provider import AIProviderResponseError
from app.research.decision import ProposedRule, ResearchAction, SpecificationUpdate, WebResearchDecision
from app.research.specification import Condition, FieldRef, IndicatorSpec


def _require_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise AIProviderResponseError(f"missing or empty required string field {key!r}")
    return value


def _optional_str(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise AIProviderResponseError(f"field {key!r} must be a string if present")
    return value


def _optional_str_tuple(data: dict[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key)
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise AIProviderResponseError(f"field {key!r} must be a list of strings if present")
    return tuple(value)


def _operand_from_json(value: Any) -> "FieldRef | Condition | float":
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        if "op" in value:
            return condition_from_dict(value)
        if "name" in value:
            params = value.get("params", {})
            if not isinstance(params, dict):
                raise AIProviderResponseError("FieldRef params must be an object")
            return FieldRef(name=_require_str(value, "name"), params=params)
    raise AIProviderResponseError(f"invalid condition operand: {value!r}")


def condition_from_dict(data: Any) -> Condition:
    if not isinstance(data, dict):
        raise AIProviderResponseError(f"condition must be an object, got {type(data).__name__}")
    op = _require_str(data, "op")
    if "left" not in data:
        raise AIProviderResponseError("condition missing required field 'left'")
    left = _operand_from_json(data["left"])
    right = _operand_from_json(data["right"]) if data.get("right") is not None else None
    return Condition(op=op, left=left, right=right)


def indicator_spec_from_dict(data: Any) -> IndicatorSpec:
    if not isinstance(data, dict):
        raise AIProviderResponseError(f"indicator must be an object, got {type(data).__name__}")
    params = data.get("params", {})
    if not isinstance(params, dict):
        raise AIProviderResponseError("indicator params must be an object")
    return IndicatorSpec(type=_require_str(data, "type"), params=params, name=_optional_str(data, "name"))


def proposed_rule_from_dict(data: Any) -> ProposedRule:
    if not isinstance(data, dict):
        raise AIProviderResponseError(f"proposed rule must be an object, got {type(data).__name__}")
    condition = condition_from_dict(data["condition"]) if data.get("condition") is not None else None
    value = data.get("value")
    if value is not None and not isinstance(value, (int, float)):
        raise AIProviderResponseError("proposed rule 'value' must be numeric or null")
    return ProposedRule(
        rule_kind=_require_str(data, "rule_kind"),
        description=_require_str(data, "description"),
        side=_optional_str(data, "side"),
        condition=condition,
        value=float(value) if value is not None else None,
        value_type=_optional_str(data, "value_type"),
        evidence_ids=_optional_str_tuple(data, "evidence_ids"),
    )


def specification_update_from_dict(data: Any) -> SpecificationUpdate:
    if not isinstance(data, dict):
        raise AIProviderResponseError(f"specification_update must be an object, got {type(data).__name__}")
    indicators_raw = data.get("indicators", [])
    if not isinstance(indicators_raw, list):
        raise AIProviderResponseError("specification_update.indicators must be a list")
    rules_raw = data.get("rules", [])
    if not isinstance(rules_raw, list):
        raise AIProviderResponseError("specification_update.rules must be a list")
    return SpecificationUpdate(
        name=_optional_str(data, "name"),
        timeframe=_optional_str(data, "timeframe"),
        market=_optional_str(data, "market"),
        instrument=_optional_str(data, "instrument"),
        session=_optional_str(data, "session"),
        indicators=tuple(indicator_spec_from_dict(i) for i in indicators_raw),
        rules=tuple(proposed_rule_from_dict(r) for r in rules_raw),
        unknowns=_optional_str_tuple(data, "unknowns"),
        ambiguities=_optional_str_tuple(data, "ambiguities"),
    )


_VALID_ACTIONS = frozenset(a.value for a in ResearchAction)


def web_research_decision_from_dict(data: Any) -> WebResearchDecision:
    if not isinstance(data, dict):
        raise AIProviderResponseError(f"provider response must be a JSON object, got {type(data).__name__}")

    action_raw = _require_str(data, "action")
    if action_raw not in _VALID_ACTIONS:
        raise AIProviderResponseError(f"unknown action {action_raw!r}; must be one of {sorted(_VALID_ACTIONS)}")

    spec_update_raw = data.get("specification_update")
    spec_update = specification_update_from_dict(spec_update_raw) if spec_update_raw is not None else None

    return WebResearchDecision(
        objective=_require_str(data, "objective"),
        reasoning_summary=_require_str(data, "reasoning_summary"),
        action=ResearchAction(action_raw),
        query=_optional_str(data, "query"),
        url=_optional_str(data, "url"),
        source_id=_optional_str(data, "source_id"),
        specification_update=spec_update,
        stopping_reason=_optional_str(data, "stopping_reason"),
    )
