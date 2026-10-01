from datetime import datetime, timedelta, timezone

from app.backtesting.engine import BacktestConfig, run_backtest
from app.backtesting.market_data import Candle, CandleSeries, Timeframe
from app.research.adapter import adapt_specification
from app.research.specification import Condition, FieldRef, IndicatorSpec, RuleSpec, RuleStatus, StrategySpecification

UTC = timezone.utc
START = datetime(2024, 1, 1, tzinfo=UTC)


def _series(closes: list[float]) -> CandleSeries:
    candles = []
    for i, c in enumerate(closes):
        candles.append(
            Candle(timestamp=START + timedelta(minutes=i + 1), open=c - 0.5, high=c + 1, low=c - 1, close=c, volume=1000)
        )
    return CandleSeries(candles, symbol="X", timeframe=Timeframe.M1)


def _ema_cross_spec(**overrides) -> StrategySpecification:
    defaults = dict(
        name="ema_cross",
        timeframe="1m",
        indicators=(IndicatorSpec(type="EMA", params={"period": 3}),),
        entry_rules=(
            RuleSpec(
                description="enter long when close crosses above EMA3",
                status=RuleStatus.INTERPRETED,
                side="long",
                condition=Condition(op="crosses_above", left=FieldRef(name="close"), right=FieldRef(name="EMA", params={"period": 3})),
            ),
        ),
        exit_rules=(
            RuleSpec(
                description="exit when close crosses below EMA3",
                status=RuleStatus.INTERPRETED,
                condition=Condition(op="crosses_below", left=FieldRef(name="close"), right=FieldRef(name="EMA", params={"period": 3})),
            ),
        ),
    )
    defaults.update(overrides)
    return StrategySpecification(**defaults)


def test_valid_spec_is_adaptable() -> None:
    result = adapt_specification(_ema_cross_spec())
    assert result.adaptable
    assert result.strategy_factory is not None
    assert result.reasons == ()


def test_incomplete_spec_is_not_adaptable() -> None:
    spec = StrategySpecification(name="incomplete", timeframe="1h")
    result = adapt_specification(spec)
    assert not result.adaptable
    assert result.strategy_factory is None
    assert any("not valid" in r for r in result.reasons)


def test_structural_stop_loss_is_not_adaptable_yet() -> None:
    spec = _ema_cross_spec(
        stop_loss_rules=(
            RuleSpec(description="stop below swing low", status=RuleStatus.INTERPRETED, condition=Condition(op="<", left=FieldRef(name="low"), right=0)),
        )
    )
    result = adapt_specification(spec)
    assert not result.adaptable
    assert any("structural placement" in r for r in result.reasons)


def test_entry_rule_without_condition_is_not_adaptable() -> None:
    spec = _ema_cross_spec(entry_rules=(RuleSpec(description="vague entry", status=RuleStatus.UNKNOWN),))
    result = adapt_specification(spec)
    assert not result.adaptable  # also fails validation (status != VALID), covered by "not valid" reason


def test_adapted_strategy_runs_through_the_real_backtesting_engine() -> None:
    closes = [100, 100, 100, 101, 103, 106, 110, 108, 104, 99, 95]
    series = _series(closes)
    result = adapt_specification(_ema_cross_spec())
    strategy = result.strategy_factory({"quantity": 1.0})

    backtest_result = run_backtest(strategy, series, BacktestConfig(symbol="X", timeframe=Timeframe.M1, starting_capital=10_000))

    assert len(backtest_result.trades) >= 1
    trade = backtest_result.trades[0]
    assert trade.side.value == "long"


def test_percent_stop_loss_is_applied() -> None:
    spec = _ema_cross_spec(
        stop_loss_rules=(RuleSpec(description="2 percent stop", status=RuleStatus.INTERPRETED, value=2.0, value_type="percent"),)
    )
    # A sharp drop right after entry should trigger the percent stop rather than the EMA exit.
    closes = [100, 100, 100, 101, 103, 106, 80, 80, 80, 80, 80]
    series = _series(closes)
    result = adapt_specification(spec)
    assert result.adaptable
    strategy = result.strategy_factory({"quantity": 1.0})
    backtest_result = run_backtest(strategy, series, BacktestConfig(symbol="X", timeframe=Timeframe.M1, starting_capital=10_000))
    assert len(backtest_result.trades) >= 1
    assert backtest_result.trades[0].exit_reason.value == "stop_loss"


def test_short_side_entry_is_supported() -> None:
    spec = _ema_cross_spec(
        entry_rules=(
            RuleSpec(
                description="enter short when close crosses below EMA3",
                status=RuleStatus.INTERPRETED,
                side="short",
                condition=Condition(op="crosses_below", left=FieldRef(name="close"), right=FieldRef(name="EMA", params={"period": 3})),
            ),
        ),
        exit_rules=(),
    )
    closes = [100, 100, 100, 99, 97, 94, 90, 86, 82, 78, 74]
    series = _series(closes)
    result = adapt_specification(spec)
    strategy = result.strategy_factory({"quantity": 1.0})
    backtest_result = run_backtest(strategy, series, BacktestConfig(symbol="X", timeframe=Timeframe.M1, starting_capital=10_000))
    assert len(backtest_result.trades) == 1
    assert backtest_result.trades[0].side.value == "short"


def test_adapter_never_uses_eval_or_exec() -> None:
    import ast
    import inspect

    import app.research.adapter as adapter_module

    tree = ast.parse(inspect.getsource(adapter_module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            assert name not in ("eval", "exec", "compile")
