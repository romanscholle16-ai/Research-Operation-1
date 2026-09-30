"""Each `RuleVariant` names one explicit, pre-built structural
alternative - its own `strategy_factory`, not a parameter to a shared
one. This is what keeps the explorer "explicit strategy variants rather
than allowing arbitrary uncontrolled code generation" (Phase 3 brief):
a variant's logic is authored ahead of time by whoever calls this
system, never synthesized here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.backtesting.strategy import Strategy
from app.systems.base import ResearchRequest, ResearchSystem
from app.systems.experiment import ExperimentDefinition


@dataclass(frozen=True)
class RuleVariant:
    name: str
    strategy_factory: Callable[[dict[str, Any]], Strategy]
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuleExplorerRequest(ResearchRequest):
    variants: tuple[RuleVariant, ...] = ()

    def __post_init__(self) -> None:
        if not self.variants:
            raise ValueError("RuleExplorerRequest requires at least one variant")


class RuleExplorer(ResearchSystem):
    name = "rule_explorer"

    def generate_experiments(self, request: RuleExplorerRequest) -> list[ExperimentDefinition]:
        experiments = []
        for variant in request.variants:
            experiments.append(
                ExperimentDefinition(
                    research_system=self.name,
                    strategy_name=request.strategy_name,
                    strategy_version=request.strategy_version,
                    strategy_factory=variant.strategy_factory,
                    parameters=dict(request.base_parameters),
                    candles=request.candles,
                    execution_config=request.execution_config,
                    higher_timeframes=request.higher_timeframes,
                    rule_configuration={
                        "variant_name": variant.name,
                        "description": variant.description,
                        **variant.metadata,
                    },
                    parent_experiment_id=request.parent_experiment_id,
                )
            )
        return experiments
