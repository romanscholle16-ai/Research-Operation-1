from app.systems.parameter_space import Categorical, Fixed, ParameterSpace, ValueList, ValueRange


def test_fixed_values() -> None:
    assert Fixed(5).values() == [5]


def test_value_list_preserves_order() -> None:
    assert ValueList([3, 1, 2]).values() == [3, 1, 2]


def test_value_range_inclusive_of_stop() -> None:
    assert ValueRange(10, 30, 10).values() == [10, 20, 30]


def test_value_range_non_integer_step() -> None:
    assert ValueRange(1.0, 2.0, 0.5).values() == [1.0, 1.5, 2.0]


def test_value_range_rejects_zero_step() -> None:
    import pytest

    with pytest.raises(ValueError):
        ValueRange(0, 10, 0).values()


def test_categorical_values() -> None:
    assert Categorical(["a", "b", "c"]).values() == ["a", "b", "c"]


def test_empty_parameter_space_yields_single_empty_combination() -> None:
    assert ParameterSpace({}).generate_combinations() == [{}]


def test_generate_combinations_is_deterministic_cartesian_product() -> None:
    space = ParameterSpace({"period": ValueList([10, 20]), "stop": ValueList([1.0, 1.5, 2.0])})
    combos = space.generate_combinations()
    assert len(combos) == 6
    # sorted key order (period before stop) determines iteration order
    assert combos[0] == {"period": 10, "stop": 1.0}
    assert combos[-1] == {"period": 20, "stop": 2.0}


def test_generate_combinations_repeated_calls_are_identical() -> None:
    space = ParameterSpace({"a": ValueList([1, 2]), "b": Categorical(["x", "y"])})
    assert space.generate_combinations() == space.generate_combinations()


def test_fixed_parameter_does_not_expand_combinations() -> None:
    space = ParameterSpace({"period": ValueList([10, 20]), "risk_pct": Fixed(1.0)})
    combos = space.generate_combinations()
    assert len(combos) == 2
    assert all(c["risk_pct"] == 1.0 for c in combos)
