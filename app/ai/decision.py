"""Structured AI output (Phase 4 brief section 6). No free-form AI text
is ever used as the internal control protocol - a provider must return a
`ResearchDecision`, and everything inside it is typed and JSON-safe (so
it can be persisted, logged, and validated deterministically).

`ExperimentProposal` is deliberately NOT a `ResearchRequest` - a
`ResearchRequest` carries live objects (a `CandleSeries`, a
`Callable` strategy factory) that an AI cannot produce as data. A
proposal instead names WHAT to vary (a research system, plus simple
JSON-safe values) and, for anything that requires actual logic (a rule
variant's strategy factory, an execution variant's cost models), picks
by NAME from a pre-registered `ResearchCatalog` (catalog.py) that a
human assembled ahead of time - never something the AI authors itself.
See translation.py for how a proposal becomes real `ExperimentDefinition`s
via the existing Phase 3 research systems, unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ExperimentProposal:
    research_system: str
    reason: str = ""
    base_parameters: dict[str, Any] = field(default_factory=dict)

    # parameter_explorer: {param_name: [values...]}
    parameter_space: dict[str, list[Any]] | None = None

    # rule_explorer: names must exist in ResearchCatalog.rule_variants
    rule_variant_names: tuple[str, ...] | None = None

    # risk_execution: names must exist in ResearchCatalog.execution_variants
    execution_variant_names: tuple[str, ...] | None = None

    # market_conditions: [{"method": "chronological_chunks", "chunk_count": 4}, ...]
    segment_specs: tuple[dict[str, Any], ...] | None = None

    # adversarial: simple JSON-safe subset of AdversarialConfig's fields
    adversarial: dict[str, Any] | None = None


@dataclass(frozen=True)
class ResearchDecision:
    """One AI turn: a hypothesis, the experiments it wants run to test
    it, and (optionally) a reason to stop the whole research session."""

    objective: str
    hypothesis: str
    reasoning_summary: str
    requested_experiments: tuple[ExperimentProposal, ...] = ()
    analysis_tasks: tuple[str, ...] = ()
    stopping_reason: str | None = None
    confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "hypothesis": self.hypothesis,
            "reasoning_summary": self.reasoning_summary,
            "requested_experiments": [
                {
                    "research_system": p.research_system,
                    "reason": p.reason,
                    "base_parameters": p.base_parameters,
                    "parameter_space": p.parameter_space,
                    "rule_variant_names": list(p.rule_variant_names) if p.rule_variant_names else None,
                    "execution_variant_names": list(p.execution_variant_names) if p.execution_variant_names else None,
                    "segment_specs": list(p.segment_specs) if p.segment_specs else None,
                    "adversarial": p.adversarial,
                }
                for p in self.requested_experiments
            ],
            "analysis_tasks": list(self.analysis_tasks),
            "stopping_reason": self.stopping_reason,
            "confidence": self.confidence,
        }
