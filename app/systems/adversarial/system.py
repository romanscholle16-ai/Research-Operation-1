from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any

from app.backtesting.costs import FeeModel, SlippageModel
from app.systems.base import ResearchRequest, ResearchSystem
from app.systems.experiment import ExperimentDefinition
from app.systems.market_conditions.segmentation import segment_leave_one_out_chronological


@dataclass(frozen=True)
class AdversarialConfig:
    include_baseline: bool = True
    worse_fee_model: FeeModel | None = None
    worse_slippage_model: SlippageModel | None = None
    # param name -> alternate values to test one-at-a-time, holding all other params at base
    parameter_jitter: dict[str, list[Any]] = field(default_factory=dict)
    # 0 disables; otherwise splits candles into this many chunks and tests
    # dropping each one in turn ("does performance depend on one period")
    leave_out_chunk_count: int = 0


@dataclass(frozen=True)
class AdversarialRequest(ResearchRequest):
    config: AdversarialConfig = field(default_factory=AdversarialConfig)


class AdversarialResearchSystem(ResearchSystem):
    """Prioritizes robustness testing over optimization - this system
    never picks a "best" configuration; it only produces the set of
    perturbed experiments a human or later qualification system compares
    against the baseline."""

    name = "adversarial"

    def generate_experiments(self, request: AdversarialRequest) -> list[ExperimentDefinition]:
        config = request.config
        experiments: list[ExperimentDefinition] = []
        baseline_id: str | None = None

        if config.include_baseline:
            baseline = ExperimentDefinition(
                research_system=self.name,
                strategy_name=request.strategy_name,
                strategy_version=request.strategy_version,
                strategy_factory=request.strategy_factory,
                parameters=dict(request.base_parameters),
                candles=request.candles,
                execution_config=request.execution_config,
                higher_timeframes=request.higher_timeframes,
                rule_configuration={"adversarial_variant": "baseline"},
                parent_experiment_id=request.parent_experiment_id,
            )
            experiments.append(baseline)
            baseline_id = baseline.id

        parent_id = baseline_id or request.parent_experiment_id

        if config.worse_fee_model is not None:
            experiments.append(
                ExperimentDefinition(
                    research_system=self.name,
                    strategy_name=request.strategy_name,
                    strategy_version=request.strategy_version,
                    strategy_factory=request.strategy_factory,
                    parameters=dict(request.base_parameters),
                    candles=request.candles,
                    execution_config=dataclasses.replace(request.execution_config, fee_model=config.worse_fee_model),
                    higher_timeframes=request.higher_timeframes,
                    rule_configuration={"adversarial_variant": "worse_fees"},
                    parent_experiment_id=parent_id,
                )
            )

        if config.worse_slippage_model is not None:
            experiments.append(
                ExperimentDefinition(
                    research_system=self.name,
                    strategy_name=request.strategy_name,
                    strategy_version=request.strategy_version,
                    strategy_factory=request.strategy_factory,
                    parameters=dict(request.base_parameters),
                    candles=request.candles,
                    execution_config=dataclasses.replace(
                        request.execution_config, slippage_model=config.worse_slippage_model
                    ),
                    higher_timeframes=request.higher_timeframes,
                    rule_configuration={"adversarial_variant": "worse_slippage"},
                    parent_experiment_id=parent_id,
                )
            )

        for param_name, jittered_values in config.parameter_jitter.items():
            for value in jittered_values:
                parameters = {**request.base_parameters, param_name: value}
                experiments.append(
                    ExperimentDefinition(
                        research_system=self.name,
                        strategy_name=request.strategy_name,
                        strategy_version=request.strategy_version,
                        strategy_factory=request.strategy_factory,
                        parameters=parameters,
                        candles=request.candles,
                        execution_config=request.execution_config,
                        higher_timeframes=request.higher_timeframes,
                        rule_configuration={
                            "adversarial_variant": "parameter_jitter",
                            "parameter": param_name,
                            "value": value,
                        },
                        parent_experiment_id=parent_id,
                    )
                )

        if config.leave_out_chunk_count > 0:
            for segment in segment_leave_one_out_chronological(request.candles, config.leave_out_chunk_count):
                experiments.append(
                    ExperimentDefinition(
                        research_system=self.name,
                        strategy_name=request.strategy_name,
                        strategy_version=request.strategy_version,
                        strategy_factory=request.strategy_factory,
                        parameters=dict(request.base_parameters),
                        candles=segment.candles,
                        execution_config=request.execution_config,
                        higher_timeframes=request.higher_timeframes,
                        rule_configuration={
                            "adversarial_variant": "leave_one_out",
                            "segment_label": segment.label,
                        },
                        parent_experiment_id=parent_id,
                    )
                )

        return experiments
