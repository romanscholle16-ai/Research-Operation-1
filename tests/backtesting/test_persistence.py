from app.backtesting.engine import BacktestConfig, run_backtest
from app.backtesting.market_data import Timeframe
from app.backtesting.persistence import load_experiment_metrics, load_trades, save_backtest_result
from app.backtesting.signals import Signal, SignalAction
from app.database.connection import Database
from app.database.schema import CURRENT_SCHEMA_VERSION
from tests.fixtures.mock_strategies import ScriptedStrategy
from tests.fixtures.synthetic_data import build_series

ROWS = [
    (100, 101, 99, 100, 1000),
    (100, 105, 100, 104, 1000),
    (104, 110, 103, 108, 1000),
    (108, 109, 107, 108, 1000),
]


def _make_result():
    series = build_series(ROWS)
    script = {
        0: [Signal(SignalAction.OPEN_LONG, timestamp=series[0].timestamp, quantity=1.0)],
        2: [Signal(SignalAction.CLOSE, timestamp=series[2].timestamp)],
    }
    config = BacktestConfig(symbol="TEST/USDT", timeframe=Timeframe.M1, starting_capital=10_000.0)
    return run_backtest(ScriptedStrategy(script), series, config)


def test_migration_2_adds_backtesting_columns(database: Database) -> None:
    assert CURRENT_SCHEMA_VERSION >= 2
    versions = {row["version"] for row in database.query_all("SELECT version FROM schema_migrations")}
    assert 2 in versions

    trades_columns = {row["name"] for row in database.query_all("PRAGMA table_info(trades)")}
    assert {"gross_pnl", "slippage_cost", "return_pct", "exit_reason"}.issubset(trades_columns)

    experiments_columns = {row["name"] for row in database.query_all("PRAGMA table_info(experiments)")}
    assert {"strategy_name", "fingerprint"}.issubset(experiments_columns)


def test_save_backtest_result_persists_experiment(database: Database) -> None:
    result = _make_result()
    save_backtest_result(database, result)

    row = database.query_one("SELECT * FROM experiments WHERE id = ?", (result.run_id,))
    assert row is not None
    assert row["fingerprint"] == result.fingerprint
    assert row["strategy_name"] == result.strategy_name
    assert row["status"] == "completed"


def test_save_backtest_result_persists_trades(database: Database) -> None:
    result = _make_result()
    save_backtest_result(database, result)

    trades = load_trades(database, result.run_id)
    assert len(trades) == len(result.trades)
    persisted = trades[0]
    original = result.trades[0]
    assert persisted["symbol"] == original.symbol
    assert persisted["side"] == original.side.value
    assert round(persisted["pnl"], 9) == round(original.net_pnl, 9)
    assert round(persisted["gross_pnl"], 9) == round(original.gross_pnl, 9)
    assert persisted["exit_reason"] == original.exit_reason.value


def test_save_backtest_result_persists_metrics(database: Database) -> None:
    result = _make_result()
    save_backtest_result(database, result)

    persisted_metrics = load_experiment_metrics(database, result.run_id)
    assert persisted_metrics["total_trades"] == result.metrics.total_trades
    assert persisted_metrics["net_profit"] == result.metrics.net_profit
    assert persisted_metrics["win_rate"] == result.metrics.win_rate


def test_fingerprint_is_unique_across_experiments(database: Database) -> None:
    result = _make_result()
    save_backtest_result(database, result)

    duplicate = database.query_all(
        "SELECT id FROM experiments WHERE fingerprint = ?", (result.fingerprint,)
    )
    assert len(duplicate) == 1
