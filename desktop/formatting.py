"""Pure display helpers. No I/O, no Qt. Display rounding only: never feed results back into accounting.

Money shown to the user is always a Decimal (or None -> 'Unavailable'). Floats from the
research snapshot are converted through ``Decimal(repr(x))`` so artefacts such as
0.30000000000000004 never reach the screen.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN, InvalidOperation, localcontext
from zoneinfo import ZoneInfo

UNAVAILABLE = 'Unavailable'
DASH = '—'
CHICAGO = ZoneInfo('America/Chicago')


def to_decimal(value) -> Decimal | None:
    """Exact Decimal from int/str/Decimal/float; None for None/NaN/inf/garbage."""
    if value is None or isinstance(value, bool):
        return None
    try:
        d = value if isinstance(value, Decimal) else Decimal(repr(value) if isinstance(value, float) else str(value))
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None


def cents(price) -> str:
    """Dollar price (0..1) as cents: 0.35 -> '35.0¢', 0.0935 -> '9.35¢'. None -> '—'."""
    d = to_decimal(price)
    if d is None:
        return DASH
    d = d.quantize(Decimal('0.000001'), rounding=ROUND_HALF_EVEN)     # strip binary-float noise (sub-micro-dollar)
    c = d * 100
    one = c.quantize(Decimal('0.1'), rounding=ROUND_HALF_EVEN)
    text = f'{one}' if one == c else f"{c.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)}"
    return text + '¢'


def spread_cents(bid, ask) -> str:
    b, a = to_decimal(bid), to_decimal(ask)
    if b is None or a is None:
        return DASH
    return cents(a - b)


def percent(prob, places: int = 1) -> str:
    d = to_decimal(prob)
    if d is None:
        return DASH
    return f"{(d * 100).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN)}%"


def money(value, *, plus: bool = False) -> str:
    """Decimal dollars -> '$1,234.50' / '-$3.20'; None -> 'Unavailable'."""
    d = to_decimal(value)
    if d is None:
        return UNAVAILABLE
    try:
        with localcontext() as ctx:
            ctx.prec = 80                                  # an absurd amount must degrade to Unavailable, never crash a page
            q = d.quantize(Decimal('0.01'), rounding=ROUND_HALF_EVEN)
    except InvalidOperation:
        return UNAVAILABLE
    sign = '-' if q < 0 else ('+' if plus and q > 0 else '')
    return f"{sign}${abs(q):,.2f}"


def quantity(value) -> str:
    d = to_decimal(value)
    if d is None:
        return DASH
    return f'{d:,.0f}' if d == d.to_integral_value() else f"{d.normalize():,f}"


def count(value) -> str:
    d = to_decimal(value)
    return DASH if d is None else quantity(d)         # 2.5 contracts shows as 2.5, never truncated to 2


def stamp(ts) -> str:
    if not ts:
        return UNAVAILABLE
    try:
        return datetime.fromtimestamp(ts, CHICAGO).strftime('%b %d, %Y · %H:%M %Z')
    except (ValueError, OverflowError, OSError):
        return UNAVAILABLE                                 # a corrupt timestamp must not take the page down


def short_stamp(ts) -> str:
    if not ts:
        return DASH
    try:
        return datetime.fromtimestamp(ts, CHICAGO).strftime('%b %d %H:%M')
    except (ValueError, OverflowError, OSError):
        return DASH


def clock(ts) -> str:
    if not ts:
        return DASH
    try:
        return datetime.fromtimestamp(ts, CHICAGO).strftime('%H:%M')
    except (ValueError, OverflowError, OSError):
        return DASH


def age_text(seconds) -> str:
    """Human age: 45 s, 4 min, 1 h 12 min, 2 d 3 h. None -> 'unknown age'."""
    if seconds is None or seconds < 0:
        return 'unknown age'
    s = int(seconds)
    if s < 90:
        return f'{s} s'
    m = s // 60
    if m < 90:
        return f'{m} min'
    h, mm = divmod(m, 60)
    if h < 48:
        return f'{h} h {mm:02d} min'
    d, hh = divmod(h, 24)
    return f'{d} d {hh} h'
