"""Position and P&L engine for the personal ledger. Pure functions, Decimal only, no I/O.

Accounting model (documented because the numbers are the user's real money)
---------------------------------------------------------------------------
* A market has a single net position: YES contracts *or* NO contracts, never both. Buying the
  opposite side of what you hold nets against it (one YES + one NO always pays exactly $1), which
  is how the exchange reports positions. Netting a pair is treated as *selling* the held side at
  ``1 - price_paid_for_the_other_side``.
* Cost basis is average-cost and includes entry fees. Closing fees reduce proceeds. A fill that
  both closes and opens (flips) has its fee split pro rata by contract count.
* Realised P&L (net of all fees) = proceeds from closing/netting + settlement payout
  - cost basis of what was closed. Settlement uses the RECORDED revenue (authoritative); the
  position-derived payout is only a cross-check and any difference is flagged.
* Unrealised P&L exists only when a fresh executable *exit* quote is supplied (held-side bid) and
  is reported before exit fees. Otherwise it is None -> "Unavailable". Never zero.
* If the history is internally impossible (selling more than held, settlement with no/other position,
  count mismatch) the market is flagged ``incomplete`` and its realised P&L is None. It is excluded
  from totals and counted, never silently estimated.

The independent oracle used by the tests is order-independent and shares no code with this module:
P&L(closed market) = sell cash - buy cash + $1 x netted pairs + settlement payout - fees.
"""
from __future__ import annotations

import decimal
from dataclasses import dataclass, field
from decimal import Decimal

from .models import Fill, Settlement, CashTransaction, ZERO, ONE

_CTX = decimal.Context(prec=60, rounding=decimal.ROUND_HALF_EVEN)
TOLERANCE = Decimal('0.005')      # revenue cross-check tolerance (half a cent)
CENT = Decimal('0.01')            # cent-level tolerance for recorded-cost cross-checks


@dataclass(frozen=True)
class Flag:
    code: str
    severity: str       # 'info' | 'warn' | 'error'
    message: str


@dataclass(frozen=True)
class Mark:
    """An executable exit quote for the *YES* contract at ``ts`` (epoch seconds)."""
    ts: float
    yes_bid: Decimal | None
    yes_ask: Decimal | None


@dataclass
class RealizedEvent:
    ts: float
    ticker: str
    kind: str              # 'close' | 'net' | 'settlement'
    side: str
    qty: Decimal
    entry_avg: Decimal     # average cost per contract incl. entry fees
    exit_price: Decimal    # price received per contract before the closing fee
    fee: Decimal
    pnl: Decimal           # net of fees


@dataclass
class MarketLedger:
    ticker: str
    status: str = 'open'              # open | closed | settled
    side: str | None = None           # held side (open positions)
    qty: Decimal = ZERO               # held contracts
    cost_basis: Decimal = ZERO        # dollars incl. entry fees for held contracts
    avg_entry: Decimal | None = None  # per held contract, incl. fees
    realized: Decimal | None = ZERO   # final value; None when incomplete
    _running: Decimal = ZERO          # internal running total
    fees: Decimal = ZERO              # every fee charged on this market (fills + settlement)
    opened_qty: Decimal = ZERO
    open_notional: Decimal = ZERO     # sum(count*price) of opening pieces, excl. fees
    closed_qty: Decimal = ZERO
    close_notional: Decimal = ZERO    # sum(count*exit price) of closing pieces, excl. fees
    first_ts: float | None = None
    last_ts: float | None = None
    settled_ts: float | None = None
    result: str | None = None
    settlement_revenue: Decimal | None = None
    record_pnl: Decimal | None = None  # revenue - recorded costs - fee, as the exchange record states (info only)
    incomplete: bool = False
    flags: list = field(default_factory=list)
    unrealized: Decimal | None = None
    unrealized_reason: str = ''
    mark_value: Decimal | None = None
    sides: set = field(default_factory=set)      # sides ever traded; both => averages would mix YES and NO

    @property
    def avg_entry_price(self):
        return (self.open_notional / self.opened_qty) if self.opened_qty else None

    @property
    def avg_exit_price(self):
        return (self.close_notional / self.closed_qty) if self.closed_qty else None


