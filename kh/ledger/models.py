"""Strict parsing and immutable record types for the personal ledger.

Boundary rules (every importer and the manual-entry form go through these):
  * numbers arrive as str/int/Decimal only. float and bool are rejected.
  * price is a dollar price strictly between 0 and 1 (the price of the side traded).
  * count > 0, fee >= 0, all finite.
  * timestamps are epoch seconds (UTC) after parsing; naive ISO strings need an explicit tz.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

ZERO = Decimal(0)
ONE = Decimal(1)
SIDES = ('yes', 'no')
ACTIONS = ('buy', 'sell')
RESULTS = ('yes', 'no', 'void', 'scalar')
CASH_KINDS = ('deposit', 'withdrawal', 'adjustment', 'other')
# 'kalshi_api' is reserved for a future, separately authorised read-only adapter. Nothing writes it today.
SOURCES = ('manual', 'csv', 'json', 'sample', 'kalshi_api')
_TICKER = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$')


class LedgerError(ValueError):
    """A record failed validation. The message is safe to show to the user."""


def dec(value, field: str = 'value') -> Decimal:
    if value is None or isinstance(value, (bool, float)):
        raise LedgerError(f'{field}: must be given as text or integer, got {type(value).__name__}')
    if isinstance(value, str):
        value = value.strip().replace(',', '').replace('$', '')
    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation:
        raise LedgerError(f'{field}: not a number: {value!r}') from None
    if not d.is_finite():
        raise LedgerError(f'{field}: must be finite')
    return d


def ticker(value) -> str:
    t = str(value or '').strip()
    if not _TICKER.match(t):
        raise LedgerError(f'ticker: invalid market ticker {value!r}')
    return t


def price(value, unit: str = 'dollars') -> Decimal:
    d = dec(value, 'price')
    if unit == 'cents':
        d = d / 100
    elif unit != 'dollars':
        raise LedgerError("price unit must be 'dollars' or 'cents'")
    if not (ZERO < d < ONE):
        raise LedgerError(f'price: must be strictly between $0 and $1, got {d}')
    return d


def count(value) -> Decimal:
    d = dec(value, 'count')
    if d <= 0:
        raise LedgerError('count: must be greater than zero')
    return d


def fee(value) -> Decimal:
    d = ZERO if value in (None, '') else dec(value, 'fee')
    if d < 0:
        raise LedgerError('fee: must not be negative')
    return d


def choice(value, allowed, field):
    v = str(value or '').strip().lower()
    if v not in allowed:
        raise LedgerError(f'{field}: must be one of {", ".join(allowed)}; got {value!r}')
    return v


def timestamp(value, tz: str = 'America/Chicago') -> float:
    """Epoch seconds. Accepts epoch numbers (as str/int) or ISO-8601. Naive ISO uses ``tz``."""
    if value is None or isinstance(value, bool):
        raise LedgerError('ts: missing timestamp')
    if isinstance(value, (int, Decimal)):
        return float(value)
    text = str(value).strip()
    if re.fullmatch(r'\d{9,11}(\.\d+)?', text):
        return float(text)
    try:
        dt = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        raise LedgerError(f'ts: unrecognised timestamp {value!r}') from None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    return dt.astimezone(timezone.utc).timestamp()


def s(d: Decimal) -> str:
    """Canonical text form stored in SQLite (exact, no exponent)."""
    return format(d, 'f')


@dataclass(frozen=True)
class Fill:
    fill_id: str
    ticker: str
    side: str
    action: str
    count: Decimal
    price: Decimal            # dollars per contract of the side traded
    fee: Decimal              # actual fee charged on this fill (dollars)
    ts: float
    order_id: str = ''
    is_taker: bool | None = None
    source: str = 'manual'
    synthetic_id: bool = False
    note: str = ''
    seq: int = 0              # insertion order, tie-breaker for equal timestamps


@dataclass(frozen=True)
class Settlement:
    settlement_id: str
    ticker: str
    market_result: str        # yes | no | void | scalar
    settled_ts: float
    revenue: Decimal          # dollars paid out by the exchange (authoritative)
    fee: Decimal = ZERO
    yes_count: Decimal | None = None
    no_count: Decimal | None = None
    yes_total_cost: Decimal | None = None
    no_total_cost: Decimal | None = None
    source: str = 'manual'


@dataclass(frozen=True)
class CashTransaction:
    txn_id: str
    ts: float
    kind: str
    amount: Decimal           # signed: deposits positive, withdrawals negative
    note: str = ''
    source: str = 'manual'


def make_fill(raw: dict, *, price_unit: str = 'dollars', tz: str = 'America/Chicago', source: str = 'manual') -> Fill:
    """Validate a mapping into a Fill (``fill_id`` may be empty; the store then derives a deterministic id)."""
    taker = raw.get('is_taker')
    if isinstance(taker, str):
        taker = {'true': True, '1': True, 'yes': True, 'false': False, '0': False, 'no': False, '': None}.get(taker.strip().lower(), 'bad')
        if taker == 'bad':
            raise LedgerError('is_taker: expected true/false')
    return Fill(
        fill_id=str(raw.get('fill_id') or '').strip(), ticker=ticker(raw.get('ticker')),
        side=choice(raw.get('side'), SIDES, 'side'), action=choice(raw.get('action'), ACTIONS, 'action'),
        count=count(raw.get('count')), price=price(raw.get('price'), price_unit), fee=fee(raw.get('fee')),
        ts=timestamp(raw.get('ts'), tz), order_id=str(raw.get('order_id') or '').strip(),
        is_taker=taker, source=choice(source, SOURCES, 'source'), note=str(raw.get('note') or '')[:500])


def make_settlement(raw: dict, *, tz: str = 'America/Chicago', source: str = 'manual') -> Settlement:
    def opt(k):
        v = raw.get(k)
        return None if v in (None, '') else dec(v, k)
    rev = dec(raw.get('revenue'), 'revenue')
    if rev < 0:
        raise LedgerError('revenue: must not be negative')
    for k in ('yes_count', 'no_count', 'yes_total_cost', 'no_total_cost'):
        v = opt(k)
        if v is not None and v < 0:
            raise LedgerError(f'{k}: must not be negative')
    return Settlement(
        settlement_id=str(raw.get('settlement_id') or '').strip(), ticker=ticker(raw.get('ticker')),
        market_result=choice(raw.get('market_result'), RESULTS, 'market_result'),
        settled_ts=timestamp(raw.get('settled_ts'), tz), revenue=rev, fee=fee(raw.get('fee')),
        yes_count=opt('yes_count'), no_count=opt('no_count'), yes_total_cost=opt('yes_total_cost'),
        no_total_cost=opt('no_total_cost'), source=choice(source, SOURCES, 'source'))


def make_cash(raw: dict, *, tz: str = 'America/Chicago', source: str = 'manual') -> CashTransaction:
    kind = choice(raw.get('kind'), CASH_KINDS, 'kind')
    amt = dec(raw.get('amount'), 'amount')
    if kind == 'deposit' and amt <= 0:
        raise LedgerError('amount: a deposit must be positive')
    if kind == 'withdrawal' and amt >= 0:
        raise LedgerError('amount: a withdrawal must be negative')
    return CashTransaction(txn_id=str(raw.get('txn_id') or '').strip(), ts=timestamp(raw.get('ts'), tz), kind=kind,
                           amount=amt, note=str(raw.get('note') or '')[:500], source=choice(source, SOURCES, 'source'))
