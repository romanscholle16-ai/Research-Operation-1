from app.ai.decision import ExperimentProposal
from app.ai.validation import validate_proposal
from tests.ai.conftest import make_catalog


def test_valid_parameter_explorer_proposal_is_accepted() -> None:
    catalog = make_catalog()
    proposal = ExperimentProposal(research_system="parameter_explorer", parameter_space={"qty": [1.0, 2.0]})
    assert validate_proposal(proposal, catalog) == []


def test_unknown_research_system_is_rejected() -> None:
    catalog = make_catalog()
    proposal = ExperimentProposal(research_system="not_a_real_system")
    errors = validate_proposal(proposal, catalog)
    assert len(errors) == 1
    assert "unknown research_system" in errors[0]


def test_parameter_explorer_requires_parameter_space() -> None:
    catalog = make_catalog()
    errors = validate_proposal(ExperimentProposal(research_system="parameter_explorer"), catalog)
    assert any("parameter_space" in e for e in errors)


def test_parameter_explorer_rejects_empty_value_list() -> None:
    catalog = make_catalog()
    errors = validate_proposal(
        ExperimentProposal(research_system="parameter_explorer", parameter_space={"qty": []}), catalog
    )
    assert any("qty" in e for e in errors)


def test_rule_explorer_rejects_unknown_variant_name() -> None:
    catalog = make_catalog()
    proposal = ExperimentProposal(research_system="rule_explorer", rule_variant_names=("does_not_exist",))
    errors = validate_proposal(proposal, catalog)
    assert any("does_not_exist" in e for e in errors)


def test_rule_explorer_accepts_known_variant_name() -> None:
    catalog = make_catalog()
    proposal = ExperimentProposal(research_system="rule_explorer", rule_variant_names=("long_only",))
    assert validate_proposal(proposal, catalog) == []


def test_rule_explorer_requires_at_least_one_variant() -> None:
    catalog = make_catalog()
    errors = validate_proposal(ExperimentProposal(research_system="rule_explorer"), catalog)
    assert any("rule_variant_name" in e for e in errors)


def test_risk_execution_rejects_unknown_variant_name() -> None:
    catalog = make_catalog()
    proposal = ExperimentProposal(research_system="risk_execution", execution_variant_names=("nope",))
    errors = validate_proposal(proposal, catalog)
    assert any("nope" in e for e in errors)


def test_risk_execution_accepts_known_variant_name() -> None:
    catalog = make_catalog()
    proposal = ExperimentProposal(research_system="risk_execution", execution_variant_names=("baseline",))
    assert validate_proposal(proposal, catalog) == []


def test_market_conditions_rejects_unknown_method() -> None:
    catalog = make_catalog()
    proposal = ExperimentProposal(research_system="market_conditions", segment_specs=({"method": "regime_ml"},))
    errors = validate_proposal(proposal, catalog)
    assert any("unknown segmentation method" in e for e in errors)


def test_market_conditions_chronological_chunks_requires_chunk_count() -> None:
    catalog = make_catalog()
    proposal = ExperimentProposal(
        research_system="market_conditions", segment_specs=({"method": "chronological_chunks"},)
    )
    errors = validate_proposal(proposal, catalog)
    assert any("chunk_count" in e for e in errors)


def test_market_conditions_volatility_needs_no_extra_params() -> None:
    catalog = make_catalog()
    proposal = ExperimentProposal(research_system="market_conditions", segment_specs=({"method": "volatility"},))
    assert validate_proposal(proposal, catalog) == []


def test_adversarial_rejects_unsupported_keys() -> None:
    catalog = make_catalog()
    proposal = ExperimentProposal(research_system="adversarial", adversarial={"delete_everything": True})
    errors = validate_proposal(proposal, catalog)
    assert any("unsupported keys" in e for e in errors)


def test_adversarial_accepts_known_fields() -> None:
    catalog = make_catalog()
    proposal = ExperimentProposal(
        research_system="adversarial",
        adversarial={"worse_fee_rate": 0.01, "leave_out_chunk_count": 2, "parameter_jitter": {"qty": [0.5, 1.5]}},
    )
    assert validate_proposal(proposal, catalog) == []


def test_adversarial_rejects_negative_leave_out_chunk_count() -> None:
    catalog = make_catalog()
    proposal = ExperimentProposal(research_system="adversarial", adversarial={"leave_out_chunk_count": -1})
    errors = validate_proposal(proposal, catalog)
    assert any("leave_out_chunk_count" in e for e in errors)


def test_adversarial_rejects_malformed_parameter_jitter() -> None:
    catalog = make_catalog()
    proposal = ExperimentProposal(research_system="adversarial", adversarial={"parameter_jitter": "not a dict"})
    errors = validate_proposal(proposal, catalog)
    assert any("parameter_jitter" in e for e in errors)
