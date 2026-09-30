"""Turns a validated `ExperimentProposal` into `ExperimentDefinition`s by
building the matching Phase 3 `ResearchRequest` subtype and calling that
system's `generate_experiments()` UNCHANGED - this module never builds
an `ExperimentDefinition` by hand and never calls `run_backtest()`. That
is what keeps AI-generated experiment configurations normalized the same
way any human-constructed request would be (Phase 4 brief section 19):
fingerprinting, deduplication, and execution all go through the exact
same Phase 3 code path regardless of who produced the `ResearchRequest`.

Callers must run `validate_proposal()` (validation.py) first - this
module assumes a valid proposal and will raise `KeyError`/`ValueError`
on a malformed one rather than defending against it a second time.
"""

from __future__ import annotations

from app.ai.catalog import ResearchCatalog
from app.ai.decision import ExperimentProposal
from app.backtesting.costs import FixedBpsSlippageModel, PercentageFeeModel
from app.systems.adversarial import AdversarialConfig, AdversarialRequest, AdversarialResearchSystem
from app.systems.experiment import ExperimentDefinition
from app.systems.market_conditions import (
    MarketConditionRequest,
    MarketConditionTester,
    segment_by_chronological_chunks,
    segment_by_day_of_week,
    segment_by_volatility,
)
from app.systems.parameter_explorer import ParameterExplorer, ParameterExplorerRequest
from app.systems.parameter_space import ParameterSpace, ValueList
from app.systems.risk_execution import RiskExecutionOptimizer, RiskExecutionRequest
from app.systems.rule_explorer import RuleExplorer, RuleExplorerRequest

_SEGMENTATION_FUNCTIONS = {
    "chronological_chunks": lambda candles, spec: segment_by_chronological_chunks(
        candles, spec["chunk_count"]
    ),
    "volatility": lambda candles, spec: segment_by_volatility(candles),
    "day_of_week": lambda candles, spec: segment_by_day_of_week(candles),
}


def proposal_to_experiment_definitions(
    proposal: ExperimentProposal, catalog: ResearchCatalog
) -> list[ExperimentDefinition]:
    if proposal.research_system == "parameter_explorer":
        request = ParameterExplorerRequest(
            strategy_name=catalog.strategy_name,
            strategy_version=catalog.strategy_version,
            strategy_factory=catalog.strategy_factory,
            candles=catalog.candles,
            execution_config=catalog.execution_config,
            higher_timeframes=catalog.higher_timeframes,
            base_parameters=proposal.base_parameters,
            parameter_space=ParameterSpace(
                {name: ValueList(values) for name, values in (proposal.parameter_space or {}).items()}
            ),
        )
        return ParameterExplorer().generate_experiments(request)

    if proposal.research_system == "rule_explorer":
        variants = tuple(catalog.rule_variants[name] for name in proposal.rule_variant_names or ())
        request = RuleExplorerRequest(
            strategy_name=catalog.strategy_name,
            strategy_version=catalog.strategy_version,
            strategy_factory=catalog.strategy_factory,
            candles=catalog.candles,
            execution_config=catalog.execution_config,
            higher_timeframes=catalog.higher_timeframes,
            base_parameters=proposal.base_parameters,
            variants=variants,
        )
        return RuleExplorer().generate_experiments(request)

    if proposal.research_system == "risk_execution":
        variants = tuple(
            catalog.execution_variants[name] for name in proposal.execution_variant_names or ()
        )
        request = RiskExecutionRequest(
            strategy_name=catalog.strategy_name,
            strategy_version=catalog.strategy_version,
            strategy_factory=catalog.strategy_factory,
            candles=catalog.candles,
            execution_config=catalog.execution_config,
            higher_timeframes=catalog.higher_timeframes,
            base_parameters=proposal.base_parameters,
            variants=variants,
        )
        return RiskExecutionOptimizer().generate_experiments(request)

    if proposal.research_system == "market_conditions":
        segments = []
        for spec in proposal.segment_specs or ():
            segments.extend(_SEGMENTATION_FUNCTIONS[spec["method"]](catalog.candles, spec))
        request = MarketConditionRequest(
            strategy_name=catalog.strategy_name,
            strategy_version=catalog.strategy_version,
            strategy_factory=catalog.strategy_factory,
            candles=catalog.candles,
            execution_config=catalog.execution_config,
            higher_timeframes=catalog.higher_timeframes,
            base_parameters=proposal.base_parameters,
            segments=tuple(segments),
        )
        return MarketConditionTester().generate_experiments(request)

    if proposal.research_system == "adversarial":
        adv = proposal.adversarial or {}
        config = AdversarialConfig(
            include_baseline=adv.get("include_baseline", True),
            worse_fee_model=(
                PercentageFeeModel(rate=adv["worse_fee_rate"]) if "worse_fee_rate" in adv else None
            ),
            worse_slippage_model=(
                FixedBpsSlippageModel(bps=adv["worse_slippage_bps"])
                if "worse_slippage_bps" in adv
                else None
            ),
            parameter_jitter=adv.get("parameter_jitter", {}),
            leave_out_chunk_count=adv.get("leave_out_chunk_count", 0),
        )
        request = AdversarialRequest(
            strategy_name=catalog.strategy_name,
            strategy_version=catalog.strategy_version,
            strategy_factory=catalog.strategy_factory,
            candles=catalog.candles,
            execution_config=catalog.execution_config,
            higher_timeframes=catalog.higher_timeframes,
            base_parameters=proposal.base_parameters,
            config=config,
        )
        return AdversarialResearchSystem().generate_experiments(request)

    raise ValueError(f"unknown research_system {proposal.research_system!r}")
