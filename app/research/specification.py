"""The canonical structured strategy representation (Phase 6 brief
section 14). Every rule is a data structure - a `Condition`/`FieldRef`
expression tree over named fields ("close", "EMA", ...) and comparison/
logical operators - never a string of Python (or any other language)
source code. `app/research/adapter.py` is the only thing that ever
interprets a `Condition` tree, and it does so by walking the tree and
evaluating each node against precomputed values; nothing here or there
ever calls `eval`/`exec`/`compile`.

Section 15's "no assumption filling" is enforced by `RuleStatus`: a rule
built from a direct quote is `EXPLICIT`; an AI's own reading of an
ambiguous passage is `INTERPRETED` (never conflated with `EXPLICIT`);
anything the source didn't address at all is `UNKNOWN`; a recognized but
not-yet-representable concept is `UNSUPPORTED`. A specification's
`status` can only be `VALID` when nothing underneath it is `UNKNOWN` or
`UNSUPPORTED` and it isn't flagged `AMBIGUOUS` - enforced by
`validation.py`, not by this module (this module only models the shape).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class SpecStatus(str, Enum):
    VALID = "valid"
    INCOMPLETE = "incomplete"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"


class RuleStatus(str, Enum):
    EXPLICIT = "explicit"  # directly supported by quoted evidence
    INTERPRETED = "interpreted"  # an AI's hypothesis - explicitly labeled, never passed off as EXPLICIT
    UNKNOWN = "unknown"  # the source never addressed this
    UNSUPPORTED = "unsupported"  # recognized, but not representable/implemented yet


def new_spec_id() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True)
class FieldRef:
    """A reference to a price field ("close", "open", ...) or an
    indicator ("EMA", "SMA", ...) with its parameters."""

    name: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Condition:
    """A structural boolean/comparison expression. `left`/`right` are
    each a `FieldRef`, a nested `Condition` (for "and"/"or"), or a plain
    number - never a string to be executed."""

    op: str  # ">" | "<" | ">=" | "<=" | "==" | "!=" | "and" | "or" | "crosses_above" | "crosses_below"
    left: "FieldRef | Condition | float | int"
    right: "FieldRef | Condition | float | int | None" = None


@dataclass(frozen=True)
class IndicatorSpec:
    type: str  # e.g. "EMA", "SMA"
    params: dict[str, Any] = field(default_factory=dict)
    name: str | None = None  # optional alias, e.g. "fast_ema"


@dataclass(frozen=True)
class RuleSpec:
    description: str  # human-readable summary / the original claim text
    status: RuleStatus
    side: str | None = None  # "long" | "short" | None
    condition: Condition | None = None
    value: float | None = None  # for simple numeric rules (e.g. a fixed stop distance)
    value_type: str | None = None  # "percent" | "price_offset" | "r_multiple" | "atr_multiple" | ...
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class StrategySpecification:
    name: str
    description: str = ""
    market: str | None = None
    instrument: str | None = None
    timeframe: str | None = None
    session: str | None = None
    indicators: tuple[IndicatorSpec, ...] = ()
    entry_rules: tuple[RuleSpec, ...] = ()
    exit_rules: tuple[RuleSpec, ...] = ()
    stop_loss_rules: tuple[RuleSpec, ...] = ()
    take_profit_rules: tuple[RuleSpec, ...] = ()
    position_rules: tuple[RuleSpec, ...] = ()
    filters: tuple[RuleSpec, ...] = ()
    confirmation_rules: tuple[RuleSpec, ...] = ()
    execution_assumptions: dict[str, Any] = field(default_factory=dict)
    required_data: tuple[str, ...] = ()
    source_evidence_ids: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    ambiguities: tuple[str, ...] = ()
    status: SpecStatus = SpecStatus.INCOMPLETE
    id: str = field(default_factory=new_spec_id)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def all_rules(self) -> tuple[RuleSpec, ...]:
        return (
            self.entry_rules
            + self.exit_rules
            + self.stop_loss_rules
            + self.take_profit_rules
            + self.position_rules
            + self.filters
            + self.confirmation_rules
        )
