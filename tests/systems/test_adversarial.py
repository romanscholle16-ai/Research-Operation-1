from app.backtesting.costs import FixedBpsSlippageModel, PercentageFeeModel, ZeroFeeModel
from app.backtesting.engine import BacktestConfig
from app.backtesting.market_data import Timeframe
from app.systems.adversarial import AdversarialConfig, AdversarialRequest, AdversarialResearchSystem
from tests.fixtures.mock_strategies import FixedTradeStrategy
from tests.fixtures.synthetic_data import build_series

ROWS = [(100 + i, 105 + i, 95 + i, 100 + i, 1000) for i in range(12)]


def _request(config: AdversarialConfig, **overrides) -> AdversarialRequest:
    defaults = dict(
        strategy_name="fixed_trade",
        strategy_version="1",
        strategy_factory=lambda p: FixedTradeStrategy(p),
        candles=build_series(ROWS),
        execution_config=BacktestConfig(
            symbol="TEST/USDT", timeframe=Timeframe.M1, starting_capital=10_000.0, fee_model=ZeroFeeModel()
        ),
        config=config,
    )
    defaults.update(overrides)
    return AdversarialRequest(**defaults)


def test_baseline_included_by_default() -> None:
    experiments = AdversarialResearchSystem().generate_experiments(_request(AdversarialConfig()))
    assert len(experiments) == 1
    assert experiments[0].rule_configuration == {"adversarial_variant": "baseline"}


def test_baseline_can_be_excluded() -> None:
    experiments = AdversarialResearchSystem().generate_experiments(
        _request(AdversarialConfig(include_baseline=False))
    )
    assert experiments == []


def test_worse_fee_and_slippage_variants() -> None:
    config = AdversarialConfig(
        worse_fee_model=PercentageFeeModel(rate=0.01),
        worse_slippage_model=FixedBpsSlippageModel(bps=100),
    )
    experiments = AdversarialResearchSystem().generate_experiments(_request(config))
    variants = {e.rule_configuration["adversarial_variant"] for e in experiments}
    assert variants == {"baseline", "worse_fees", "worse_slippage"}

    fee_exp = next(e for e in experiments if e.rule_configuration["adversarial_variant"] == "worse_fees")
    assert fee_exp.execution_config.fee_model.rate == 0.01
    slip_exp = next(e for e in experiments if e.rule_configuration["adversarial_variant"] == "worse_slippage")
    assert slip_exp.execution_config.slippage_model.bps == 100


def test_parameter_jitter_generates_one_experiment_per_value() -> None:
    config = AdversarialConfig(include_baseline=False, parameter_jitter={"qty": [0.5, 1.5, 2.0]})
    experiments = AdversarialResearchSystem().generate_experiments(
        _request(config, base_parameters={"qty": 1.0, "side": "long"})
    )
    assert len(experiments) == 3
    values = sorted(e.rule_configuration["value"] for e in experiments)
    assert values == [0.5, 1.5, 2.0]
    for e in experiments:
        assert e.rule_configuration["adversarial_variant"] == "parameter_jitter"
        assert e.rule_configuration["parameter"] == "qty"
        assert e.parameters["side"] == "long"  # other base params preserved
        assert e.parameters["qty"] == e.rule_configuration["value"]


def test_leave_one_out_generates_one_experiment_per_chunk() -> None:
    config = AdversarialConfig(include_baseline=False, leave_out_chunk_count=4)
    experiments = AdversarialResearchSystem().generate_experiments(_request(config))
    assert len(experiments) == 4
    for e in experiments:
        assert e.rule_configuration["adversarial_variant"] == "leave_one_out"
        assert len(e.candles) == 9  # 12 candles - 3 dropped per chunk


def test_variants_are_children_of_the_baseline() -> None:
    config = AdversarialConfig(
        worse_fee_model=PercentageFeeModel(rate=0.01),
        parameter_jitter={"qty": [2.0]},
        leave_out_chunk_count=2,
    )
    experiments = AdversarialResearchSystem().generate_experiments(_request(config))
    baseline = next(e for e in experiments if e.rule_configuration["adversarial_variant"] == "baseline")
    for e in experiments:
        if e.id == baseline.id:
            continue
        assert e.parent_experiment_id == baseline.id


def test_never_computes_a_best_result_it_only_generates_experiments() -> None:
    # The system's public surface has no notion of "best"/ranking - it
    # only returns the plan of experiments to run.
    assert not hasattr(AdversarialResearchSystem(), "best_result")
    assert not hasattr(AdversarialResearchSystem(), "optimize")
