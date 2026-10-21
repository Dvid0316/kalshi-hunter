"""Service-level tests for the personal ledger: what the user would actually see after importing or recording trades.

Every test uses its own temporary KH_VAR_DIR, so none of them can touch a real account database.
"""
from __future__ import annotations

import hashlib
import socket
from decimal import Decimal
from pathlib import Path

import pytest

from desktop import paths
from desktop.account_service import AccountService
from desktop.repository import Repository
from kh.ledger import models as M

ROOT = Path(__file__).resolve().parents[1]
D = Decimal


@pytest.fixture(scope='module')
def repo():
    return Repository()


@pytest.fixture()
def var(tmp_path, monkeypatch):
    monkeypatch.setenv('KH_VAR_DIR', str(tmp_path))
    return tmp_path


@pytest.fixture()
def svc(repo, var):
    return AccountService(repo, db_path=var / 'account.db')


def write(var, name, text):
    p = var / name
    p.write_text(text)
    return p


FILLS = ("fill_id,ticker,side,action,count,price,fee,ts\n"
         "F1,KXTEST-1,yes,buy,10,0.40,0.20,2026-10-01 10:00\n"
         "F2,KXTEST-1,yes,buy,abc,0.40,0.20,2026-10-01 10:05\n"          # bad count
         "F3,,yes,buy,1,0.40,0,2026-10-01 10:06\n"                        # missing ticker
         "F4,KXTEST-2,yes,sell,5,0.50,0.10,2026-10-02 10:00\n")           # sells something never bought


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------------ empty / unavailable
def test_empty_account_says_unavailable_never_zero(svc):
    st = svc.status()
    assert st['has_data'] is False and st['authorization']['api_access'] is False
    s = svc.positions()['summary']
    for key in ('realized', 'fees', 'open_cost', 'unrealized', 'net_deposits', 'equity'):
        assert s[key] == 'Unavailable', key
    assert svc.history('transactions')['empty'] is True
    assert svc.data_quality()['empty'] is True
    assert not (svc.path).exists(), 'merely looking must not create the account database'


# ------------------------------------------------------------------ import behaviour
def test_import_accepts_good_rows_and_rejects_bad_ones_with_reasons(svc, var):
    r = svc.import_file(write(var, 'fills.csv', FILLS))
    assert (r['new'], r['rejected'], r['dup'], r['conflict']) == (2, 2, 0, 0)
    reasons = ' | '.join(x['reason'] for x in r['rejects'])
    assert 'count' in reasons and 'ticker' in reasons


def test_import_is_idempotent(svc, var):
    f = write(var, 'fills.csv', FILLS)
    svc.import_file(f)
    again = svc.import_file(f)
    assert (again['new'], again['dup']) == (0, 2)
    assert svc.history('transactions')['total'] == 2, 'a re-import must not double-count anything'


def test_conflicting_duplicate_keeps_original_and_is_flagged(svc, var):
    svc.import_file(write(var, 'fills.csv', FILLS))
    changed = write(var, 'fills2.csv', "fill_id,ticker,side,action,count,price,fee,ts\nF1,KXTEST-1,yes,buy,10,0.45,0.20,2026-10-01 10:00\n")
    r = svc.import_file(changed)
    assert r['conflict'] == 1 and r['new'] == 0
    row = next(p for p in svc.positions()['rows'] if p['ticker'] == 'KXTEST-1')
    assert row['avg_entry'] == '42.0¢', 'cost basis must still reflect the ORIGINAL 40¢ fill + fees'
    dq = svc.data_quality()
    assert dq['ok'] is False and any('Conflicting duplicate' in i['message'] for i in dq['items'])


def test_oversell_is_incomplete_and_has_no_pnl(svc, var):
    svc.import_file(write(var, 'fills.csv', FILLS))
    closed = {p['ticker']: p for p in svc.positions('closed')['rows']}
    bad = closed['KXTEST-2']
    assert bad['incomplete'] is True and bad['realized'] == 'Unavailable'
    assert any('no matching position' in f for f in bad['flags'])
    assert svc.positions()['summary']['incomplete'] == 1


