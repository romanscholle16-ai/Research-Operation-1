"""Deterministic strategy-specification validation (Phase 6 brief
section 16). Runs BEFORE a specification is allowed anywhere near
`adapter.py`/Phase 2-3. Two distinct kinds of problem are kept separate:

- `errors`: the specification is structurally malformed (an unsupported
  operator, indicator, or field name; a wrong-typed parameter; a missing
  required scalar). This always means `INVALID` - nothing here attempts
  to "fix" a malformed rule by guessing what was meant.
- `computed_status`: even a structurally well-formed specification is
  only ever `VALID` when nothing in it is `UNKNOWN`/`UNSUPPORTED` and it
  carries no recorded ambiguity (brief section 15 - unresolved mandatory
  rules must not silently enter execution). Otherwise it is `INCOMPLETE`
  or `AMBIGUOUS`, which `adapter.py` refuses to adapt.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.backtesting.market_data import Timeframe
from app.research.specification import Condition, FieldRef, RuleStatus, SpecStatus, StrategySpecification

SUPPORTED_INDICATORS: dict[str, frozenset[str]] = {
    "EMA": frozenset({"period"}),
    "SMA": frozenset({"period"}),
}
SUPPORTED_PRICE_FIELDS = frozenset({"open", "high", "low", "close", "volume"})
SUPPORTED_COMPARISON_OPS = frozenset({">", "<", ">=", "<=", "==", "!=", "crosses_above", "crosses_below"})
SUPPORTED_LOGICAL_OPS = frozenset({"and", "or"})
SUPPORTED_OPS = SUPPORTED_COMPARISON_OPS | SUPPORTED_LOGICAL_OPS
SUPPORTED_TIMEFRAMES = frozenset(tf.value for tf in Timeframe)


@dataclass(frozen=True)
class ValidationResult:
    errors: tuple[str, ...]
    computed_status: SpecStatus

    @property
    def is_valid(self) -> bool:
        return self.computed_status is SpecStatus.VALID and not self.errors


def _validate_field_ref(ref: FieldRef, errors: list[str]) -> None:
    if ref.name in SUPPORTED_PRICE_FIELDS:
        return
    if ref.name in SUPPORTED_INDICATORS:
        required = SUPPORTED_INDICATORS[ref.name]
        missing = required - set(ref.params.keys())
        if missing:
            errors.append(f"indicator {ref.name!r} missing required params: {sorted(missing)}")
        for key in required:
            value = ref.params.get(key)
            if value is not None and not isinstance(value, (int, float)):
                errors.append(f"indicator {ref.name!r} param {key!r} must be numeric, got {type(value).__name__}")
        return
    errors.append(f"unsupported field/indicator reference {ref.name!r}")


def _validate_condition(condition: Condition, errors: list[str]) -> None:
    if condition.op in SUPPORTED_LOGICAL_OPS:
        if not isinstance(condition.left, Condition) or not isinstance(condition.right, Condition):
            errors.append(f"logical operator {condition.op!r} requires two nested conditions")
        else:
            _validate_condition(condition.left, errors)
            _validate_condition(condition.right, errors)
        return
    if condition.op not in SUPPORTED_OPS:
        errors.append(f"unsupported condition operator {condition.op!r}")
        return
    for operand in (condition.left, condition.right):
        if isinstance(operand, FieldRef):
            _validate_field_ref(operand, errors)
        elif isinstance(operand, Condition):
            errors.append(f"comparison operator {condition.op!r} cannot take a nested condition as an operand")
        elif operand is None:
            errors.append(f"comparison operator {condition.op!r} requires both operands")
        elif not isinstance(operand, (int, float)):
            errors.append(f"condition operand must be a field reference or a number, got {type(operand).__name__}")


def validate_specification(spec: StrategySpecification) -> ValidationResult:
    errors: list[str] = []

    if not spec.name or not spec.name.strip():
        errors.append("name is required")

    if spec.timeframe is not None and spec.timeframe not in SUPPORTED_TIMEFRAMES:
        errors.append(f"unsupported timeframe {spec.timeframe!r}; must be one of {sorted(SUPPORTED_TIMEFRAMES)}")

    for indicator in spec.indicators:
        if indicator.type not in SUPPORTED_INDICATORS:
            errors.append(f"unsupported indicator type {indicator.type!r}")
            continue
        missing = SUPPORTED_INDICATORS[indicator.type] - set(indicator.params.keys())
        if missing:
            errors.append(f"indicator {indicator.type!r} missing required params: {sorted(missing)}")

    all_rules = spec.all_rules()
    for rule in all_rules:
        if rule.condition is not None:
            _validate_condition(rule.condition, errors)
        if rule.side is not None and rule.side not in ("long", "short"):
            errors.append(f"rule side must be 'long' or 'short', got {rule.side!r}")

    if errors:
        return ValidationResult(errors=tuple(errors), computed_status=SpecStatus.INVALID)

    if spec.ambiguities:
        return ValidationResult(errors=(), computed_status=SpecStatus.AMBIGUOUS)

    has_unresolved_rule = any(
        rule.status in (RuleStatus.UNKNOWN, RuleStatus.UNSUPPORTED) for rule in all_rules
    )
    if spec.unknowns or has_unresolved_rule or not spec.entry_rules or spec.timeframe is None:
        return ValidationResult(errors=(), computed_status=SpecStatus.INCOMPLETE)

    return ValidationResult(errors=(), computed_status=SpecStatus.VALID)