@dataclass
class Report:
    markets: dict
    events: list
    cash_net: Decimal
    cash_count: int
    flags: list                          # global flags (possible duplicates, etc.)

    # ---- aggregates (None means unavailable, never an estimate)
    def _complete(self):
        return [m for m in self.markets.values() if not m.incomplete]

    @property
    def n_incomplete(self):
        return sum(1 for m in self.markets.values() if m.incomplete)

    @property
    def realized_total(self):
        # Only closed/settled markets contribute to the headline, plus realised portions of open ones.
        ms = self._complete()
        if not ms:                       # nothing verifiable -> unavailable, not $0.00
            return None
        return sum((m.realized for m in ms), ZERO)

    @property
    def fees_total(self):
        return sum((m.fees for m in self.markets.values()), ZERO) if self.markets else None

    @property
    def open_positions(self):
        return [m for m in self.markets.values() if m.status == 'open' and m.qty > 0]

    @property
    def closed_positions(self):
        return [m for m in self.markets.values() if m.status in ('closed', 'settled')]

    @property
    def open_cost_basis(self):
        return sum((m.cost_basis for m in self.open_positions), ZERO) if self.markets else None

    @property
    def unrealized_total(self):
        op = [m for m in self.open_positions if not m.incomplete]
        if not op or any(m.unrealized is None for m in op):
            return None
        return sum((m.unrealized for m in op), ZERO)

    @property
    def n_marked(self):
        return sum(1 for m in self.open_positions if m.unrealized is not None)


@dataclass
class _Pos:
    """Running net position while replaying one market's fills."""
    side: str | None = None
    qty: Decimal = ZERO
    basis: Decimal = ZERO


def _other(side):
    return 'no' if side == 'yes' else 'yes'


def _realize(m: MarketLedger, pos: _Pos, k, price, fee_part, ts, kind):
    """Close ``k`` of the held contracts at ``price`` per contract (held-side terms)."""
    c = _CTX
    proceeds = c.subtract(c.multiply(k, price), fee_part)
    cost = pos.basis if k == pos.qty else c.divide(c.multiply(pos.basis, k), pos.qty)
    entry_avg = c.divide(cost, k)
    pnl = c.subtract(proceeds, cost)
    pos.qty = c.subtract(pos.qty, k)
    pos.basis = c.subtract(pos.basis, cost) if pos.qty else ZERO
    m._running = c.add(m._running, pnl)
    m.closed_qty = c.add(m.closed_qty, k)
    m.close_notional = c.add(m.close_notional, c.multiply(k, price))
    return RealizedEvent(ts, m.ticker, kind, pos.side, k, entry_avg, price, fee_part, pnl)


