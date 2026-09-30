"""Deterministic experiment fingerprinting (Phase 3 brief section 9:
deduplication). Reuses Phase 2's `compute_data_identity` and
`ExecutionAssumptions` rather than re-deriving a notion of "same data" or
"same execution assumptions" - the backtesting engine already owns both.

The fingerprint covers every input that could materially change a
backtest's result: research system, strategy identity, resolved
parameters, rule configuration, execution assumptions, data identity, and
timeframe. It deliberately does NOT include the experiment's own `id`,
campaign, or timestamps - those identify the *request*, not the
*configuration*, which is exactly what makes fingerprint equality a valid
duplicate-detection signal.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from app.backtesting.result import ExecutionAssumptions, compute_data_identity

if TYPE_CHECKING:
    from app.systems.experiment import ExperimentDefinition


def compute_experiment_fingerprint(definition: "ExperimentDefinition") -> tuple[str, str]:
    """Return (fingerprint, data_identity)."""
    data_identity = compute_data_identity(definition.candles)
    config = definition.execution_config
    execution_assumptions = ExecutionAssumptions(
        starting_capital=config.starting_capital,
        fee_model=config.fee_model,
        slippage_model=config.slippage_model,
        intrabar_policy=config.intrabar_policy,
    )
    canonical = json.dumps(
        {
            "research_system": definition.research_system,
            "strategy_name": definition.strategy_name,
            "strategy_version": definition.strategy_version,
            "parameters": definition.parameters,
            "rule_configuration": definition.rule_configuration,
            "execution_assumptions": execution_assumptions.to_dict(),
            "data_identity": data_identity,
            "timeframe": config.timeframe.value,
        },
        sort_keys=True,
        default=str,
    )
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return fingerprint, data_identity
