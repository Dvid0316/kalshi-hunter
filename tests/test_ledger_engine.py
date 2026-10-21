"""Ledger engine: hand-computed scenarios plus a property test against an independent oracle.

The oracle is deliberately a different method from the engine (aggregate cash flows, no per-trade
cost basis, no order dependence) and uses fractions.Fraction, so agreement is meaningful.
"""
import random
from decimal import Decimal as D
from fractions import Fraction

import pytest

from kh.ledger import models as M
from kh.ledger import engine as E


def F(i, side, action, count, price, fee='0', ts=None, ticker='T1'):
    ts = ts if ts is not None else i
    return M.Fill(str(i), ticker, side, action, D(str(count)), D(str(price)), D(str(fee)), float(ts), seq=i)


def S(ticker='T1', result='yes', revenue='0', fee='0', ts=1000, yes=None, no=None, i='s1'):
    return M.Settlement(i, ticker, result, float(ts), D(revenue), D(fee),
                        None if yes is None else D(str(yes)), None if no is None else D(str(no)))


# ---------------------------------------------------------------- hand-computed scenarios
@pytest.mark.parametrize('side,price,result,revenue,want', [
    ('yes', '0.40', 'yes', '10', '5.80'),    # 10*(1-0.40) - 0.20 fee
    ('yes', '0.40', 'no', '0', '-4.20'),     # lose cost + fee
    ('no', '0.35', 'no', '10', '6.30'),      # 10*(1-0.35) - 0.20
    ('no', '0.35', 'yes', '0', '-3.70'),
])
def test_held_to_settlement_four_outcomes(side, price, result, revenue, want):
    r = E.compute([F(1, side, 'buy', 10, price, '0.20')], [S(result=result, revenue=revenue, yes=10 if side == 'yes' else 0, no=10 if side == 'no' else 0)])
    m = r.markets['T1']
    assert m.realized == D(want) and m.status == 'settled' and not m.incomplete and m.flags == []
    assert r.realized_total == D(want)


def test_round_trip_trade_scalp():
    r = E.compute([F(1, 'yes', 'buy', 30, '0.30', '0.45'), F(2, 'yes', 'sell', 30, '0.38', '0.47')])
    m = r.markets['T1']
    assert m.realized == D('1.48') and m.status == 'closed' and m.qty == 0 and m.cost_basis == 0
    assert m.avg_entry_price == D('0.30') and m.avg_exit_price == D('0.38')
    assert m.fees == D('0.92')


def test_partial_close_average_cost_and_open_remainder():
    r = E.compute([F(1, 'yes', 'buy', 40, '0.55', '0.70'), F(2, 'yes', 'sell', 15, '0.62', '0.25')])
    m = r.markets['T1']
    assert m.realized == D('9.05') - D('22.70') * 15 / 40 == D('0.5375')
    assert m.qty == 25 and m.cost_basis == D('14.1875') and m.status == 'open'
    assert m.avg_entry == D('14.1875') / 25


def test_buying_the_other_side_nets_the_position():
    r = E.compute([F(1, 'yes', 'buy', 10, '0.40', '0.17'), F(2, 'no', 'buy', 10, '0.55', '0.17')])
    m = r.markets['T1']
    # sold YES at 1-0.55=0.45: proceeds 4.50-0.17 ; cost 4.00+0.17
    assert m.realized == D('0.16') and m.qty == 0 and m.status == 'closed'
    assert r.events[0].kind == 'net' and r.events[0].exit_price == D('0.45')


def test_netting_more_than_held_flips_into_the_other_side_and_splits_the_fee():
    r = E.compute([F(1, 'yes', 'buy', 10, '0.40', '0'), F(2, 'no', 'buy', 15, '0.55', '0.30')])
    m = r.markets['T1']
    assert (m.side, m.qty) == ('no', D(5))
    # 10 netted: 10*0.45 - fee(0.30*10/15=0.20) - cost 4.00 = 0.30 ; 5 NO opened with fee 0.10
    assert m.realized == D('0.30') and m.cost_basis == D('5') * D('0.55') + D('0.10')


