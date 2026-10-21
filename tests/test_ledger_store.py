"""Ledger store, importer, journal and evidence-isolation tests."""
import json
import sqlite3
from decimal import Decimal as D

import pytest

from kh.ledger import engine as E, importers, models as M, sample
from kh.ledger.compare import compare
from kh.ledger.store import AccountStore, StoreError

FILLS_CSV = """fill_id,ticker,side,action,count,price,fee,ts,order_id
f1,KXTEST-1,yes,buy,10,0.40,0.20,2026-10-21T10:00:00-05:00,o1
f2,KXTEST-1,yes,sell,10,0.55,0.20,2026-10-21T11:00:00-05:00,o2
"""


@pytest.fixture
def store(tmp_path):
    s = AccountStore(tmp_path / 'account.db')
    yield s
    s.close()


def write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text)
    return p


# ---------------------------------------------------------------- import & idempotency
def test_csv_import_is_idempotent(store, tmp_path):
    p = write(tmp_path, 'fills.csv', FILLS_CSV)
    r1 = importers.import_file(store, p)
    r2 = importers.import_file(store, p)
    assert (r1.n_new, r1.n_dup) == (2, 0) and (r2.n_new, r2.n_dup) == (0, 2)
    assert store.counts()['fills'] == 2
    rep = E.compute(store.fills())
    assert rep.markets['KXTEST-1'].realized == D('1.10')          # 10*(0.55-0.40) - 0.40 fees


def test_same_id_different_content_is_a_conflict_and_never_overwrites(store, tmp_path):
    importers.import_file(store, write(tmp_path, 'a.csv', FILLS_CSV))
    changed = FILLS_CSV.replace('0.40', '0.45', 1)
    r = importers.import_file(store, write(tmp_path, 'b.csv', changed))
    assert (r.n_new, r.n_dup, r.n_conflict) == (0, 1, 1)
    assert len(store.conflicts()) == 1
    rep = E.compute(store.fills())
    assert rep.markets['KXTEST-1'].realized == D('1.10')          # original books unchanged


def test_rows_without_ids_get_stable_synthetic_ids_and_identical_rows_stay_distinct(store, tmp_path):
    csv = ('ticker,side,action,count,price,fee,ts\n'
           'KXA,yes,buy,5,0.30,0.10,2026-10-21T10:00:00-05:00\n'
           'KXA,yes,buy,5,0.30,0.10,2026-10-21T10:00:00-05:00\n')       # two genuine identical fills
    p = write(tmp_path, 'noid.csv', csv)
    importers.import_file(store, p)
    importers.import_file(store, p)                                    # re-import must not double count
    fills = store.fills()
    assert len(fills) == 2 and all(f.synthetic_id for f in fills)
    assert len({f.fill_id for f in fills}) == 2


def test_bad_rows_are_rejected_individually_and_logged(store, tmp_path):
    csv = ('ticker,side,action,count,price,fee,ts\n'
           'KXA,yes,buy,5,0.30,0.10,2026-10-21T10:00:00-05:00\n'
           'KXA,yes,buy,5,1.30,0.10,2026-10-21T10:00:00-05:00\n'      # price out of range
           'KXA,yes,buy,-5,0.30,0.10,2026-10-21T10:00:00-05:00\n')    # negative count
    r = importers.import_file(store, write(tmp_path, 'bad.csv', csv))
    assert (r.n_new, r.n_rejected) == (1, 2)
    assert len(store.rejects()) == 2 and 'price' in store.rejects()[0]['reason']


def test_cents_json_and_kind_detection(store, tmp_path):
    csv = 'ticker,side,action,count,price,fee,ts\nKXA,no,buy,5,35,0.10,1792600000\n'
    importers.import_file(store, write(tmp_path, 'c.csv', csv), price_unit='cents')
    assert store.fills()[0].price == D('0.35')
    js = json.dumps({'records': [dict(kind='deposit', amount='100', ts='1792600000')]})
    r = importers.import_file(store, write(tmp_path, 'cash.json', js))
    assert r.kind == 'cash' and store.cash()[0].amount == D('100')
    with pytest.raises(M.LedgerError):
        importers.import_file(store, write(tmp_path, 'what.csv', 'foo,bar\n1,2\n'))


