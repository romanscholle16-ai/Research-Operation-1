"""Configurable, exchange-independent fee and slippage models.

Fee and slippage are deliberately separate, independently swappable
models (Phase 2 brief section 6). Neither has a Binance-shaped or any
other exchange-specific default - the zero-cost models are the default
so tests are exact, and callers opt into realistic costs explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class FeeModel(Protocol):
    def calculate_fee(self, price: float, quantity: float) -> float:
        """Return the fee, in quote currency, for a fill of `quantity` at `price`."""
        ...


class SlippageModel(Protocol):
    def apply(self, price: float, *, is_buy: bool, quantity: float) -> float:
        """Return the fill price after slippage.

        `is_buy` is the direction of this specific transaction (True =
        buying, e.g. opening a long or covering a short; False = selling,
        e.g. opening a short or exiting a long) - NOT the resulting
        position side. Slippage always moves the price against the trader.
        """
        ...


@dataclass(frozen=True)
class ZeroFeeModel:
    def calculate_fee(self, price: float, quantity: float) -> float:
        return 0.0


@dataclass(frozen=True)
class PercentageFeeModel:
    """Fee = `rate` * notional (e.g. rate=0.0005 for 0.05%)."""

    rate: float

    def calculate_fee(self, price: float, quantity: float) -> float:
        return abs(price * quantity) * self.rate


@dataclass(frozen=True)
class ZeroSlippageModel:
    def apply(self, price: float, *, is_buy: bool, quantity: float) -> float:
        return price


@dataclass(frozen=True)
class FixedBpsSlippageModel:
    """Slippage moves the fill price against the trader by `bps` basis
    points: higher for buys, lower for sells."""

    bps: float

    def apply(self, price: float, *, is_buy: bool, quantity: float) -> float:
        factor = self.bps / 10_000.0
        return price * (1 + factor) if is_buy else price * (1 - factor)