def test_settlement_uses_recorded_revenue_but_flags_disagreement():
    r = E.compute([F(1, 'yes', 'buy', 10, '0.50', '0')], [S(result='yes', revenue='9', yes=10, no=0)])
    m = r.markets['T1']
    assert m.realized == D('4.00')                      # 9 recorded - 5.00 cost
    assert [f.code for f in m.flags] == ['settlement_revenue_mismatch'] and not m.incomplete


def test_settlement_count_mismatch_makes_market_unavailable_not_estimated():
    r = E.compute([F(1, 'yes', 'buy', 10, '0.50', '0')], [S(result='yes', revenue='12', yes=12, no=0)])
    m = r.markets['T1']
    assert m.incomplete and m.realized is None
    assert 'settlement_position_mismatch' in {f.code for f in m.flags}
    assert r.realized_total is None and r.n_incomplete == 1       # nothing verifiable -> Unavailable, not $0


def test_sell_without_buy_is_incomplete():
    r = E.compute([F(1, 'yes', 'sell', 10, '0.70', '0.15')])
    m = r.markets['T1']
    assert m.incomplete and m.realized is None and m.fees == D('0.15')
    assert m.flags[0].code == 'sell_without_position'


def test_oversell_flags_and_does_not_crash():
    r = E.compute([F(1, 'yes', 'buy', 5, '0.40'), F(2, 'yes', 'sell', 8, '0.50', '0.08')])
    m = r.markets['T1']
    assert m.incomplete and m.realized is None and 'sell_exceeds_position' in {f.code for f in m.flags}


def test_settlement_without_fills_and_revenue_without_position():
    r = E.compute([], [S(result='yes', revenue='10')])
    assert r.markets['T1'].incomplete and 'settlement_without_fills' in {f.code for f in r.markets['T1'].flags}
    r = E.compute([F(1, 'yes', 'buy', 5, '0.4'), F(2, 'yes', 'sell', 5, '0.5')], [S(result='yes', revenue='10')])
    assert 'revenue_without_position' in {f.code for f in r.markets['T1'].flags}


def test_nonbinary_and_late_fill_and_multiple_settlements_are_flagged():
    r = E.compute([F(1, 'yes', 'buy', 10, '0.50', ts=1), F(2, 'yes', 'buy', 1, '0.5', ts=2000)],
                  [S(result='void', revenue='5', ts=1000)])
    codes = {f.code for f in r.markets['T1'].flags}
    assert {'nonbinary_settlement', 'fill_after_settlement'} <= codes
    r = E.compute([F(1, 'yes', 'buy', 1, '0.5')], [S(i='a', revenue='1', ts=10), S(i='b', revenue='1', ts=20)])
    assert r.markets['T1'].incomplete


def test_unrealized_requires_a_fresh_executable_exit_quote():
    fills = [F(1, 'yes', 'buy', 10, '0.40', '0.20'), F(2, 'no', 'buy', 4, '0.30', '0.10', ticker='T2')]
    marks = {'T1': E.Mark(990.0, D('0.50'), D('0.52')), 'T2': E.Mark(990.0, D('0.60'), D('0.64'))}
    r = E.compute(fills, marks=marks, now=1000.0)
    t1, t2 = r.markets['T1'], r.markets['T2']
    assert t1.unrealized == D('10') * D('0.50') - D('4.20')           # sells at the YES bid
    assert t2.unrealized == D('4') * (1 - D('0.64')) - D('1.30')      # NO exits at 1 - YES ask
    assert r.unrealized_total == t1.unrealized + t2.unrealized and r.n_marked == 2
    stale = E.compute(fills, marks=marks, now=990 + 301)
    assert stale.markets['T1'].unrealized is None and stale.unrealized_total is None
    assert 'too old' in stale.markets['T1'].unrealized_reason
    nobid = E.compute(fills[:1], marks={'T1': E.Mark(990.0, None, D('0.52'))}, now=1000.0)
    assert nobid.markets['T1'].unrealized is None
    assert E.compute(fills, now=1000.0).unrealized_total is None       # no marks at all


