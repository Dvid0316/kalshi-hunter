"""Long binary paper contracts held to binary settlement. Never account trades.

Cash cost = filled quantity * side purchase price + recorded entry fee.
Settlement = quantity * (1 if purchased side wins else 0).
No exit fee is invented. Voids/nonbinary outcomes require a separate policy.
All arithmetic uses Decimal; rounding is a presentation concern only.
"""
from decimal import Decimal


def amount(value):
    x = Decimal(str(value))
    if not x.is_finite():
        raise ValueError('Amounts must be finite')
    return x


def settlement_pnl(side, qty, price, entry_fee, outcome):
    if side not in ('yes', 'no') or outcome not in (0, 1):
        raise ValueError('Binary side and outcome required')
    q, p, f = map(amount, (qty, price, entry_fee))
    if q <= 0 or not 0 <= p <= 1 or f < 0:
        raise ValueError('Invalid quantity, price or fee')
    payout = q if (side == 'yes') == (outcome == 1) else Decimal(0)
    return payout - q * p - f
