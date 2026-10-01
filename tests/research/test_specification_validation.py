from app.research.specification import (
    Condition,
    FieldRef,
    IndicatorSpec,
    RuleSpec,
    RuleStatus,
    SpecStatus,
    StrategySpecification,
)
from app.research.validation import validate_specification


def _entry_rule(**overrides) -> RuleSpec:
    defaults = dict(
        description="enter long on EMA cross",
        status=RuleStatus.INTERPRETED,
        side="long",
        condition=Condition(op="crosses_above", left=FieldRef(name="close"), right=FieldRef(name="EMA", params={"period": 50})),
    )
    defaults.update(overrides)
    return RuleSpec(**defaults)


def test_valid_specification() -> None:
    spec = StrategySpecification(name="s", timeframe="1h", entry_rules=(_entry_rule(),))
    result = validate_specification(spec)
    assert result.is_valid
    assert result.computed_status is SpecStatus.VALID
    assert result.errors == ()


def test_missing_name_is_invalid() -> None:
    spec = StrategySpecification(name="", timeframe="1h", entry_rules=(_entry_rule(),))
    result = validate_specification(spec)
    assert result.computed_status is SpecStatus.INVALID
    assert any("name" in e for e in result.errors)


def test_no_entry_rules_is_incomplete() -> None:
    spec = StrategySpecification(name="s", timeframe="1h")
    result = validate_specification(spec)
    assert result.computed_status is SpecStatus.INCOMPLETE
    assert result.errors == ()


def test_missing_timeframe_is_incomplete() -> None:
    spec = StrategySpecification(name="s", entry_rules=(_entry_rule(),))
    result = validate_specification(spec)
    assert result.computed_status is SpecStatus.INCOMPLETE


def test_unsupported_timeframe_is_invalid() -> None:
    spec = StrategySpecification(name="s", timeframe="3m", entry_rules=(_entry_rule(),))
    result = validate_specification(spec)
    assert result.computed_status is SpecStatus.INVALID
    assert any("timeframe" in e for e in result.errors)


def test_unsupported_indicator_type_is_invalid() -> None:
    rule = _entry_rule(condition=Condition(op=">", left=FieldRef(name="close"), right=FieldRef(name="RSI", params={"period": 14})))
    spec = StrategySpecification(name="s", timeframe="1h", entry_rules=(rule,))
    result = validate_specification(spec)
    assert result.computed_status is SpecStatus.INVALID
    assert any("RSI" in e for e in result.errors)


def test_indicator_missing_required_param_is_invalid() -> None:
    rule = _entry_rule(condition=Condition(op=">", left=FieldRef(name="close"), right=FieldRef(name="EMA", params={})))
    spec = StrategySpecification(name="s", timeframe="1h", entry_rules=(rule,))
    result = validate_specification(spec)
    assert result.computed_status is SpecStatus.INVALID
    assert any("period" in e for e in result.errors)


def test_unsupported_operator_is_invalid() -> None:
    rule = _entry_rule(condition=Condition(op="xor", left=FieldRef(name="close"), right=5))
    spec = StrategySpecification(name="s", timeframe="1h", entry_rules=(rule,))
    result = validate_specification(spec)
    assert result.computed_status is SpecStatus.INVALID
    assert any("xor" in e for e in result.errors)


def test_invalid_side_is_invalid() -> None:
    rule = _entry_rule(side="sideways")
    spec = StrategySpecification(name="s", timeframe="1h", entry_rules=(rule,))
    result = validate_specification(spec)
    assert result.computed_status is SpecStatus.INVALID


def test_ambiguities_make_status_ambiguous() -> None:
    spec = StrategySpecification(name="s", timeframe="1h", entry_rules=(_entry_rule(),), ambiguities=("unclear what 'confirmation' means",))
    result = validate_specification(spec)
    assert result.computed_status is SpecStatus.AMBIGUOUS
    assert result.errors == ()


def test_unresolved_unknown_rule_is_incomplete() -> None:
    unresolved = RuleSpec(description="exact sweep definition not given", status=RuleStatus.UNKNOWN)
    spec = StrategySpecification(name="s", timeframe="1h", entry_rules=(_entry_rule(),), exit_rules=(unresolved,))
    result = validate_specification(spec)
    assert result.computed_status is SpecStatus.INCOMPLETE


def test_unsupported_rule_status_is_incomplete() -> None:
    unresolved = RuleSpec(description="trailing stop by volatility bands", status=RuleStatus.UNSUPPORTED)
    spec = StrategySpecification(name="s", timeframe="1h", entry_rules=(_entry_rule(),), stop_loss_rules=(unresolved,))
    result = validate_specification(spec)
    assert result.computed_status is SpecStatus.INCOMPLETE


def test_explicit_unknowns_list_forces_incomplete_even_if_rules_look_fine() -> None:
    spec = StrategySpecification(name="s", timeframe="1h", entry_rules=(_entry_rule(),), unknowns=("confirmation rule not defined",))
    result = validate_specification(spec)
    assert result.computed_status is SpecStatus.INCOMPLETE


def test_logical_and_requires_two_conditions() -> None:
    bad = Condition(op="and", left=FieldRef(name="close"), right=5)
    rule = _entry_rule(condition=bad)
    spec = StrategySpecification(name="s", timeframe="1h", entry_rules=(rule,))
    result = validate_specification(spec)
    assert result.computed_status is SpecStatus.INVALID


def test_nested_logical_condition_is_valid() -> None:
    inner_a = Condition(op=">", left=FieldRef(name="close"), right=FieldRef(name="EMA", params={"period": 50}))
    inner_b = Condition(op=">", left=FieldRef(name="volume"), right=1000)
    combined = Condition(op="and", left=inner_a, right=inner_b)
    rule = _entry_rule(condition=combined)
    spec = StrategySpecification(name="s", timeframe="1h", entry_rules=(rule,))
    result = validate_specification(spec)
    assert result.is_valid
