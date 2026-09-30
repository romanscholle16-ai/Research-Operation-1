from app.backtesting.costs import PercentageFeeModel, ZeroFeeModel, ZeroSlippageModel
from app.backtesting.engine import BacktestConfig, run_backtest
from app.backtesting.intrabar import IntrabarPolicy
from app.backtesting.market_data import Timeframe
from app.backtesting.result import ExecutionAssumptions, compute_data_identity, compute_fingerprint
from app.backtesting.signals import Signal, SignalAction
from tests.fixtures.mock_strategies import ScriptedStrategy
from tests.fixtures.synthetic_data import build_series

ROWS = [
    (100, 101, 99, 100, 1000),
    (100, 105, 100, 104, 1000),
    (104, 110, 103, 108, 1000),
    (108, 109, 107, 108, 1000),
]


def _config(**overrides) -> BacktestConfig:
    defaults = dict(symbol="TEST/USDT", timeframe=Timeframe.M1, starting_capital=10_000.0)
    defaults.update(overrides)
    return BacktestConfig(**defaults)


def _script(series):
    return {
        0: [Signal(SignalAction.OPEN_LONG, timestamp=series[0].timestamp, quantity=1.0)],
        2: [Signal(SignalAction.CLOSE, timestamp=series[2].timestamp)],
    }


def test_identical_inputs_produce_identical_results() -> None:
    series = build_series(ROWS)
    result_a = run_backtest(ScriptedStrategy(_script(series)), series, _config())
    result_b = run_backtest(ScriptedStrategy(_script(series)), series, _config())

    assert result_a.fingerprint == result_b.fingerprint
    assert result_a.metrics == result_b.metrics
    assert [t.net_pnl for t in result_a.trades] == [t.net_pnl for t in result_b.trades]
    assert result_a.equity_curve.ending_equity == result_b.equity_curve.ending_equity


def test_run_id_differs_but_fingerprint_matches_across_runs() -> None:
    series = build_series(ROWS)
    result_a = run_backtest(ScriptedStrategy(_script(series)), series, _config())
    result_b = run_backtest(ScriptedStrategy(_script(series)), series, _config())

    assert result_a.run_id != result_b.run_id  # a fresh identity per run...
    assert result_a.fingerprint == result_b.fingerprint  # ...but the same reproducibility fingerprint


def test_different_parameters_change_fingerprint() -> None:
    series = build_series(ROWS)
    result_a = run_backtest(
        ScriptedStrategy(_script(series)), series, _config(strategy_params={"x": 1})
    )
    result_b = run_backtest(
        ScriptedStrategy(_script(series)), series, _config(strategy_params={"x": 2})
    )
    assert result_a.fingerprint != result_b.fingerprint


def test_different_execution_assumptions_change_fingerprint() -> None:
    series = build_series(ROWS)
    result_a = run_backtest(ScriptedStrategy(_script(series)), series, _config(fee_model=ZeroFeeModel()))
    result_b = run_backtest(
        ScriptedStrategy(_script(series)), series, _config(fee_model=PercentageFeeModel(rate=0.001))
    )
    assert result_a.fingerprint != result_b.fingerprint


def test_different_data_changes_fingerprint() -> None:
    series_a = build_series(ROWS)
    series_b = build_series(ROWS[:-1] + [(108, 120, 107, 115, 1000)])  # last close differs
    result_a = run_backtest(ScriptedStrategy(_script(series_a)), series_a, _config())
    result_b = run_backtest(ScriptedStrategy(_script(series_b)), series_b, _config())
    assert result_a.fingerprint != result_b.fingerprint


def test_compute_fingerprint_is_a_pure_function() -> None:
    series = build_series(ROWS)
    assumptions = ExecutionAssumptions(
        starting_capital=10_000.0,
        fee_model=ZeroFeeModel(),
        slippage_model=ZeroSlippageModel(),
        intrabar_policy=IntrabarPolicy.STOP_FIRST,
    )
    data_identity = compute_data_identity(series)

    fp1 = compute_fingerprint(
        strategy_name="s", strategy_version="1", parameters={"a": 1},
        data_identity=data_identity, execution_assumptions=assumptions,
    )
    fp2 = compute_fingerprint(
        strategy_name="s", strategy_version="1", parameters={"a": 1},
        data_identity=data_identity, execution_assumptions=assumptions,
    )
    assert fp1 == fp2

    fp3 = compute_fingerprint(
        strategy_name="s", strategy_version="1", parameters={"a": 1},
        data_identity=data_identity, execution_assumptions=assumptions, engine_version="999.0.0",
    )
    assert fp1 != fp3


def test_data_identity_stable_for_same_series_different_for_different_series() -> None:
    series_a = build_series(ROWS)
    series_b = build_series(ROWS)
    series_c = build_series(ROWS[:-1] + [(108, 120, 107, 115, 1000)])

    assert compute_data_identity(series_a) == compute_data_identity(series_b)
    assert compute_data_identity(series_a) != compute_data_identity(series_c)
