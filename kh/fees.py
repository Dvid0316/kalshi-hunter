"""Kalshi trading fee math.

Source: Kalshi Fee Schedule (effective July 7, 2026), https://kalshi.com/docs/kalshi-fee-schedule.pdf
  taker fees = round up(M x 0.07 x C x P x (1-P))
  maker fees = round up(M x 0.0175 x C x P x (1-P))   (M defaults to 0 for maker unless series is listed)
Rounding: https://docs.kalshi.com/getting_started/fee_rounding -- non-direct members are aligned to $0.01.
We conservatively round each order's fee UP to the cent (retail / non-direct member).
"""
import math
from decimal import Decimal, ROUND_CEILING

TAKER_RATE = Decimal("0.07")
MAKER_RATE = Decimal("0.0175")


def fee(price: float, contracts: float = 1, multiplier: float = 1.0, maker: bool = False,
        precision: str = "0.01") -> float:
    """Fee in dollars for one order of `contracts` at `price` (dollars, 0..1)."""
    p = Decimal(str(price)); c = Decimal(str(contracts)); m = Decimal(str(multiplier))
    if p <= 0 or p >= 1 or c <= 0 or m == 0:
        return 0.0
    raw = m * (MAKER_RATE if maker else TAKER_RATE) * c * p * (1 - p)
    return float(raw.quantize(Decimal(precision), rounding=ROUND_CEILING))


def fee_per_contract(price: float, contracts: float = 100, multiplier: float = 1.0) -> float:
    """Average taker fee per contract for an order of `contracts` (default 100-lot)."""
    return fee(price, contracts, multiplier) / contracts