def compute(fills, settlements=(), cash=(), *, marks=None, now=None, mark_max_age=300.0) -> Report:
    """Build the full ledger report from validated records (already excluding voided ones)."""
    c = _CTX
    cash = list(cash)
    by_ticker: dict[str, list] = {}
    for f in sorted(fills, key=lambda x: (x.ts, x.seq)):
        by_ticker.setdefault(f.ticker.upper(), []).append(f)
    settle: dict[str, list] = {}
    for s in settlements:
        settle.setdefault(s.ticker.upper(), []).append(s)
    markets, events, gflags = {}, [], []
    for t in sorted(set(by_ticker) | set(settle)):
        m = MarketLedger(ticker=t)
        pos = _Pos()
        for f in by_ticker.get(t, []):
            m.fees = c.add(m.fees, f.fee)
            m.sides.add(f.side)
            m.first_ts = f.ts if m.first_ts is None else min(m.first_ts, f.ts)
            m.last_ts = f.ts if m.last_ts is None else max(m.last_ts, f.ts)
            if f.action == 'buy':
                k_close = min(f.count, pos.qty) if (pos.side == _other(f.side) and pos.qty > 0) else ZERO
                fee_close = (f.fee if k_close == f.count else c.divide(c.multiply(f.fee, k_close), f.count)) if k_close else ZERO
                if k_close:
                    ev = _realize(m, pos, k_close, c.subtract(ONE, f.price), fee_close, f.ts, 'net')
                    events.append(ev)
                    if pos.qty == 0:
                        pos.side = None
                k_open = c.subtract(f.count, k_close)
                if k_open > 0:
                    if pos.qty == 0:
                        pos.side = f.side
                    pos.qty = c.add(pos.qty, k_open)
                    pos.basis = c.add(pos.basis, c.add(c.multiply(k_open, f.price), c.subtract(f.fee, fee_close)))
                    m.opened_qty = c.add(m.opened_qty, k_open)
                    m.open_notional = c.add(m.open_notional, c.multiply(k_open, f.price))
            else:  # sell
                if pos.side != f.side or pos.qty <= 0:
                    m.incomplete = True
                    m.flags.append(Flag('sell_without_position', 'error',
                                        f'Sold {f.count} {f.side.upper()} on {t} with no matching position: earlier buy fills are missing.'))
                    continue
                k = min(f.count, pos.qty)
                if f.count > pos.qty:
                    m.incomplete = True
                    m.flags.append(Flag('sell_exceeds_position', 'error',
                                        f'Sold {f.count} {f.side.upper()} but only {pos.qty} were held: earlier buy fills are missing.'))
                fee_part = f.fee if k == f.count else c.divide(c.multiply(f.fee, k), f.count)
                events.append(_realize(m, pos, k, f.price, fee_part, f.ts, 'close'))
                if pos.qty == 0:
                    pos.side = None
        # ------------------------------------------------------------ settlement
        sl = settle.get(t, [])
        if len(sl) > 1:
            m.incomplete = True
            m.flags.append(Flag('multiple_settlements', 'error', f'{len(sl)} settlement records exist for {t}.'))
        if sl:
            s = sorted(sl, key=lambda x: x.settled_ts)[-1]
            m.settled_ts, m.result, m.settlement_revenue = s.settled_ts, s.market_result, s.revenue
            for x in sl:                                  # every settlement fee was really charged, even if the records conflict
                m.fees = c.add(m.fees, x.fee)
            late = [f for f in by_ticker.get(t, []) if f.ts > s.settled_ts]
            if late:
                m.incomplete = True
                m.flags.append(Flag('fill_after_settlement', 'error', f'{len(late)} fill(s) are dated after settlement of {t}: a timestamp is wrong or the settlement belongs to another position.'))
            if s.yes_total_cost is not None and s.no_total_cost is not None:
                m.record_pnl = c.subtract(c.subtract(s.revenue, c.add(s.yes_total_cost, s.no_total_cost)), s.fee)
                recorded_cost = c.add(s.yes_total_cost, s.no_total_cost)
                if m.open_notional and abs(recorded_cost - m.open_notional) > CENT:
                    m.flags.append(Flag('recorded_cost_mismatch', 'warn',
                                        f'Settlement records ${recorded_cost} of cost for {t} while the fills total ${m.open_notional}: '
                                        'one of the two is missing something.'))
            remaining, basis, side = pos.qty, pos.basis, pos.side
            if s.market_result in ('yes', 'no'):
                derived = remaining if (remaining > 0 and side == s.market_result) else ZERO
                if abs(derived - s.revenue) > TOLERANCE:
                    m.incomplete = True
                    m.flags.append(Flag('settlement_revenue_mismatch', 'error',
                                        f'Recorded revenue ${s.revenue} differs from the ${derived} implied by the fills for {t}: fills are missing '
                                        'or the amount/unit is wrong. No P&L is shown until it is corrected.'))
                exp_yes = remaining if side == 'yes' else ZERO
                exp_no = remaining if side == 'no' else ZERO
                if (s.yes_count is not None and s.yes_count != exp_yes) or (s.no_count is not None and s.no_count != exp_no):
                    m.incomplete = True
                    m.flags.append(Flag('settlement_position_mismatch', 'error',
                                        f'Settlement of {t} recorded YES={s.yes_count} NO={s.no_count}, but the fills imply '
                                        f'YES={exp_yes} NO={exp_no}: fills are missing or wrong.'))
            else:
                m.flags.append(Flag('nonbinary_settlement', 'warn',
                                    f'{t} settled as {s.market_result!r}; P&L uses the recorded revenue. Review it manually.'))
                if s.market_result == 'void' and remaining > 0 and s.revenue == ZERO:
                    m.incomplete = True
                    m.flags.append(Flag('void_settlement_without_refund', 'error',
                                        f'{t} is recorded as voided with no payout although {remaining} contract(s) were held: '
                                        'a void normally refunds cost, so the fills or the amount are wrong. No P&L is shown.'))
                if remaining > 0 and s.revenue > remaining + TOLERANCE:
                    m.incomplete = True
                    m.flags.append(Flag('revenue_exceeds_position', 'error',
                                        f'{t} ({s.market_result}) paid ${s.revenue} but the fills leave only {remaining} contract(s), '
                                        f'which can pay at most ${remaining}: fills are missing or the amount is wrong.'))
            if remaining == 0 and s.revenue > 0:
                m.incomplete = True
                m.flags.append(Flag('revenue_without_position', 'error',
                                    f'{t} paid ${s.revenue} at settlement but the fills leave no position: fills are missing.'))
            if not by_ticker.get(t):
                m.incomplete = True
                m.flags.append(Flag('settlement_without_fills', 'error', f'{t} has a settlement but no fills.'))
            exit_per = c.divide(s.revenue, remaining) if remaining > 0 else ZERO
            pnl = c.subtract(c.subtract(s.revenue, s.fee), basis)
            if remaining > 0:
                m.closed_qty = c.add(m.closed_qty, remaining)
                m.close_notional = c.add(m.close_notional, s.revenue)
                events.append(RealizedEvent(s.settled_ts, t, 'settlement', side or '', remaining,
                                            c.divide(basis, remaining), exit_per, s.fee, pnl))
            elif s.revenue > 0 or s.fee > 0:
                events.append(RealizedEvent(s.settled_ts, t, 'settlement', side or '', ZERO, ZERO, ZERO, s.fee, pnl))
            m._running = c.add(m._running, pnl)
            m.status = 'settled'
            pos = _Pos()
        elif pos.qty == 0 and by_ticker.get(t):
            m.status = 'closed'
        # ------------------------------------------------------------ open position state
        m.side, m.qty, m.cost_basis = pos.side, pos.qty, pos.basis
        m.avg_entry = c.divide(pos.basis, pos.qty) if pos.qty > 0 else None
        if m.qty > 0 and not m.incomplete:
            _mark(m, (marks or {}).get(t), now, mark_max_age)
        elif m.qty > 0:
            m.unrealized_reason = 'History incomplete'
        m.realized = None if m.incomplete else m._running
        markets[t] = m
    # ---------------------------------------------------------------- global checks
    seen = {}
    for f in fills:
        key = (f.ticker, f.side, f.action, f.count, f.price, f.ts, f.order_id)
        seen.setdefault(key, []).append(f.fill_id)
    dup = [ids for ids in seen.values() if len(ids) > 1 and not any(i.startswith('syn:') for i in ids)]
    if dup:
        gflags.append(Flag('possible_duplicate_fills', 'warn',
                           f'{len(dup)} group(s) of fills share ticker, side, size, price, time and order but have different ids. '
                           'They are both counted; void one if it is a duplicate entry.'))
    if any(f.synthetic_id for f in fills):
        gflags.append(Flag('synthetic_ids', 'info', 'Some fills had no exchange id; deterministic ids were generated so re-imports stay idempotent.'))
    cash_net = sum((x.amount for x in cash), ZERO)
    events.sort(key=lambda e: (e.ts, e.ticker))
    return Report(markets=markets, events=events, cash_net=cash_net, cash_count=len(cash), flags=gflags)


def _mark(m: MarketLedger, mark, now, max_age):
    if mark is None:
        m.unrealized_reason = 'No quote'
        return
    if now is None or not (0 <= now - mark.ts <= max_age):
        m.unrealized_reason = 'Quote too old to mark'
        return
    quotes = [q for q in (mark.yes_bid, mark.yes_ask) if q is not None]
    if any(not isinstance(q, Decimal) or not (ZERO <= q <= ONE) for q in quotes):
        m.unrealized_reason = 'Invalid quote (must be Decimal dollars between 0 and 1)'
        return
    if any(q.as_tuple().exponent < -10 for q in quotes):
        m.unrealized_reason = 'Invalid quote (binary float artifact, not an exact decimal price)'
        return
    if mark.yes_bid is not None and mark.yes_ask is not None and mark.yes_bid > mark.yes_ask:
        m.unrealized_reason = 'Crossed quote'
        return
    bid = mark.yes_bid if m.side == 'yes' else (None if mark.yes_ask is None else ONE - mark.yes_ask)
    if bid is None:
        m.unrealized_reason = 'No bid on the held side'
        return
    m.mark_value = _CTX.multiply(m.qty, bid)
    m.unrealized = _CTX.subtract(m.mark_value, m.cost_basis)