def test_unrealized_total_is_unavailable_if_any_open_position_is_unmarked():
    fills = [F(1, 'yes', 'buy', 10, '0.40'), F(2, 'yes', 'buy', 10, '0.40', ticker='T2')]
    r = E.compute(fills, marks={'T1': E.Mark(995.0, D('0.5'), D('0.52'))}, now=1000.0)
    assert r.markets['T1'].unrealized is not None and r.unrealized_total is None and r.n_marked == 1


def test_possible_duplicate_fills_are_flagged_not_dropped():
    a = F(1, 'yes', 'buy', 5, '0.40', ts=100)
    b = M.Fill('2', 'T1', 'yes', 'buy', D(5), D('0.40'), D(0), 100.0, seq=2)
    r = E.compute([a, b])
    assert r.markets['T1'].qty == 10 and 'possible_duplicate_fills' in {f.code for f in r.flags}


def test_cash_transactions_never_affect_trading_pnl():
    cash = [M.CashTransaction('c1', 1.0, 'deposit', D('500')), M.CashTransaction('c2', 2.0, 'withdrawal', D('-120.50'))]
    r = E.compute([F(1, 'yes', 'buy', 1, '0.5')], cash=iter(cash))      # generator input must work
    assert r.cash_net == D('379.50') and r.cash_count == 2 and r.realized_total == D(0)


def test_decimal_precision_no_binary_artifacts():
    # 0.1 + 0.2 style traps: three fills of 0.1 qty at 0.1 price
    r = E.compute([F(i, 'yes', 'buy', '0.1', '0.1', '0.001') for i in (1, 2, 3)] + [F(4, 'yes', 'sell', '0.3', '0.2', '0.003')])
    assert r.markets['T1'].realized == D('0.3') * D('0.2') - D('0.003') - (D('0.1') * D('0.1') * 3 + D('0.003'))


# ---------------------------------------------------------------- independent oracle (property test)
def frac(x):
    return Fraction(str(x))


def oracle_closed_pnl(fills, settlement=None):
    """Order-independent total P&L of a market that ends flat or settled."""
    sells = sum(frac(f.count) * frac(f.price) for f in fills if f.action == 'sell')
    buys = sum(frac(f.count) * frac(f.price) for f in fills if f.action == 'buy')
    fees = sum(frac(f.fee) for f in fills)
    b = {s: sum(frac(f.count) for f in fills if f.side == s and f.action == 'buy') for s in ('yes', 'no')}
    sd = {s: sum(frac(f.count) for f in fills if f.side == s and f.action == 'sell') for s in ('yes', 'no')}
    ry, rn = b['yes'] - sd['yes'], b['no'] - sd['no']
    pairs = min(ry, rn)
    payout = Fraction(0)
    if settlement is not None:
        left_yes, left_no = ry - pairs, rn - pairs
        payout = left_yes if settlement.market_result == 'yes' else left_no
        fees += frac(settlement.fee)
    return sells - buys + pairs + payout - fees


def random_market(rng, ticker='T1'):
    pos, fills, t = 0, [], 0
    for _ in range(rng.randint(1, 14)):
        t += rng.randint(1, 50)
        count = rng.randint(1, 20)
        price = D(rng.randint(1, 99)) / 100
        fee = D(rng.randint(0, 40)) / 100
        choices = ['buy_yes', 'buy_no']
        if pos > 0:
            choices.append('sell_yes')
        if pos < 0:
            choices.append('sell_no')
        pick = rng.choice(choices)
        if pick == 'buy_yes':
            fills.append(F(t, 'yes', 'buy', count, price, fee, t, ticker)); pos += count
        elif pick == 'buy_no':
            fills.append(F(t, 'no', 'buy', count, price, fee, t, ticker)); pos -= count
        elif pick == 'sell_yes':
            k = rng.randint(1, min(count, pos)); fills.append(F(t, 'yes', 'sell', k, price, fee, t, ticker)); pos -= k
        else:
            k = rng.randint(1, min(count, -pos)); fills.append(F(t, 'no', 'sell', k, price, fee, t, ticker)); pos += k
    return fills, pos, t


