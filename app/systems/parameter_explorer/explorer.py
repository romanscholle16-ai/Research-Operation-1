from __future__ import annotations

from dataclasses import dataclass

from app.systems.base import ResearchRequest, ResearchSystem
from app.systems.experiment import ExperimentDefinition
from app.systems.parameter_space import ParameterSpace


@dataclass(frozen=True)
class ParameterExplorerRequest(ResearchRequest):
    parameter_space: ParameterSpace = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.parameter_space is None:
            raise ValueError("ParameterExplorerRequest requires parameter_space")


class ParameterExplorer(ResearchSystem):
    name = "parameter_explorer"

    def generate_experiments(self, request: ParameterExplorerRequest) -> list[ExperimentDefinition]:
        combinations = request.parameter_space.generate_combinations()
        experiments = []
        for combo in combinations:
            parameters = {**request.base_parameters, **combo}
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
                    rule_configuration={},
                    parent_experiment_id=request.parent_experiment_id,
                )
            )
        return experiments