def test_settlement_record_is_the_authoritative_realized_result(svc, var):
    svc.import_file(write(var, 'fills.csv', FILLS))
    svc.import_file(write(var, 's.csv', "settlement_id,ticker,market_result,settled_ts,revenue,fee\nS1,KXTEST-1,yes,2026-10-05 12:00,10.00,0\n"))
    row = next(p for p in svc.positions('closed')['rows'] if p['ticker'] == 'KXTEST-1')
    # 10 contracts bought at $0.40, paid out $1.00 each, $0.20 fee:  10 x 0.60 - 0.20 = 5.80
    assert row['realized'] == '+$5.80' and row['outcome'] == 'WON'
    assert svc.positions()['summary']['realized'] == '+$5.80'


def test_losing_settlement_is_a_loss_including_fees(svc, var):
    svc.import_file(write(var, 'f.csv', "ticker,side,action,count,price,fee,ts\nKXL-1,yes,buy,5,0.30,0.10,2026-10-01 10:00\n"))
    svc.import_file(write(var, 's.csv', "ticker,market_result,settled_ts,revenue\nKXL-1,no,2026-10-02 10:00,0\n"))
    row = svc.positions('closed')['rows'][0]
    assert row['realized'] == '-$1.60' and row['outcome'] == 'LOST'            # -(5 x 0.30) - 0.10


def test_unrealized_is_never_computed_from_archived_quotes(svc, var):
    svc.import_file(write(var, 'f.csv', "ticker,side,action,count,price,fee,ts\nCONTROLS-2026-D,yes,buy,5,0.30,0.10,2026-10-01 10:00\n"))
    s = svc.positions()['summary']
    assert s['unrealized'] == 'Unavailable'
    row = svc.positions()['rows'][0]
    assert row['unrealized'] == 'Unavailable', 'the archived CONTROLS quote must not be used to mark this position'


def test_cash_movements_are_never_counted_as_profit(svc, var):
    svc.import_file(write(var, 'c.csv', "ts,kind,amount\n2026-10-01 09:00,deposit,500.00\n2026-10-03 09:00,withdrawal,-120.50\n"))
    s = svc.positions()['summary']
    assert s['net_deposits'] == '+$379.50'
    assert s['realized'] in ('Unavailable', '$0.00'), 'deposits must not leak into realized P&L'


# ------------------------------------------------------------------ manual recording
def test_record_fill_creates_a_position_and_never_orders(svc, monkeypatch):
    def deny(*a, **k):
        raise AssertionError('network access is forbidden')
    monkeypatch.setattr(socket.socket, 'connect', deny)
    svc.record_fill('KXREC-1', 'no', 'buy', 3, '35', '0.05')
    row = svc.positions()['rows'][0]
    assert (row['ticker'], row['side'], row['qty']) == ('KXREC-1', 'NO', '3')
    assert row['cost_basis'] == '$1.10'                                       # 3 x 0.35 + 0.05


@pytest.mark.parametrize('bad', [dict(price_cents=40.5), dict(price_cents='abc'), dict(price_cents='150'), dict(count=0), dict(count=2.5), dict(side='maybe'), dict(ticker='')])
def test_record_fill_rejects_invalid_input(svc, bad):
    args = dict(ticker='KXREC-2', side='yes', action='buy', count=1, price_cents='40', fee='0')
    args.update(bad)
    with pytest.raises(M.LedgerError):
        svc.record_fill(args['ticker'], args['side'], args['action'], args['count'], args['price_cents'], args['fee'])
    assert svc.status()['has_data'] is False, 'a rejected record must leave no trace'


def test_voiding_a_record_removes_it_from_results_but_not_from_history(svc):
    svc.record_fill('KXV-1', 'yes', 'buy', 2, '50', '0')
    store = svc._open()
    try:
        fid = store.fills()[0].fill_id
    finally:
        store.close()
    svc.void_record('fills', fid, 'entered by mistake')
    assert svc.positions()['rows'] == []
    store = svc._open()
    try:
        assert store.fills() == []
        assert [f.fill_id for f in store.fills(include_voided=True)] == [fid], 'voiding adds a new fact; the original row is kept'
    finally:
        store.close()
    with pytest.raises(M.LedgerError):
        svc.void_record('fills', fid, '   ')                                   # a reason is mandatory


