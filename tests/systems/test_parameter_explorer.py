from app.backtesting.engine import BacktestConfig
from app.backtesting.market_data import Timeframe
from app.systems.parameter_explorer import ParameterExplorer, ParameterExplorerRequest
from app.systems.parameter_space import ParameterSpace, ValueList
from tests.fixtures.mock_strategies import FixedTradeStrategy
from tests.fixtures.synthetic_data import build_series

ROWS = [
    (100, 101, 99, 100, 1000),
    (100, 105, 100, 104, 1000),
    (104, 110, 103, 108, 1000),
    (108, 109, 107, 108, 1000),
]


def _request(**overrides) -> ParameterExplorerRequest:
    defaults = dict(
        strategy_name="fixed_trade",
        strategy_version="1",
        strategy_factory=lambda p: FixedTradeStrategy(p),
        candles=build_series(ROWS),
        execution_config=BacktestConfig(symbol="TEST/USDT", timeframe=Timeframe.M1, starting_capital=10_000.0),
        parameter_space=ParameterSpace({"qty": ValueList([1.0, 2.0, 3.0])}),
    )
    defaults.update(overrides)
    return ParameterExplorerRequest(**defaults)


def test_generates_one_experiment_per_combination() -> None:
    experiments = ParameterExplorer().generate_experiments(_request())
    assert len(experiments) == 3
    assert {e.parameters["qty"] for e in experiments} == {1.0, 2.0, 3.0}


def test_experiments_have_unique_ids() -> None:
    experiments = ParameterExplorer().generate_experiments(_request())
    assert len({e.id for e in experiments}) == len(experiments)


def test_research_system_name_is_recorded() -> None:
    experiments = ParameterExplorer().generate_experiments(_request())
    assert all(e.research_system == "parameter_explorer" for e in experiments)


def test_does_not_hardcode_a_strategy() -> None:
    # Generic over whatever strategy_factory the caller supplies.
    calls = []
    experiments = ParameterExplorer().generate_experiments(
        _request(strategy_factory=lambda p: calls.append(p) or FixedTradeStrategy(p))
    )
    for e in experiments:
        e.build_strategy()
    assert calls == [{"qty": 1.0}, {"qty": 2.0}, {"qty": 3.0}]


def test_base_parameters_are_merged_with_combination() -> None:
    experiments = ParameterExplorer().generate_experiments(
        _request(base_parameters={"side": "short"}, parameter_space=ParameterSpace({"qty": ValueList([1.0])}))
    )
    assert experiments[0].parameters == {"side": "short", "qty": 1.0}


def test_rule_configuration_is_empty_for_pure_parameter_sweep() -> None:
    experiments = ParameterExplorer().generate_experiments(_request())
    assert all(e.rule_configuration == {} for e in experiments)


def test_no_configured_parameter_space_yields_no_experiments() -> None:
    experiments = ParameterExplorer().generate_experiments(
        _request(parameter_space=ParameterSpace({"qty": ValueList([])}))
    )
    assert experiments == []
