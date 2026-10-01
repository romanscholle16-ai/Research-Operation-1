"""The boundary between a `StrategySpecification` and Phase 2's
`Strategy` interface (Phase 6 brief section 17).

This is a SAFE INTERPRETER, not code generation: `_evaluate_condition()`
walks a `Condition` tree and computes a boolean by looking up precomputed
numeric values for a fixed, whitelisted set of fields/indicators
(`validation.py`'s `SUPPORTED_PRICE_FIELDS`/`SUPPORTED_INDICATORS`).
There is no `eval`/`exec`/`compile` anywhere in this module, and there
cannot be an injection vector through a `Condition` tree the way there
could be through a string of code, because a `Condition` is a frozen
dataclass tree built only from already-validated, already-whitelisted
pieces (`validation.py` runs first and `adapt_specification()` refuses
anything that didn't pass).

Deliberately narrow scope (brief section 17: "If full generic compilation
... would require unsafe or speculative code generation, do NOT implement
it"): only `close`/`open`/`high`/`low`/`volume` fields, `EMA`/`SMA`
indicators, comparison/logical/crossing operators, and percent-based
stop-loss/take-profit are actually adaptable into a running `Strategy`.
Anything else (a structural stop placement, an unsupported indicator, a
rule with no resolvable condition) makes `adapt_specification()` return
`adaptable=False` with specific reasons - never a best-effort guess.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.backtesting.market_data import Candle
from app.backtesting.signals import Signal, SignalAction
from app.backtesting.strategy import Strategy, StrategyContext
from app.research.specification import Condition, FieldRef, RuleSpec, StrategySpecification
from app.research.validation import validate_specification


def _sma(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def _ema(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    k = 2.0 / (period + 1)
    value = sum(closes[:period]) / period
    for price in closes[period:]:
        value = price * k + value * (1 - k)
    return value


_PRICE_FIELD_GETTERS: dict[str, Callable[[Candle], float]] = {
    "open": lambda c: c.open,
    "high": lambda c: c.high,
    "low": lambda c: c.low,
    "close": lambda c: c.close,
    "volume": lambda c: c.volume,
}

_INDICATOR_FUNCTIONS: dict[str, Callable[[list[float], int], float | None]] = {
    "EMA": _ema,
    "SMA": _sma,
}


def _resolve(operand: "FieldRef | Condition | float | int", closes: list[float], candle: Candle) -> float | None:
    if isinstance(operand, (int, float)):
        return float(operand)
    if isinstance(operand, FieldRef):
        if operand.name in _PRICE_FIELD_GETTERS:
            return _PRICE_FIELD_GETTERS[operand.name](candle)
        if operand.name in _INDICATOR_FUNCTIONS:
            return _INDICATOR_FUNCTIONS[operand.name](closes, int(operand.params["period"]))
    return None


def _evaluate_condition(
    condition: Condition,
    closes: list[float],
    candle: Candle,
    previous_closes: list[float] | None,
    previous_candle: Candle | None,
) -> bool | None:
    if condition.op == "and":
        left = _evaluate_condition(condition.left, closes, candle, previous_closes, previous_candle)  # type: ignore[arg-type]
        right = _evaluate_condition(condition.right, closes, candle, previous_closes, previous_candle)  # type: ignore[arg-type]
        return None if left is None or right is None else (left and right)
    if condition.op == "or":
        left = _evaluate_condition(condition.left, closes, candle, previous_closes, previous_candle)  # type: ignore[arg-type]
        right = _evaluate_condition(condition.right, closes, candle, previous_closes, previous_candle)  # type: ignore[arg-type]
        return None if left is None or right is None else (left or right)

    left_val = _resolve(condition.left, closes, candle)
    right_val = _resolve(condition.right, closes, candle)  # type: ignore[arg-type]
    if left_val is None or right_val is None:
        return None

    if condition.op == ">":
        return left_val > right_val
    if condition.op == "<":
        return left_val < right_val
    if condition.op == ">=":
        return left_val >= right_val
    if condition.op == "<=":
        return left_val <= right_val
    if condition.op == "==":
        return left_val == right_val
    if condition.op == "!=":
        return left_val != right_val
    if condition.op in ("crosses_above", "crosses_below"):
        if previous_closes is None or previous_candle is None:
            return None
        prev_left = _resolve(condition.left, previous_closes, previous_candle)
        prev_right = _resolve(condition.right, previous_closes, previous_candle)  # type: ignore[arg-type]
        if prev_left is None or prev_right is None:
            return None
        if condition.op == "crosses_above":
            return prev_left <= prev_right and left_val > right_val
        return prev_left >= prev_right and left_val < right_val
    return None  # unreachable after validation.py, which rejects unknown ops


class SpecDrivenStrategy(Strategy):
    """A deterministic `Strategy` interpreting a validated
    `StrategySpecification`'s entry/exit conditions and percent-based
    stop-loss/take-profit. Stop/target distances are computed from the
    signal candle's close as an estimate - the actual fill (and
    therefore the realized stop/target price) happens on the next
    candle's open per Phase 2's look-ahead rules, the same way a trader
    sizing a stop before an order fills would estimate from the last
    known price."""

    def __init__(self, spec: StrategySpecification, params: dict | None = None) -> None:
        params = params or {}
        self.spec = spec
        self.name = spec.name
        self.version = spec.id
        self.quantity = params.get("quantity", spec.execution_assumptions.get("quantity", 1.0))

    def on_bar(self, context: StrategyContext) -> list[Signal]:
        history = context.history
        candle = context.current_candle
        closes = [c.close for c in history]
        previous_closes = closes[:-1] if len(closes) > 1 else None
        previous_candle = history[-2] if len(history) > 1 else None

        if context.position is None:
            for rule in self.spec.entry_rules:
                if rule.condition is None or rule.side not in ("long", "short"):
                    continue
                if _evaluate_condition(rule.condition, closes, candle, previous_closes, previous_candle):
                    action = SignalAction.OPEN_LONG if rule.side == "long" else SignalAction.OPEN_SHORT
                    stop_loss, take_profit = self._compute_stop_and_target(candle.close, rule.side)
                    return [
                        Signal(
                            action,
                            timestamp=candle.timestamp,
                            quantity=self.quantity,
                            stop_loss=stop_loss,
                            take_profit=take_profit,
                        )
                    ]
            return []

        for rule in self.spec.exit_rules:
            if rule.condition is None:
                continue
            if rule.side is not None and rule.side != context.position.side.value:
                continue
            if _evaluate_condition(rule.condition, closes, candle, previous_closes, previous_candle):
                return [Signal(SignalAction.CLOSE, timestamp=candle.timestamp)]
        return []

    def _compute_stop_and_target(self, reference_price: float, side: str) -> tuple[float | None, float | None]:
        stop_loss = None
        for rule in self.spec.stop_loss_rules:
            if rule.value is not None and rule.value_type == "percent":
                distance = reference_price * (rule.value / 100.0)
                stop_loss = reference_price - distance if side == "long" else reference_price + distance
        take_profit = None
        for rule in self.spec.take_profit_rules:
            if rule.value is not None and rule.value_type == "percent":
                distance = reference_price * (rule.value / 100.0)
                take_profit = reference_price + distance if side == "long" else reference_price - distance
        return stop_loss, take_profit


@dataclass(frozen=True)
class AdapterResult:
    adaptable: bool
    strategy_factory: Callable[[dict], Strategy] | None
    reasons: tuple[str, ...] = ()


_SUPPORTED_STOP_TARGET_VALUE_TYPES = frozenset({"percent"})


def adapt_specification(spec: StrategySpecification) -> AdapterResult:
    """Returns a working `strategy_factory` only for a specification that
    both passes `validate_specification()` (status VALID) AND stays
    within this adapter's deliberately narrow supported subset. Anything
    else comes back `adaptable=False` with specific reasons - never a
    partial or best-effort strategy.
    """
    validation = validate_specification(spec)
    if not validation.is_valid:
        return AdapterResult(
            adaptable=False,
            strategy_factory=None,
            reasons=(f"specification is not valid (status={validation.computed_status.value})", *validation.errors),
        )

    reasons: list[str] = []
    for rule in spec.entry_rules:
        if rule.condition is None:
            reasons.append(f"entry rule {rule.description!r} has no structural condition to interpret")
        if rule.side not in ("long", "short"):
            reasons.append(f"entry rule {rule.description!r} does not specify side (long/short)")

    for rule in (*spec.stop_loss_rules, *spec.take_profit_rules):
        if rule.condition is not None:
            reasons.append(f"rule {rule.description!r} uses a structural placement condition, not yet supported by this adapter")
        elif rule.value is not None and rule.value_type not in _SUPPORTED_STOP_TARGET_VALUE_TYPES:
            reasons.append(f"rule {rule.description!r} has unsupported value_type {rule.value_type!r}")

    if reasons:
        return AdapterResult(adaptable=False, strategy_factory=None, reasons=tuple(reasons))

    def factory(params: dict) -> Strategy:
        return SpecDrivenStrategy(spec, params)

    return AdapterResult(adaptable=True, strategy_factory=factory)