def test_oversize_file_is_refused(store, tmp_path, monkeypatch):
    monkeypatch.setattr(importers, 'MAX_BYTES', 50)
    with pytest.raises(M.LedgerError):
        importers.import_file(store, write(tmp_path, 'big.csv', FILLS_CSV))


def test_exact_decimal_round_trip(store):
    f = M.make_fill(dict(fill_id='x', ticker='KXA', side='yes', action='buy', count='3', price='0.123456', fee='0.0123', ts='1792600000'))
    store.add_fills([f])
    back = store.fills()[0]
    assert (back.price, back.fee, back.count) == (D('0.123456'), D('0.0123'), D('3'))


# ---------------------------------------------------------------- append-only, void, settlements
def test_ledger_tables_are_append_only(store, tmp_path):
    importers.import_file(store, write(tmp_path, 'a.csv', FILLS_CSV))
    store.journal_add(title='row must exist for a row-level trigger to fire')
    store.void('fills', 'f1', 'test')
    for sql in ("UPDATE fills SET price='0.01'", 'DELETE FROM fills', 'DELETE FROM import_batches',
                "UPDATE journal_revisions SET title='x'", "UPDATE journal_entries SET ticker='X'",
                'DELETE FROM voids', 'DELETE FROM journal_revisions'):
        with pytest.raises(sqlite3.DatabaseError):
            store.c.execute(sql)


def test_void_excludes_a_record_but_keeps_it(store, tmp_path):
    importers.import_file(store, write(tmp_path, 'a.csv', FILLS_CSV))
    store.void('fills', 'f2', 'entered twice by mistake')
    assert [f.fill_id for f in store.fills()] == ['f1']
    assert len(store.fills(include_voided=True)) == 2
    with pytest.raises(M.LedgerError):
        store.void('fills', 'f2', '')
    with pytest.raises(M.LedgerError):
        store.void('fills', 'nope', 'x')


def test_settlements_import_and_report(store, tmp_path):
    importers.import_file(store, write(tmp_path, 'f.csv', FILLS_CSV.replace('sell', 'buy', 1).split('\n')[0] + '\nf1,KXTEST-1,yes,buy,10,0.40,0.20,1792600000,o1\n'))
    s = ('ticker,market_result,settled_ts,revenue,fee,yes_count,no_count\n'
         'KXTEST-1,yes,1792700000,10.00,0,10,0\n')
    r = importers.import_file(store, write(tmp_path, 's.csv', s))
    assert r.kind == 'settlements' and r.n_new == 1
    rep = E.compute(store.fills(), store.settlements())
    assert rep.markets['KXTEST-1'].realized == D('5.80') and rep.markets['KXTEST-1'].status == 'settled'


# ---------------------------------------------------------------- isolation / guards
def test_store_refuses_evidence_locations_and_evidence_databases(tmp_path):
    from kh.ledger import store as st
    with pytest.raises(StoreError):
        AccountStore(st.PROJECT_ROOT / 'data' / 'account.db')
    with pytest.raises(StoreError):
        AccountStore(st.PROJECT_ROOT / 'research' / 'x.db')
    with pytest.raises(StoreError):
        AccountStore(tmp_path / 'kalshi_copy.db')
    ev = tmp_path / 'looks_innocent.db'
    c = sqlite3.connect(ev)
    c.execute('CREATE TABLE hash_chain(seq INTEGER)')
    c.commit(); c.close()
    with pytest.raises(StoreError):
        AccountStore(ev)
    beside = tmp_path / 'ev'
    beside.mkdir()
    (beside / 'kalshi.db').write_bytes(b'')
    with pytest.raises(StoreError):
        AccountStore(beside / 'account.db')


def test_ledger_package_has_no_network_or_trading_capability():
    import pathlib, re
    root = pathlib.Path(__file__).resolve().parents[1]
    banned = re.compile(r'^\s*(import|from)\s+(requests|urllib|http|socket|ssl|aiohttp|httpx|websocket)', re.M)
    for f in (root / 'kh/ledger').glob('*.py'):
        assert not banned.search(f.read_text()), f
        text = f.read_text().lower()
        for word in ('create_order', 'place_order', 'cancel_order', '/portfolio/orders'):
            assert word not in text, (f, word)


