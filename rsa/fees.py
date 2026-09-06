"""Fee models for prediction-market contracts.

Every contract pays $1.00 if the outcome occurs and $0 otherwise, so a contract
bought at price ``p`` (in dollars) risks ``p`` plus fees to win ``1 - p`` minus
fees. Fees are what turn a small mispricing into a losing bet, so the backtest
always nets them out.

Robinhood (effective 1 June 2026): commission per order is
``ceil_to_cent(k * p * (1 - p) * contracts)`` with ``k = 0.10`` for standard
accounts and ``k = 0.05`` with Robinhood Gold, plus an exchange fee of up to
$0.01 per contract charged by the clearing exchange (Kalshi/Rothera). Before
June 2026 Robinhood charged a flat $0.01 commission + $0.01 exchange fee.

Kalshi direct: ``ceil_to_cent(0.07 * contracts * p * (1 - p))`` on most
series (some series use a lower rate; pass ``rate`` to override).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def ceil_to_cent(x: float) -> float:
    """Round *up* to the next cent, tolerating float noise (0.30000000000000004 -> 0.30)."""
    return math.ceil(round(x, 9) * 100 - 1e-9) / 100


@dataclass(frozen=True)
class FeeModel:
    """Base class. ``fee(price, contracts)`` returns total fees in dollars for one order."""

    name: str = "none"

    def fee(self, price: float, contracts: int = 1) -> float:  # pragma: no cover - trivial
        return 0.0

    def fee_per_contract(self, price: float, contracts: int = 1) -> float:
        return self.fee(price, contracts) / contracts if contracts else 0.0


@dataclass(frozen=True)
class NoFees(FeeModel):
    name: str = "none"

    def fee(self, price: float, contracts: int = 1) -> float:
        return 0.0


@dataclass(frozen=True)
class RobinhoodFees(FeeModel):
    """Robinhood's probability-weighted commission (June 2026 schedule) + exchange fee."""

    name: str = "robinhood"
    gold: bool = False
    exchange_fee_per_contract: float = 0.01

    @property
    def k(self) -> float:
        return 0.05 if self.gold else 0.10

    def commission(self, price: float, contracts: int = 1) -> float:
        _check_price(price)
        return ceil_to_cent(self.k * price * (1.0 - price) * contracts)

    def fee(self, price: float, contracts: int = 1) -> float:
        return self.commission(price, contracts) + self.exchange_fee_per_contract * contracts


@dataclass(frozen=True)
class RobinhoodFlatFees(FeeModel):
    """Robinhood's pre-June-2026 schedule: $0.01 commission + $0.01 exchange fee per contract."""

    name: str = "robinhood_flat"
    commission_per_contract: float = 0.01
    exchange_fee_per_contract: float = 0.01

    def fee(self, price: float, contracts: int = 1) -> float:
        _check_price(price)
        return (self.commission_per_contract + self.exchange_fee_per_contract) * contracts


@dataclass(frozen=True)
class KalshiFees(FeeModel):
    """Kalshi's taker fee: ceil_to_cent(rate * C * P * (1 - P)); rate is 0.07 on most series."""

    name: str = "kalshi"
    rate: float = 0.07

    def fee(self, price: float, contracts: int = 1) -> float:
        _check_price(price)
        return ceil_to_cent(self.rate * contracts * price * (1.0 - price))


FEE_MODELS: dict[str, FeeModel] = {
    "none": NoFees(),
    "robinhood": RobinhoodFees(),
    "robinhood_gold": RobinhoodFees(gold=True),
    "robinhood_flat": RobinhoodFlatFees(),
    "kalshi": KalshiFees(),
}


def get_fee_model(name: str) -> FeeModel:
    try:
        return FEE_MODELS[name]
    except KeyError:
        raise KeyError(f"Unknown fee model '{name}'. Known: {', '.join(FEE_MODELS)}") from None


def breakeven_probability(price: float, fees: FeeModel, contracts: int = 1) -> float:
    """Win probability needed for a buy at ``price`` to have zero expected profit.

    EV = q * (1 - price) - (1 - q) * price - fee  =>  q* = price + fee_per_contract.
    """
    return price + fees.fee_per_contract(price, contracts)


def expected_profit(prob: float, price: float, fees: FeeModel, contracts: int = 1) -> float:
    """Expected profit in dollars for buying ``contracts`` at ``price`` with true win probability ``prob``."""
    return contracts * (prob * (1.0 - price) - (1.0 - prob) * price) - fees.fee(price, contracts)


def _check_price(price: float) -> None:
    if not (0.0 <= price <= 1.0):
        raise ValueError(f"price must be in dollars between 0 and 1, got {price}")