@pytest.mark.parametrize('seed', range(40))
def test_engine_matches_independent_oracle_on_random_markets(seed):
    rng = random.Random(seed)
    for n in range(25):
        fills, pos, t = random_market(rng)
        mode = rng.choice(['settle', 'flat'])
        if mode == 'flat' and pos != 0:                       # close out by selling the held side
            side = 'yes' if pos > 0 else 'no'
            t += 1
            fills.append(F(t, side, 'sell', abs(pos), D(rng.randint(1, 99)) / 100, D('0.07'), t)); pos = 0
        settlement = None
        if mode == 'settle':
            result = rng.choice(['yes', 'no'])
            win = (pos > 0 and result == 'yes') or (pos < 0 and result == 'no')
            revenue = D(abs(pos)) if win else D(0)
            settlement = S(result=result, revenue=str(revenue), fee=str(D(rng.randint(0, 20)) / 100), ts=t + 5,
                           yes=pos if pos > 0 else 0, no=-pos if pos < 0 else 0)
        rep = E.compute(fills, [settlement] if settlement else [])
        m = rep.markets['T1']
        assert not m.incomplete, (seed, n, m.flags)
        want = oracle_closed_pnl(fills, settlement)
        got = Fraction(str(m.realized))
        assert abs(got - want) < Fraction(1, 10 ** 30), (seed, n, m.realized, float(want))
        assert m.qty == 0 and m.cost_basis == 0
        assert m.fees == sum((f.fee for f in fills), D(0)) + (settlement.fee if settlement else 0)


def test_replay_is_order_stable_for_equal_timestamps():
    a = [F(1, 'yes', 'buy', 5, '0.4', ts=7), F(2, 'yes', 'sell', 5, '0.5', ts=7)]
    r1 = E.compute(a)
    r2 = E.compute(list(reversed(a)))          # compute() sorts by (ts, seq): input order must not matter
    assert r1.markets['T1'].realized == r2.markets['T1'].realized == D('0.5')


# ---------------------------------------------------------------- boundary validation
@pytest.mark.parametrize('bad', [
    dict(price=0.4), dict(price='0'), dict(price='1'), dict(price='1.2'), dict(price='nan'), dict(price='abc'),
    dict(count='0'), dict(count='-3'), dict(count=2.5), dict(fee='-0.01'), dict(side='maybe'), dict(action='hold'),
    dict(ticker=''), dict(ticker='bad ticker!'), dict(ts=None), dict(ts='not a time')])
def test_fill_validation_rejects(bad):
    raw = dict(ticker='T1', side='yes', action='buy', count='5', price='0.4', fee='0.1', ts='2026-10-21T10:00:00-05:00')
    raw.update(bad)
    with pytest.raises(M.LedgerError):
        M.make_fill(raw)


def test_fill_parsing_units_and_timezones():
    raw = dict(ticker='T1', side='YES', action='Buy', count='5', price='40', fee='$0.10', ts='2026-10-21T10:00:00')
    f = M.make_fill(raw, price_unit='cents')
    assert f.price == D('0.4') and f.fee == D('0.10') and f.side == 'yes'
    # naive timestamp is read as America/Chicago (CDT = UTC-5 on this date)
    assert f.ts == M.timestamp('2026-10-21T15:00:00+00:00')
    assert M.timestamp('1792600000') == 1792600000.0


def test_settlement_and_cash_validation():
    with pytest.raises(M.LedgerError):
        M.make_settlement(dict(ticker='T1', market_result='maybe', settled_ts='1792600000', revenue='1'))
    with pytest.raises(M.LedgerError):
        M.make_settlement(dict(ticker='T1', market_result='yes', settled_ts='1792600000', revenue='-1'))
    with pytest.raises(M.LedgerError):
        M.make_cash(dict(kind='withdrawal', amount='50', ts='1792600000'))     # withdrawals must be negative
    assert M.make_cash(dict(kind='deposit', amount='$1,250.50', ts='1792600000')).amount == D('1250.50')
