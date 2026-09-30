from app.ai.decision import ExperimentProposal
from app.ai.translation import proposal_to_experiment_definitions
from tests.ai.conftest import make_catalog


def test_parameter_explorer_translation() -> None:
    catalog = make_catalog()
    proposal = ExperimentProposal(
        research_system="parameter_explorer", parameter_space={"qty": [1.0, 2.0]}, base_parameters={"side": "long"}
    )
    definitions = proposal_to_experiment_definitions(proposal, catalog)
    assert len(definitions) == 2
    assert {d.parameters["qty"] for d in definitions} == {1.0, 2.0}
    assert all(d.parameters["side"] == "long" for d in definitions)
    assert all(d.research_system == "parameter_explorer" for d in definitions)


def test_rule_explorer_translation_uses_catalog_variants() -> None:
    catalog = make_catalog()
    proposal = ExperimentProposal(research_system="rule_explorer", rule_variant_names=("long_only", "short_only"))
    definitions = proposal_to_experiment_definitions(proposal, catalog)
    assert len(definitions) == 2
    sides = {d.build_strategy().side for d in definitions}
    assert sides == {"long", "short"}


def test_risk_execution_translation_uses_catalog_variants() -> None:
    catalog = make_catalog()
    proposal = ExperimentProposal(research_system="risk_execution", execution_variant_names=("baseline",))
    definitions = proposal_to_experiment_definitions(proposal, catalog)
    assert len(definitions) == 1
    assert definitions[0].rule_configuration["execution_variant"] == "baseline"


def test_market_conditions_translation_chronological_chunks() -> None:
    catalog = make_catalog()
    proposal = ExperimentProposal(
        research_system="market_conditions", segment_specs=({"method": "chronological_chunks", "chunk_count": 2},)
    )
    definitions = proposal_to_experiment_definitions(proposal, catalog)
    assert len(definitions) == 2
    assert all(d.rule_configuration["segmentation_method"] == "chronological_chunks" for d in definitions)


def test_market_conditions_translation_multiple_specs_accumulate() -> None:
    catalog = make_catalog()
    proposal = ExperimentProposal(
        research_system="market_conditions",
        segment_specs=({"method": "volatility"}, {"method": "day_of_week"}),
    )
    definitions = proposal_to_experiment_definitions(proposal, catalog)
    methods = {d.rule_configuration["segmentation_method"] for d in definitions}
    assert methods == {"volatility_median_split", "day_of_week"}


def test_adversarial_translation_builds_config_from_simple_values() -> None:
    catalog = make_catalog()
    proposal = ExperimentProposal(
        research_system="adversarial",
        adversarial={"worse_fee_rate": 0.01, "worse_slippage_bps": 25, "leave_out_chunk_count": 0},
    )
    definitions = proposal_to_experiment_definitions(proposal, catalog)
    variants = {d.rule_configuration["adversarial_variant"] for d in definitions}
    assert variants == {"baseline", "worse_fees", "worse_slippage"}
    fee_def = next(d for d in definitions if d.rule_configuration["adversarial_variant"] == "worse_fees")
    assert fee_def.execution_config.fee_model.rate == 0.01
    slip_def = next(d for d in definitions if d.rule_configuration["adversarial_variant"] == "worse_slippage")
    assert slip_def.execution_config.slippage_model.bps == 25


def test_adversarial_translation_defaults_to_baseline_only() -> None:
    catalog = make_catalog()
    proposal = ExperimentProposal(research_system="adversarial", adversarial={})
    definitions = proposal_to_experiment_definitions(proposal, catalog)
    assert len(definitions) == 1
    assert definitions[0].rule_configuration["adversarial_variant"] == "baseline"


def test_translation_never_calls_run_backtest_itself() -> None:
    # See tests/ai/test_safety.py for the AST-based, docstring-safe
    # version of this check applied to the whole app/ai package.
    import inspect

    import app.ai.translation as translation_module

    for name, obj in vars(translation_module).items():
        if inspect.isfunction(obj) and obj.__module__ == translation_module.__name__:
            assert "run_backtest" not in obj.__code__.co_names
