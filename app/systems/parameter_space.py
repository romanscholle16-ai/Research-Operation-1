"""Deterministic parameter generation, shared by every research system
that needs to enumerate configurations (Parameter Explorer directly;
Risk/Execution Optimizer and others reuse the same primitives).

No randomness, no AI (Phase 3 brief section 4). `ParameterSpace.
generate_combinations()` always returns the same list, in the same
order, for the same input - it iterates parameter names in sorted order
and takes the Cartesian product of each parameter's values in the order
they were specified.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any, Protocol


class ParamSpec(Protocol):
    def values(self) -> list[Any]: ...


@dataclass(frozen=True)
class Fixed:
    """A parameter held constant across every experiment in the space."""

    value: Any

    def values(self) -> list[Any]:
        return [self.value]


@dataclass(frozen=True)
class ValueList:
    """An explicit, ordered list of values to test."""

    items: list[Any]

    def values(self) -> list[Any]:
        return list(self.items)


@dataclass(frozen=True)
class ValueRange:
    """A numeric range [start, stop] stepped by `step` (inclusive of
    `stop` when it lands exactly on a step, within floating-point
    tolerance)."""

    start: float
    stop: float
    step: float

    def values(self) -> list[Any]:
        if self.step == 0:
            raise ValueError("ValueRange.step must be non-zero")
        count = round((self.stop - self.start) / self.step)
        result = []
        for i in range(count + 1):
            value = self.start + i * self.step
            if (self.step > 0 and value > self.stop + 1e-9) or (
                self.step < 0 and value < self.stop - 1e-9
            ):
                break
            result.append(round(value, 10))
        return result


@dataclass(frozen=True)
class Categorical:
    """A named set of mutually exclusive alternatives (e.g. rule
    variants, session names) - semantically distinct from `ValueList`
    even though the mechanics are the same, per Phase 3 brief section 3."""

    options: list[Any]

    def values(self) -> list[Any]:
        return list(self.options)


@dataclass(frozen=True)
class ParameterSpace:
    parameters: dict[str, ParamSpec]

    def generate_combinations(self) -> list[dict[str, Any]]:
        if not self.parameters:
            return [{}]
        names = sorted(self.parameters.keys())
        value_lists = [self.parameters[name].values() for name in names]
        combinations = []
        for combo in itertools.product(*value_lists):
            combinations.append(dict(zip(names, combo)))
        return combinations