# ------------------------------------------------------------------ safety / isolation
def test_account_db_refuses_to_live_inside_evidence(repo, var):
    for target in (ROOT / 'data' / 'account.db', ROOT / 'research' / 'account.db', ROOT / 'strategies' / 'x.db', ROOT / 'data' / 'kalshi.db'):
        with pytest.raises(paths.EvidenceWriteError):
            AccountService(repo, db_path=target)._writer()
    assert not (ROOT / 'data' / 'account.db').exists()


def test_sample_data_never_touches_the_real_account_db(repo, var):
    s = AccountService(repo, sample=True)
    s.prepare()
    assert s.status()['sample'] is True and s.status()['has_data'] is True
    assert (var / 'sample' / 'account.db').exists()
    assert not (var / 'account.db').exists(), 'sample mode must not create or modify the real ledger'


def test_corrupt_ledger_is_reported_clearly_and_left_untouched(svc, var):
    bad = var / 'account.db'
    bad.write_bytes(b'this is not sqlite')
    before = sha(bad)
    for call in (svc.status, svc.positions, svc.data_quality, svc.journal):
        with pytest.raises(M.LedgerError) as e:
            call()
        assert 'not modified' in str(e.value) and 'backup' in str(e.value)
    with pytest.raises(M.LedgerError):
        svc.record_fill('KXC-1', 'yes', 'buy', 1, '50', '0')
    with pytest.raises(M.LedgerError):
        svc.import_file(write(var, 'f.csv', FILLS))
    assert sha(bad) == before, 'a damaged ledger must never be overwritten or "repaired" silently'
    assert sorted(p.name for p in var.glob('account.db*')) == ['account.db']


def test_import_makes_no_network_connection(svc, var, monkeypatch):
    def deny(*a, **k):
        raise AssertionError('network access is forbidden')
    monkeypatch.setattr(socket.socket, 'connect', deny)
    monkeypatch.setattr(socket, 'create_connection', deny)
    svc.import_file(write(var, 'fills.csv', FILLS))
    svc.positions(); svc.history('settlements'); svc.data_quality(); svc.comparison()


def test_oversize_and_unrecognised_files_fail_safely(svc, var):
    with pytest.raises(M.LedgerError):
        svc.import_file(write(var, 'x.csv', "foo,bar\n1,2\n"))
    with pytest.raises(M.LedgerError):
        svc.import_file(var / 'missing.csv')
    assert svc.status()['has_data'] is False


# ------------------------------------------------------------------ journal + comparison
def test_journal_revisions_keep_history_and_delete_only_hides(svc):
    out = svc.journal_save(0, 'Senate view', 'first thought', 'CONTROLS-2026-D', 'pre_trade', 'senate', 'no', '36', '55')
    jid = out['id']
    svc.journal_save(jid, 'Senate view', 'changed my mind', 'CONTROLS-2026-D', 'pre_trade', 'senate', 'yes', '40', '60')
    e = next(x for x in svc.journal()['entries'] if x['id'] == jid)
    assert e['body'] == 'changed my mind' and e['edited'] is True and e['revisions'] == 2
    assert 'Grok recorded' in e['research_note'], 'journal entries link to recorded research for the same ticker'
    store = svc._open()
    try:
        entry = next(x for x in store.journal(include_history=True) if x['id'] == jid)
        bodies = [r['body'] for r in entry['history']]
    finally:
        store.close()
    assert bodies == ['first thought', 'changed my mind']
    svc.journal_delete(jid)
    assert all(x['id'] != jid for x in svc.journal()['entries'])


def test_comparison_is_descriptive_and_never_adds_paper_to_actual(repo, var):
    s = AccountService(repo, sample=True)
    s.prepare()
    c = s.comparison()
    assert 'never added together' in c['note']
    by = {r['ticker']: r for r in c['rows']}
    assert by['CONTROLS-2026-D']['relation_code'] == 'same_side'
    assert by['KXAPRPOTUS-26OCT23-38.5']['relation_code'] == 'opposite_side'
    assert by['CONTROLH-2026-D']['relation_code'] == 'research_only' and by['CONTROLH-2026-D']['my_actual'] == '—'
    assert all(r['paper_status'].endswith('paper') for r in c['rows']), 'paper results are always labelled as paper'
