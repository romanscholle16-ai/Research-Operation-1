from app.backtesting.engine import BacktestConfig, run_backtest
from app.backtesting.intrabar import IntrabarPolicy
from app.backtesting.market_data import Timeframe
from app.backtesting.signals import Signal, SignalAction
from app.backtesting.trades import ExitReason
from tests.fixtures.mock_strategies import ScriptedStrategy
from tests.fixtures.synthetic_data import build_series


def _config(intrabar_policy: IntrabarPolicy = IntrabarPolicy.STOP_FIRST) -> BacktestConfig:
    return BacktestConfig(
        symbol="TEST/USDT", timeframe=Timeframe.M1, starting_capital=10_000.0, intrabar_policy=intrabar_policy
    )


def test_stop_loss_triggers_and_exits_at_stop_price() -> None:
    rows = [
        (100, 101, 99, 100, 1000),   # idx0: signal
        (100, 101, 99, 100, 1000),   # idx1: entry fill @ open=100
        (100, 102, 98, 101, 1000),   # idx2: no touch (stop=95, target=110)
        (101, 102, 94, 96, 1000),    # idx3: low=94 <= stop=95 -> triggers
    ]
    series = build_series(rows)
    script = {
        0: [
            Signal(
                SignalAction.OPEN_LONG,
                timestamp=series[0].timestamp,
                quantity=1.0,
                stop_loss=95.0,
                take_profit=110.0,
            )
        ]
    }
    result = run_backtest(ScriptedStrategy(script), series, _config())

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason is ExitReason.STOP_LOSS
    assert trade.exit_price == 95.0
    assert trade.exit_time == series[3].timestamp


def test_take_profit_triggers_and_exits_at_target_price() -> None:
    rows = [
        (100, 101, 99, 100, 1000),
        (100, 101, 99, 100, 1000),
        (100, 102, 98, 101, 1000),
        (101, 111, 100, 105, 1000),  # idx3: high=111 >= target=110 -> triggers
    ]
    series = build_series(rows)
    script = {
        0: [
            Signal(
                SignalAction.OPEN_LONG,
                timestamp=series[0].timestamp,
                quantity=1.0,
                stop_loss=95.0,
                take_profit=110.0,
            )
        ]
    }
    result = run_backtest(ScriptedStrategy(script), series, _config())

    trade = result.trades[0]
    assert trade.exit_reason is ExitReason.TAKE_PROFIT
    assert trade.exit_price == 110.0


def test_stop_cannot_trigger_on_the_candle_the_position_was_opened() -> None:
    """The entry candle's own low touches the stop level, but the stop
    check for a position runs BEFORE that candle's entry order is applied
    (see execution.py) - so it must not fire until a later candle."""
    rows = [
        (100, 101, 99, 100, 1000),  # idx0: signal
        (100, 101, 90, 100, 1000),  # idx1: entry fill @ open=100; low=90 touches stop=95 but must be ignored
        (100, 102, 98, 101, 1000),  # idx2: no touch
        (101, 102, 94, 96, 1000),   # idx3: low=94 <= stop=95 -> triggers here instead
    ]
    series = build_series(rows)
    script = {
        0: [
            Signal(
                SignalAction.OPEN_LONG,
                timestamp=series[0].timestamp,
                quantity=1.0,
                stop_loss=95.0,
                take_profit=110.0,
            )
        ]
    }
    result = run_backtest(ScriptedStrategy(script), series, _config())

    trade = result.trades[0]
    assert trade.entry_time == series[1].timestamp
    assert trade.exit_time == series[3].timestamp  # NOT series[1]
    assert trade.exit_reason is ExitReason.STOP_LOSS


def _ambiguous_series():
    rows = [
        (100, 101, 99, 100, 1000),    # idx0: signal
        (100, 101, 99, 100, 1000),    # idx1: entry fill @ open=100
        (100, 112, 93, 105, 1000),    # idx2: high=112>=target(110) AND low=93<=stop(95): both hit
    ]
    return build_series(rows)


def test_ambiguous_candle_stop_first_policy() -> None:
    series = _ambiguous_series()
    script = {
        0: [
            Signal(
                SignalAction.OPEN_LONG,
                timestamp=series[0].timestamp,
                quantity=1.0,
                stop_loss=95.0,
                take_profit=110.0,
            )
        ]
    }
    result = run_backtest(ScriptedStrategy(script), series, _config(IntrabarPolicy.STOP_FIRST))
    trade = result.trades[0]
    assert trade.exit_reason is ExitReason.STOP_LOSS
    assert trade.exit_price == 95.0


def test_ambiguous_candle_target_first_policy() -> None:
    series = _ambiguous_series()
    script = {
        0: [
            Signal(
                SignalAction.OPEN_LONG,
                timestamp=series[0].timestamp,
                quantity=1.0,
                stop_loss=95.0,
                take_profit=110.0,
            )
        ]
    }
    result = run_backtest(ScriptedStrategy(script), series, _config(IntrabarPolicy.TARGET_FIRST))
    trade = result.trades[0]
    assert trade.exit_reason is ExitReason.TAKE_PROFIT
    assert trade.exit_price == 110.0


def test_short_stop_and_target_directions_are_mirrored() -> None:
    rows = [
        (100, 101, 99, 100, 1000),   # idx0: signal (short @ close=100)
        (100, 101, 99, 100, 1000),   # idx1: entry fill @ open=100 (short)
        (100, 106, 99, 104, 1000),   # idx2: high=106 >= stop(105 for short) -> triggers
    ]
    series = build_series(rows)
    script = {
        0: [
            Signal(
                SignalAction.OPEN_SHORT,
                timestamp=series[0].timestamp,
                quantity=1.0,
                stop_loss=105.0,  # above entry for a short
                take_profit=90.0,  # below entry for a short
            )
        ]
    }
    result = run_backtest(ScriptedStrategy(script), series, _config())
    trade = result.trades[0]
    assert trade.exit_reason is ExitReason.STOP_LOSS
    assert trade.exit_price == 105.0
