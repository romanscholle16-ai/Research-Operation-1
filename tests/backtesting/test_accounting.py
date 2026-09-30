from datetime import timedelta

from app.backtesting.equity import compute_equity_curve
from app.backtesting.metrics import compute_metrics
from app.backtesting.positions import Side
from app.backtesting.trades import ExitReason, Trade
from tests.fixtures.synthetic_data import DEFAULT_START


def _trade(net_pnl: float, *, n: int, fees: float = 0.0, slippage_cost: float = 0.0) -> Trade:
    entry = DEFAULT_START + timedelta(hours=n)
    exit_ = entry + timedelta(minutes=5)
    return Trade(
        strategy_name="test",
        symbol="TEST/USDT",
        side=Side.LONG,
        entry_time=entry,
        entry_price=100.0,
        exit_time=exit_,
        exit_price=100.0,
        quantity=1.0,
        gross_pnl=net_pnl + fees + slippage_cost,
        fees=fees,
        slippage_cost=slippage_cost,
        exit_reason=ExitReason.SIGNAL,
    )


def test_trade_net_pnl_and_return_pct() -> None:
    trade = _trade(100.0, n=0, fees=2.0, slippage_cost=1.0)
    assert trade.net_pnl == 100.0
    assert trade.gross_pnl == 103.0
    assert trade.return_pct == 100.0 / (100.0 * 1.0)
    assert trade.is_win is True


def test_equity_curve_tracks_running_equity() -> None:
    trades = [_trade(100, n=0), _trade(-50, n=1), _trade(200, n=2)]
    curve = compute_equity_curve(trades, starting_equity=1000.0)
    assert curve.starting_equity == 1000.0
    assert curve.ending_equity == 1250.0
    assert [p.equity for p in curve.points] == [1100.0, 1050.0, 1250.0]


def test_equity_curve_max_drawdown() -> None:
    # 1000 -> 1100 -> 1050 -> 1250 -> 1220 -> 1200
    trades = [_trade(100, n=0), _trade(-50, n=1), _trade(200, n=2), _trade(-30, n=3), _trade(-20, n=4)]
    curve = compute_equity_curve(trades, starting_equity=1000.0)
    assert curve.max_drawdown == 50.0
    # worst relative drawdown is 50/1100 (after trade 2), not 50/1250 (after trade 5)
    assert round(curve.max_drawdown_pct, 6) == round(50.0 / 1100.0, 6)


def test_equity_curve_orders_by_exit_time_not_insertion_order() -> None:
    later = _trade(200, n=5)
    earlier = _trade(100, n=1)
    curve = compute_equity_curve([later, earlier], starting_equity=1000.0)
    assert [p.equity for p in curve.points] == [1100.0, 1300.0]


def test_empty_equity_curve() -> None:
    curve = compute_equity_curve([], starting_equity=1000.0)
    assert curve.starting_equity == curve.ending_equity == 1000.0
    assert curve.points == ()
    assert curve.max_drawdown == 0.0
    assert curve.max_drawdown_pct == 0.0


def test_metrics_on_no_trades_are_well_defined_not_crashing() -> None:
    metrics = compute_metrics([], max_drawdown=0.0, max_drawdown_pct=0.0)
    assert metrics.total_trades == 0
    assert metrics.win_rate == 0.0
    assert metrics.net_profit == 0.0
    assert metrics.profit_factor is None
    assert metrics.average_win is None
    assert metrics.average_loss is None
    assert metrics.largest_win is None
    assert metrics.largest_loss is None


def test_metrics_full_calculation() -> None:
    trades = [_trade(100, n=0), _trade(-50, n=1), _trade(200, n=2), _trade(-30, n=3), _trade(-20, n=4)]
    curve = compute_equity_curve(trades, starting_equity=1000.0)
    metrics = compute_metrics(trades, max_drawdown=curve.max_drawdown, max_drawdown_pct=curve.max_drawdown_pct)

    assert metrics.total_trades == 5
    assert metrics.winning_trades == 2
    assert metrics.losing_trades == 3
    assert metrics.win_rate == 2 / 5
    assert metrics.gross_profit == 300.0
    assert metrics.gross_loss == -100.0
    assert metrics.net_profit == 200.0
    assert metrics.average_trade == 40.0
    assert metrics.expectancy == 40.0
    assert metrics.profit_factor == 3.0
    assert metrics.average_win == 150.0
    assert round(metrics.average_loss, 6) == round(-100.0 / 3, 6)
    assert metrics.largest_win == 200.0
    assert metrics.largest_loss == -50.0
    assert metrics.max_drawdown == curve.max_drawdown


def test_metrics_profit_factor_undefined_with_no_losses() -> None:
    trades = [_trade(100, n=0), _trade(50, n=1)]
    metrics = compute_metrics(trades, max_drawdown=0.0, max_drawdown_pct=0.0)
    assert metrics.profit_factor is None
    assert metrics.average_loss is None
    assert metrics.largest_loss is None


def test_metrics_total_fees_and_slippage_are_summed() -> None:
    trades = [
        _trade(100, n=0, fees=1.0, slippage_cost=0.5),
        _trade(-50, n=1, fees=2.0, slippage_cost=1.5),
    ]
    metrics = compute_metrics(trades, max_drawdown=0.0, max_drawdown_pct=0.0)
    assert metrics.total_fees == 3.0
    assert metrics.total_slippage == 2.0