# ---------------------------------------------------------------- journal
def test_journal_revisions_search_and_soft_delete(store):
    i = store.journal_add(title='Senate thesis', body='Models disagree', ticker='CONTROLS-2026-D', entry_type='pre_trade',
                          planned_side='no', planned_price='0.36', my_prob='0.55', tags='politics')
    store.journal_add(title='Process note', body='size small')
    store.journal_revise(i, title='Senate thesis v2', body='Models disagree; wait', tags='politics', my_prob='0.52')
    cur = store.journal(ticker='CONTROLS-2026-D', include_history=True)
    assert len(cur) == 1 and cur[0]['title'] == 'Senate thesis v2' and cur[0]['revisions'] == 2
    assert cur[0]['history'][0]['title'] == 'Senate thesis'       # the original wording is preserved
    assert [j['title'] for j in store.journal(query='SIZE small')] == ['Process note']
    store.journal_revise(i, title='x', deleted=True)
    assert [j['title'] for j in store.journal()] == ['Process note']
    assert len(store.journal(include_deleted=True)) == 2


@pytest.mark.parametrize('kw', [dict(title=''), dict(title='x', entry_type='bogus'), dict(title='x', my_prob='1.5'),
                                dict(title='x', planned_price='1.5'), dict(title='x', planned_side='maybe'), dict(title='x', ticker='bad ticker')])
def test_journal_validation(store, kw):
    with pytest.raises(M.LedgerError):
        store.journal_add(**kw)


# ---------------------------------------------------------------- sample dataset & comparison
@pytest.fixture
def sample_report(tmp_path):
    s = sample.build_sample_store(tmp_path / 'sample.db')
    rep = E.compute(s.fills(), s.settlements(), s.cash())
    yield s, rep
    s.close()


def test_sample_dataset_known_results(sample_report):
    s, rep = sample_report
    m = rep.markets
    assert m['SAMPLE-WIN-1'].realized == D('11.17')
    assert m['SAMPLE-LOSS-1'].realized == D('-6.17')
    assert m['SAMPLE-SCALP-1'].realized == D('1.48')
    assert m['SAMPLE-PARTIAL-1'].realized == D('0.5375') and m['SAMPLE-PARTIAL-1'].qty == 25
    assert m['SAMPLE-NET-1'].realized == D('0.16')
    assert m['SAMPLE-INCOMPLETE-1'].realized is None and m['SAMPLE-MISMATCH-1'].realized is None
    assert rep.n_incomplete == 2
    verified = D('11.17') - D('6.17') + D('1.48') + D('0.5375') + D('0.16') + 0   # open CONTROLS/KXAPR realized parts are 0
    assert rep.realized_total == verified
    assert rep.unrealized_total is None                       # no fresh executable quote exists offline
    assert rep.cash_net == D('500.00')


def test_comparison_keeps_actual_and_paper_separate(sample_report):
    s, rep = sample_report
    forecasts = [dict(id=1, ticker='CONTROLS-2026-D', cohort='research', cohort_label='Track A', side='no', prob_yes=0.59, ts=1792600000.0, exec_price=0.35),
                 dict(id=3, ticker='KXAPRPOTUS-26OCT23-38.5', cohort='research', cohort_label='Track A', side='no', prob_yes=0.15, ts=1792600000.0, exec_price=0.75),
                 dict(id=9, ticker='KXOTHER-1', cohort='strategy', cohort_label='Track B', side='no', prob_yes=0.05, ts=1792600000.0, exec_price=0.95)]
    rows = {r['ticker']: r for r in compare(rep, forecasts, s.journal())}
    assert rows['CONTROLS-2026-D']['research'][0]['relation'] == 'same_side'
    assert rows['KXAPRPOTUS-26OCT23-38.5']['research'][0]['relation'] == 'opposite_side'
    assert rows['KXOTHER-1']['research'][0]['relation'] == 'research_only' and not rows['KXOTHER-1']['traded']
    assert rows['CONTROLS-2026-D']['journal_estimates'][0]['my_prob'] == '0.55'
    assert 'SAMPLE-WIN-1' not in rows                           # user-only market with no research or journal
    assert 'paper_pnl_text' in rows['CONTROLS-2026-D']['research'][0] and 'actual_realized' in rows['CONTROLS-2026-D']
