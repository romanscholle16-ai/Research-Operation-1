"""Deterministic validation of AI-proposed experiments (Phase 4 brief
section 16). Every `ExperimentProposal` is checked against the
`ResearchCatalog` BEFORE it is translated into a `ResearchRequest` - an
invalid proposal never reaches `CampaignRunner`, and nothing here
"repairs" a bad proposal by guessing what the AI meant; it is rejected
with a specific, structured reason instead.
"""

from __future__ import annotations

from app.ai.catalog import ResearchCatalog
from app.ai.decision import ExperimentProposal


class ProposalValidationError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_proposal(proposal: ExperimentProposal, catalog: ResearchCatalog) -> list[str]:
    """Return a list of error strings; empty means valid."""
    errors: list[str] = []

    if proposal.research_system not in ResearchCatalog.KNOWN_RESEARCH_SYSTEMS:
        errors.append(
            f"unknown research_system {proposal.research_system!r}; "
            f"must be one of {ResearchCatalog.KNOWN_RESEARCH_SYSTEMS}"
        )
        return errors  # nothing else can be checked meaningfully

    if not isinstance(proposal.base_parameters, dict):
        errors.append("base_parameters must be a dict")

    if proposal.research_system == "parameter_explorer":
        if not proposal.parameter_space:
            errors.append("parameter_explorer requires a non-empty parameter_space")
        else:
            for name, values in proposal.parameter_space.items():
                if not isinstance(values, list) or len(values) == 0:
                    errors.append(f"parameter_space[{name!r}] must be a non-empty list")

    elif proposal.research_system == "rule_explorer":
        if not proposal.rule_variant_names:
            errors.append("rule_explorer requires at least one rule_variant_name")
        else:
            for name in proposal.rule_variant_names:
                if name not in catalog.rule_variants:
                    errors.append(f"unknown rule variant {name!r}; not in the research catalog")

    elif proposal.research_system == "risk_execution":
        if not proposal.execution_variant_names:
            errors.append("risk_execution requires at least one execution_variant_name")
        else:
            for name in proposal.execution_variant_names:
                if name not in catalog.execution_variants:
                    errors.append(f"unknown execution variant {name!r}; not in the research catalog")

    elif proposal.research_system == "market_conditions":
        if not proposal.segment_specs:
            errors.append("market_conditions requires at least one segment_spec")
        else:
            for spec in proposal.segment_specs:
                method = spec.get("method")
                if method not in ResearchCatalog.KNOWN_SEGMENTATION_METHODS:
                    errors.append(
                        f"unknown segmentation method {method!r}; "
                        f"must be one of {ResearchCatalog.KNOWN_SEGMENTATION_METHODS}"
                    )
                elif method == "chronological_chunks":
                    chunk_count = spec.get("chunk_count")
                    if not isinstance(chunk_count, int) or chunk_count < 1:
                        errors.append("chronological_chunks segment_spec requires integer chunk_count >= 1")

    elif proposal.research_system == "adversarial":
        adv = proposal.adversarial or {}
        allowed_keys = {
            "include_baseline",
            "worse_fee_rate",
            "worse_slippage_bps",
            "parameter_jitter",
            "leave_out_chunk_count",
        }
        unknown_keys = set(adv.keys()) - allowed_keys
        if unknown_keys:
            errors.append(f"adversarial proposal has unsupported keys: {sorted(unknown_keys)}")
        leave_out = adv.get("leave_out_chunk_count")
        if leave_out is not None and (not isinstance(leave_out, int) or leave_out < 0):
            errors.append("adversarial.leave_out_chunk_count must be a non-negative integer")
        jitter = adv.get("parameter_jitter")
        if jitter is not None:
            if not isinstance(jitter, dict) or not all(isinstance(v, list) for v in jitter.values()):
                errors.append("adversarial.parameter_jitter must be a dict of param_name -> list of values")

    return errors
