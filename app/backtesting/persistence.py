"""Persists a `BacktestResult` using the Phase 1 database foundation.

Reuses the existing `experiments` / `trades` / `experiment_results`
tables (extended by schema migration 2) rather than introducing a
parallel set of backtesting-only tables - see ARCHITECTURE.md
"Database integration (Phase 2)" for why.
"""

from __future__ import annotations

import json

from app.database.connection import Database
from app.backtesting.result import BacktestResult

SYSTEM_NAME = "backtesting_engine"


def save_backtest_result(db: Database, result: BacktestResult) -> None:
    with db.transaction() as conn:
        conn.execute(
            """
            INSERT INTO experiments (
                id, strategy_id, system_name, strategy_name, status,
                parameters, metadata, fingerprint, started_at, completed_at
            ) VALUES (?, NULL, ?, ?, 'completed', ?, ?, ?, ?, ?)
            """,
            (
                result.run_id,
                SYSTEM_NAME,
                result.strategy_name,
                json.dumps(result.parameters, default=str),
                json.dumps(
                    {
                        "execution_assumptions": result.execution_assumptions.to_dict(),
                        "equity_curve": result.equity_curve.to_dict(),
                        "warnings": list(result.warnings),
                        "engine_version": result.engine_version,
                        "symbol": result.symbol,
                        "timeframe": result.timeframe.value,
                        "strategy_version": result.strategy_version,
                    },
                    default=str,
                ),
                result.fingerprint,
                result.data_start.isoformat() if result.data_start else None,
                result.created_at.isoformat(),
            ),
        )

        for trade in result.trades:
            conn.execute(
                """
                INSERT INTO trades (
                    id, experiment_id, strategy_id, symbol, side,
                    entry_time, exit_time, entry_price, exit_price, quantity,
                    pnl, fees, gross_pnl, slippage_cost, return_pct, exit_reason
                ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade.id,
                    result.run_id,
                    trade.symbol,
                    trade.side.value,
                    trade.entry_time.isoformat(),
                    trade.exit_time.isoformat(),
                    trade.entry_price,
                    trade.exit_price,
                    trade.quantity,
                    trade.net_pnl,
                    trade.fees,
                    trade.gross_pnl,
                    trade.slippage_cost,
                    trade.return_pct,
                    trade.exit_reason.value,
                ),
            )

        for metric_name, metric_value in result.metrics.to_dict().items():
            conn.execute(
                """
                INSERT INTO experiment_results (id, experiment_id, metric_name, metric_value)
                VALUES (lower(hex(randomblob(16))), ?, ?, ?)
                """,
                (result.run_id, metric_name, metric_value),
            )


def load_experiment_metrics(db: Database, run_id: str) -> dict[str, float | None]:
    rows = db.query_all(
        "SELECT metric_name, metric_value FROM experiment_results WHERE experiment_id = ?", (run_id,)
    )
    return {row["metric_name"]: row["metric_value"] for row in rows}


def load_trades(db: Database, run_id: str) -> list[dict]:
    rows = db.query_all(
        "SELECT * FROM trades WHERE experiment_id = ? ORDER BY entry_time", (run_id,)
    )
    return [dict(row) for row in rows]
