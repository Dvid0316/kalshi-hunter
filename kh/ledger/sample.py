"""Synthetic SAMPLE data so the personal-trading screens can be inspected before any real account
is connected. It is NEVER loaded unless the app is started with ``--sample-account``, lives in its own
file (``var/sample/account.db``), and every account screen carries a persistent banner while it is active.

These numbers are invented. They exist only to exercise the views and tests.
"""
from __future__ import annotations

from pathlib import Path

from . import models as M
from .store import AccountStore

DAY = 86400
T0 = 1792607000  # anchor near the snapshot date; offsets below are relative


def sample_records():
    fills, settlements, cash = [], [], []

    def fill(i, ticker, side, action, count, price, fee, dt):
        fills.append(dict(fill_id=f'sample-f-{i:03d}', ticker=ticker, side=side, action=action, count=count, price=price,
                          fee=fee, ts=T0 + dt, order_id=f'sample-o-{i:03d}', is_taker=True))

    # 1 winner held to settlement
    fill(1, 'SAMPLE-WIN-1', 'yes', 'buy', '20', '0.42', '0.43', -6 * DAY)
    settlements.append(dict(settlement_id='sample-s-001', ticker='SAMPLE-WIN-1', market_result='yes',
                            settled_ts=T0 - 2 * DAY, yes_count='20', no_count='0', revenue='20.00', fee='0'))
    # 2 loser held to settlement (NO bought, YES won)
    fill(2, 'SAMPLE-LOSS-1', 'no', 'buy', '10', '0.60', '0.17', -5 * DAY)
    settlements.append(dict(settlement_id='sample-s-002', ticker='SAMPLE-LOSS-1', market_result='yes',
                            settled_ts=T0 - 3600, yes_count='0', no_count='10', revenue='0', fee='0'))
    # 3 scalp closed by trading
    fill(3, 'SAMPLE-SCALP-1', 'yes', 'buy', '30', '0.30', '0.45', -4 * DAY)
    fill(4, 'SAMPLE-SCALP-1', 'yes', 'sell', '30', '0.38', '0.47', -4 * DAY + 7200)
    # 4 partially closed, still open
    fill(5, 'SAMPLE-PARTIAL-1', 'yes', 'buy', '40', '0.55', '0.70', -3 * DAY)
    fill(6, 'SAMPLE-PARTIAL-1', 'yes', 'sell', '15', '0.62', '0.25', -3 * DAY + 3600)
    # 5 netted pair (buy YES, then buy NO against it)
    fill(7, 'SAMPLE-NET-1', 'yes', 'buy', '10', '0.40', '0.17', -2 * DAY)
    fill(8, 'SAMPLE-NET-1', 'no', 'buy', '10', '0.55', '0.17', -2 * DAY + 600)
    # 6/7 open positions in markets that Grok's research also covers
    fill(9, 'CONTROLS-2026-D', 'no', 'buy', '10', '0.36', '0.17', -1800)
    fill(10, 'KXAPRPOTUS-26OCT23-38.5', 'yes', 'buy', '5', '0.27', '0.10', -900)
    # 8 impossible history: sell with no earlier buy (missing fills)
    fill(11, 'SAMPLE-INCOMPLETE-1', 'yes', 'sell', '10', '0.70', '0.15', -1 * DAY)
    # 9 settlement disagrees with the fills (recorded 12 YES, fills say 10)
    fill(12, 'SAMPLE-MISMATCH-1', 'yes', 'buy', '10', '0.50', '0.18', -5 * DAY)
    settlements.append(dict(settlement_id='sample-s-003', ticker='SAMPLE-MISMATCH-1', market_result='yes',
                            settled_ts=T0 - 4 * DAY, yes_count='12', no_count='0', revenue='12.00', fee='0'))
    cash.append(dict(txn_id='sample-c-001', ts=T0 - 10 * DAY, kind='deposit', amount='500.00', note='SAMPLE deposit'))
    journal = [
        dict(title='SAMPLE: Senate control - why NO', ticker='CONTROLS-2026-D', entry_type='pre_trade', planned_side='no',
             planned_price='0.36', my_prob='0.55', tags='sample,politics',
             body='SAMPLE ENTRY. Model spread is wide; paying the NO ask looked cheaper than the models implied.'),
        dict(title='SAMPLE: RCP approval bracket', ticker='KXAPRPOTUS-26OCT23-38.5', entry_type='pre_trade',
             planned_side='yes', planned_price='0.27', my_prob='0.30', tags='sample,polling',
             body='SAMPLE ENTRY. Disagrees with the recorded research on side.'),
        dict(title='SAMPLE: sizing rule', entry_type='note', tags='sample,process',
             body='SAMPLE ENTRY. Keep each position under 2% of the bankroll.'),
    ]
    return fills, settlements, cash, journal


def build_sample_store(path) -> AccountStore:
    path = Path(path)
    for ext in ('', '-wal', '-shm'):
        Path(str(path) + ext).unlink(missing_ok=True)      # regenerate: the sample file is disposable
    store = AccountStore(path)
    fills, settlements, cash, journal = sample_records()
    store.add_fills([M.make_fill(r, source='sample') for r in fills], source='sample', label='SAMPLE')
    store.add_settlements([M.make_settlement(r, source='sample') for r in settlements], source='sample', label='SAMPLE')
    store.add_cash([M.make_cash(r, source='sample') for r in cash], source='sample', label='SAMPLE')
    for j in journal:
        store.journal_add(**j)
    return store
