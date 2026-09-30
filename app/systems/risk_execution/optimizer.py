from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any

from app.backtesting.costs import FeeModel, SlippageModel
from app.backtesting.intrabar import IntrabarPolicy
from app.systems.base import ResearchRequest, ResearchSystem
from app.systems.experiment import ExperimentDefinition


@dataclass(frozen=True)
class ExecutionVariant:
    """One execution/risk assumption set to test. `None` on any field
    means "keep whatever the request's base `execution_config` already
    has" - a variant only needs to name what it changes."""

    name: str
    fee_model: FeeModel | None = None
    slippage_model: SlippageModel | None = None
    intrabar_policy: IntrabarPolicy | None = None
    starting_capital: float | None = None
    description: str = ""


@dataclass(frozen=True)
class RiskExecutionRequest(ResearchRequest):
    variants: tuple[ExecutionVariant, ...] = ()

    def __post_init__(self) -> None:
        if not self.variants:
            raise ValueError("RiskExecutionRequest requires at least one variant")


class RiskExecutionOptimizer(ResearchSystem):
    name = "risk_execution"

    def generate_experiments(self, request: RiskExecutionRequest) -> list[ExperimentDefinition]:
        experiments = []
        for variant in request.variants:
            overrides: dict[str, Any] = {}
            if variant.fee_model is not None:
                overrides["fee_model"] = variant.fee_model
            if variant.slippage_model is not None:
                overrides["slippage_model"] = variant.slippage_model
            if variant.intrabar_policy is not None:
                overrides["intrabar_policy"] = variant.intrabar_policy
            if variant.starting_capital is not None:
                overrides["starting_capital"] = variant.starting_capital
            execution_config = dataclasses.replace(request.execution_config, **overrides)

            experiments.append(
                ExperimentDefinition(
                    research_system=self.name,
                    strategy_name=request.strategy_name,
                    strategy_version=request.strategy_version,
                    strategy_factory=request.strategy_factory,
                    parameters=dict(request.base_parameters),
                    candles=request.candles,
                    execution_config=execution_config,
                    higher_timeframes=request.higher_timeframes,
                    rule_configuration={"execution_variant": variant.name, "description": variant.description},
                    parent_experiment_id=request.parent_experiment_id,
                )
            )
        return experiments
