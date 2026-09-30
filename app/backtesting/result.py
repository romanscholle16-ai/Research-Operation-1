"""The structured result of one backtest run, plus reproducibility
fingerprinting (Phase 2 brief sections 14-15).

`ENGINE_VERSION` must be bumped whenever a change to this package could
change a backtest's numeric output for the same inputs (e.g. a fix to
intrabar resolution, fee rounding, ...) - it is part of the fingerprint
specifically so a changed engine does not silently masquerade as a
reproduction of an old result.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.backtesting.costs import FeeModel, SlippageModel
from app.backtesting.equity import EquityCurve
from app.backtesting.intrabar import IntrabarPolicy
from app.backtesting.market_data import CandleSeries, Timeframe
from app.backtesting.metrics import PerformanceMetrics
from app.backtesting.trades import Trade

ENGINE_VERSION = "1.0.0"


def _describe_model(model: Any) -> dict[str, Any]:
    """Serialize a FeeModel/SlippageModel for fingerprinting/result
    storage. Works for any frozen dataclass instance, which is what every
    model in app/backtesting/costs.py is."""
    return {"type": type(model).__name__, **dataclasses.asdict(model)}


@dataclass(frozen=True)
class ExecutionAssumptions:
    starting_capital: float
    fee_model: FeeModel
    slippage_model: SlippageModel
    intrabar_policy: IntrabarPolicy

    def to_dict(self) -> dict[str, Any]:
        return {
            "starting_capital": self.starting_capital,
            "fee_model": _describe_model(self.fee_model),
            "slippage_model": _describe_model(self.slippage_model),
            "intrabar_policy": self.intrabar_policy.value,
        }


def compute_data_identity(candles: CandleSeries) -> str:
    """A cheap, deterministic fingerprint of a candle series' *identity*
    (not its full content): symbol, timeframe, count, span, and a hash of
    closes. Enough to detect "this is obviously different data" and to
    make the run fingerprint reproducible for the same series object.
    Not a substitute for real data versioning/lineage, which is out of
    scope for Phase 2.
    """
    if len(candles) == 0:
        payload = f"{candles.symbol}:{candles.timeframe.value}:empty"
    else:
        closes_hash = hashlib.sha256(
            ",".join(f"{c.close:.10g}" for c in candles).encode("utf-8")
        ).hexdigest()[:16]
        payload = (
            f"{candles.symbol}:{candles.timeframe.value}:{len(candles)}:"
            f"{candles.start.isoformat()}:{candles.end.isoformat()}:{closes_hash}"
        )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_fingerprint(
    *,
    strategy_name: str,
    strategy_version: str,
    parameters: dict[str, Any],
    data_identity: str,
    execution_assumptions: ExecutionAssumptions,
    engine_version: str = ENGINE_VERSION,
) -> str:
    canonical = json.dumps(
        {
            "strategy_name": strategy_name,
            "strategy_version": strategy_version,
            "parameters": parameters,
            "data_identity": data_identity,
            "execution_assumptions": execution_assumptions.to_dict(),
            "engine_version": engine_version,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BacktestResult:
    run_id: str
    fingerprint: str
    strategy_name: str
    strategy_version: str
    symbol: str
    timeframe: Timeframe
    parameters: dict[str, Any]
    execution_assumptions: ExecutionAssumptions
    data_start: datetime | None
    data_end: datetime | None
    trades: tuple[Trade, ...]
    equity_curve: EquityCurve
    metrics: PerformanceMetrics
    warnings: tuple[str, ...]
    engine_version: str = ENGINE_VERSION
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "fingerprint": self.fingerprint,
            "strategy_name": self.strategy_name,
            "strategy_version": self.strategy_version,
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "parameters": self.parameters,
            "execution_assumptions": self.execution_assumptions.to_dict(),
            "data_start": self.data_start.isoformat() if self.data_start else None,
            "data_end": self.data_end.isoformat() if self.data_end else None,
            "trades": [
                {
                    "id": t.id,
                    "strategy_name": t.strategy_name,
                    "symbol": t.symbol,
                    "side": t.side.value,
                    "entry_time": t.entry_time.isoformat(),
                    "entry_price": t.entry_price,
                    "exit_time": t.exit_time.isoformat(),
                    "exit_price": t.exit_price,
                    "quantity": t.quantity,
                    "gross_pnl": t.gross_pnl,
                    "fees": t.fees,
                    "slippage_cost": t.slippage_cost,
                    "net_pnl": t.net_pnl,
                    "return_pct": t.return_pct,
                    "exit_reason": t.exit_reason.value,
                }
                for t in self.trades
            ],
            "equity_curve": self.equity_curve.to_dict(),
            "metrics": self.metrics.to_dict(),
            "warnings": list(self.warnings),
            "engine_version": self.engine_version,
            "created_at": self.created_at.isoformat(),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


def new_run_id() -> str:
    return str(uuid.uuid4())
