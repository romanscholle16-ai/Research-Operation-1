"""Structured AI output for the web-research workflow (Phase 6 brief
sections 18/24) - the same "typed decision, closed action set" discipline
as `app/ai/decision.py`'s `ResearchDecision`/`ExperimentProposal`.

`ResearchAction` is a closed enum: discover sources, retrieve one source,
extract evidence from one retrieved source, propose an update to the
working strategy specification, validate it, or stop. There is no action
(and no field anywhere in this module) that could express "run a shell
command", "write a file", "change my limits", or "place a trade" - the
schema itself is the enforcement, not a prompt asking the model to behave.

Any rule the AI proposes via `update_specification` is tagged
`RuleStatus.INTERPRETED` by `app/research/agent.py` when it applies the
update - never `EXPLICIT`. `EXPLICIT` is reserved for evidence quotes
(`evidence.py`) and for a specification assembled by something that
deterministically maps a quote to structure, which Phase 6 does not
attempt (see ARCHITECTURE.md "Phase 6" for why).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.research.specification import Condition, IndicatorSpec


class ResearchAction(str, Enum):
    DISCOVER_SOURCES = "discover_sources"
    RETRIEVE_SOURCE = "retrieve_source"
    EXTRACT_EVIDENCE = "extract_evidence"
    UPDATE_SPECIFICATION = "update_specification"
    VALIDATE_SPECIFICATION = "validate_specification"
    STOP = "stop"


@dataclass(frozen=True)
class ProposedRule:
    rule_kind: str  # "entry" | "exit" | "stop_loss" | "take_profit" | "filter" | "confirmation" | "position"
    description: str
    side: str | None = None
    condition: Condition | None = None
    value: float | None = None
    value_type: str | None = None
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SpecificationUpdate:
    name: str | None = None
    timeframe: str | None = None
    market: str | None = None
    instrument: str | None = None
    session: str | None = None
    indicators: tuple[IndicatorSpec, ...] = ()
    rules: tuple[ProposedRule, ...] = ()
    unknowns: tuple[str, ...] = ()
    ambiguities: tuple[str, ...] = ()


@dataclass(frozen=True)
class WebResearchDecision:
    objective: str
    reasoning_summary: str
    action: ResearchAction
    query: str | None = None  # DISCOVER_SOURCES
    url: str | None = None  # RETRIEVE_SOURCE
    source_id: str | None = None  # EXTRACT_EVIDENCE
    specification_update: SpecificationUpdate | None = None  # UPDATE_SPECIFICATION
    stopping_reason: str | None = None  # STOP (or an early-stop alongside any action)
