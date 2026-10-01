import pytest

from app.ai.provider import AIProviderResponseError
from app.ai.providers.structured_output import experiment_proposal_from_dict, research_decision_from_dict


def test_parses_a_minimal_valid_decision() -> None:
    decision = research_decision_from_dict(
        {"objective": "o", "hypothesis": "h", "reasoning_summary": "r"}
    )
    assert decision.objective == "o"
    assert decision.requested_experiments == ()
    assert decision.stopping_reason is None


def test_parses_a_full_decision_with_proposals() -> None:
    decision = research_decision_from_dict(
        {
            "objective": "o",
            "hypothesis": "h",
            "reasoning_summary": "r",
            "requested_experiments": [
                {"research_system": "parameter_explorer", "parameter_space": {"qty": [1.0, 2.0]}},
                {"research_system": "rule_explorer", "rule_variant_names": ["a", "b"], "reason": "why not"},
            ],
            "analysis_tasks": ["check drawdown"],
            "stopping_reason": None,
            "confidence": 0.75,
        }
    )
    assert len(decision.requested_experiments) == 2
    assert decision.requested_experiments[0].parameter_space == {"qty": [1.0, 2.0]}
    assert decision.requested_experiments[1].rule_variant_names == ("a", "b")
    assert decision.requested_experiments[1].reason == "why not"
    assert decision.analysis_tasks == ("check drawdown",)
    assert decision.confidence == 0.75


@pytest.mark.parametrize("missing", ["objective", "hypothesis", "reasoning_summary"])
def test_rejects_missing_required_field(missing: str) -> None:
    data = {"objective": "o", "hypothesis": "h", "reasoning_summary": "r"}
    del data[missing]
    with pytest.raises(AIProviderResponseError):
        research_decision_from_dict(data)


def test_rejects_non_dict_top_level() -> None:
    with pytest.raises(AIProviderResponseError):
        research_decision_from_dict(["not", "a", "dict"])


def test_rejects_requested_experiments_not_a_list() -> None:
    with pytest.raises(AIProviderResponseError):
        research_decision_from_dict(
            {"objective": "o", "hypothesis": "h", "reasoning_summary": "r", "requested_experiments": "nope"}
        )


def test_rejects_malformed_nested_proposal_without_dropping_it_silently() -> None:
    with pytest.raises(AIProviderResponseError):
        research_decision_from_dict(
            {
                "objective": "o",
                "hypothesis": "h",
                "reasoning_summary": "r",
                "requested_experiments": [{"not_research_system": "oops"}],
            }
        )


def test_rejects_wrong_typed_confidence() -> None:
    with pytest.raises(AIProviderResponseError):
        research_decision_from_dict(
            {"objective": "o", "hypothesis": "h", "reasoning_summary": "r", "confidence": "high"}
        )


def test_rejects_wrong_typed_stopping_reason() -> None:
    with pytest.raises(AIProviderResponseError):
        research_decision_from_dict(
            {"objective": "o", "hypothesis": "h", "reasoning_summary": "r", "stopping_reason": 123}
        )


def test_proposal_requires_research_system() -> None:
    with pytest.raises(AIProviderResponseError):
        experiment_proposal_from_dict({"reason": "no system named"})


def test_proposal_parameter_space_must_map_to_lists() -> None:
    with pytest.raises(AIProviderResponseError):
        experiment_proposal_from_dict({"research_system": "parameter_explorer", "parameter_space": {"qty": 5}})


def test_proposal_rejects_non_dict_item() -> None:
    with pytest.raises(AIProviderResponseError):
        research_decision_from_dict(
            {"objective": "o", "hypothesis": "h", "reasoning_summary": "r", "requested_experiments": ["not a dict"]}
        )


def test_hypothesis_containing_code_like_text_is_treated_as_inert_data() -> None:
    """Provider output is data, never executable (Phase 5 brief section 19)."""
    decision = research_decision_from_dict(
        {
            "objective": "o",
            "hypothesis": "__import__('os').system('echo pwned')",
            "reasoning_summary": "r",
        }
    )
    assert decision.hypothesis == "__import__('os').system('echo pwned')"
