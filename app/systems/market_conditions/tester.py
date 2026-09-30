from __future__ import annotations

from dataclasses import dataclass

from app.systems.base import ResearchRequest, ResearchSystem
from app.systems.experiment import ExperimentDefinition
from app.systems.market_conditions.segmentation import Segment


@dataclass(frozen=True)
class MarketConditionRequest(ResearchRequest):
    """`segments` are pre-built by the caller using segmentation.py's
    functions (mix and match freely - e.g. day-of-week segments plus a
    volatility split in one request)."""

    segments: tuple[Segment, ...] = ()

    def __post_init__(self) -> None:
        if not self.segments:
            raise ValueError("MarketConditionRequest requires at least one segment")


class MarketConditionTester(ResearchSystem):
    name = "market_conditions"

    def generate_experiments(self, request: MarketConditionRequest) -> list[ExperimentDefinition]:
        experiments = []
        for segment in request.segments:
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
                        "segment_label": segment.label,
                        "segmentation_method": segment.method,
                    },
                    parent_experiment_id=request.parent_experiment_id,
                )
            )
        return experiments
