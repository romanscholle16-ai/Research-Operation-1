import pytest

from app.ai.provider import AIProviderResponseError
from app.research.structured_output import (
    condition_from_dict,
    proposed_rule_from_dict,
    specification_update_from_dict,
    web_research_decision_from_dict,
)


def test_parses_minimal_valid_decision() -> None:
    decision = web_research_decision_from_dict(
        {"objective": "o", "reasoning_summary": "r", "action": "discover_sources", "query": "ema strategy"}
    )
    assert decision.action.value == "discover_sources"
    assert decision.query == "ema strategy"


def test_rejects_unknown_action() -> None:
    with pytest.raises(AIProviderResponseError):
        web_research_decision_from_dict({"objective": "o", "reasoning_summary": "r", "action": "delete_everything"})


@pytest.mark.parametrize("missing", ["objective", "reasoning_summary", "action"])
def test_rejects_missing_required_field(missing: str) -> None:
    data = {"objective": "o", "reasoning_summary": "r", "action": "stop"}
    del data[missing]
    with pytest.raises(AIProviderResponseError):
        web_research_decision_from_dict(data)


def test_condition_from_dict_parses_nested_field_refs() -> None:
    condition = condition_from_dict(
        {"op": ">", "left": {"name": "close"}, "right": {"name": "EMA", "params": {"period": 50}}}
    )
    assert condition.op == ">"
    assert condition.left.name == "close"
    assert condition.right.name == "EMA"
    assert condition.right.params == {"period": 50}


def test_condition_from_dict_parses_nested_logical_condition() -> None:
    condition = condition_from_dict(
        {
            "op": "and",
            "left": {"op": ">", "left": {"name": "close"}, "right": 100},
            "right": {"op": "<", "left": {"name": "volume"}, "right": 500},
        }
    )
    assert condition.op == "and"
    assert condition.left.op == ">"
    assert condition.right.op == "<"


def test_condition_from_dict_rejects_malformed_operand() -> None:
    with pytest.raises(AIProviderResponseError):
        condition_from_dict({"op": ">", "left": "not an operand", "right": 1})


def test_condition_requires_op_and_left() -> None:
    with pytest.raises(AIProviderResponseError):
        condition_from_dict({"left": {"name": "close"}})


def test_proposed_rule_from_dict() -> None:
    rule = proposed_rule_from_dict(
        {
            "rule_kind": "entry",
            "description": "enter long on cross",
            "side": "long",
            "condition": {"op": ">", "left": {"name": "close"}, "right": 100},
            "evidence_ids": ["e1", "e2"],
        }
    )
    assert rule.rule_kind == "entry"
    assert rule.side == "long"
    assert rule.evidence_ids == ("e1", "e2")


def test_proposed_rule_rejects_non_numeric_value() -> None:
    with pytest.raises(AIProviderResponseError):
        proposed_rule_from_dict({"rule_kind": "stop_loss", "description": "x", "value": "two percent"})


def test_specification_update_from_dict() -> None:
    update = specification_update_from_dict(
        {
            "name": "ema strat",
            "timeframe": "1h",
            "indicators": [{"type": "EMA", "params": {"period": 50}}],
            "rules": [{"rule_kind": "entry", "description": "x"}],
            "unknowns": ["confirmation rule unclear"],
        }
    )
    assert update.name == "ema strat"
    assert len(update.indicators) == 1
    assert len(update.rules) == 1
    assert update.unknowns == ("confirmation rule unclear",)


def test_full_decision_with_specification_update() -> None:
    decision = web_research_decision_from_dict(
        {
            "objective": "o",
            "reasoning_summary": "building spec",
            "action": "update_specification",
            "specification_update": {
                "name": "s",
                "rules": [
                    {
                        "rule_kind": "entry",
                        "description": "enter long",
                        "side": "long",
                        "condition": {"op": "crosses_above", "left": {"name": "close"}, "right": {"name": "EMA", "params": {"period": 50}}},
                    }
                ],
            },
        }
    )
    assert decision.specification_update is not None
    assert decision.specification_update.rules[0].side == "long"


def test_malformed_nested_rule_is_rejected_not_dropped() -> None:
    with pytest.raises(AIProviderResponseError):
        web_research_decision_from_dict(
            {
                "objective": "o",
                "reasoning_summary": "r",
                "action": "update_specification",
                "specification_update": {"rules": [{"description": "missing rule_kind"}]},
            }
        )
