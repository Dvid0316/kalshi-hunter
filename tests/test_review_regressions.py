"""Regression tests for every defect confirmed by the independent adversarial reviews.

Reviewers: (1) P&L engine math (review interrupted by a provider credit failure; its result files in
~/.hermes/cache/scratch/review/ledger/ are the evidence), (2) data handling / honest labelling (completed,
verdict: 6 defects, none critical). Each test names the finding it pins.
"""
from __future__ import annotations

import hashlib
from decimal import Decimal as D
from pathlib import Path

import pytest

from desktop import formatting as FMT
from desktop import paths
from desktop.account_service import AccountService
from desktop.repository import Repository, PAGE_SIZE, _card_pnl
from kh.ledger import engine as E
from kh.ledger import models as M
from kh.ledger.store import AccountStore

ROOT = Path(__file__).resolve().parents[1]
D0 = D('0')


def F(i, side, action, count, price, fee='0', ts=None, ticker='T1'):
    ts = ts if ts is not None else i
    return M.Fill(str(i), ticker, side, action, D(count), D(price), D(fee), float(ts), seq=i)


def S(ticker='T1', result='yes', revenue='0', fee='0', ts=1000, yes=None, no=None, i='s1', yc=None, nc=None):
    return M.Settlement(i, ticker, result, float(ts), D(revenue), D(fee),
                        None if yes is None else D(str(yes)), None if no is None else D(str(no)),
                        None if yc is None else D(str(yc)), None if nc is None else D(str(nc)))


@pytest.fixture(scope='module')
def repo(tmp_path_factory):
    r = Repository(cache=tmp_path_factory.mktemp('cache') / 'idx.db')
    r.ensure_index()
    return r


@pytest.fixture()
def var(tmp_path, monkeypatch):
    monkeypatch.setenv('KH_VAR_DIR', str(tmp_path))
    return tmp_path


@pytest.fixture()
def svc(repo, var):
    return AccountService(repo, db_path=var / 'account.db')


# ================================================================ engine: settlement money
def test_control_a_consistent_settlement_stays_verified_and_shows_pnl():
    """Guard against over-triggering the new integrity rules."""
    m = E.compute([F(1, 'yes', 'buy', 10, '0.50', '0.10')], [S(result='yes', revenue='10.00')]).markets['T1']
    assert not m.incomplete and m.realized == D('4.90') and m.flags == []


def test_void_settlement_with_no_refund_is_incomplete_not_a_confident_loss():
    """Review 1 S9b: a void that paid nothing while contracts were held is an inconsistent record, not a total loss."""
    m = E.compute([F(1, 'yes', 'buy', 10, '0.40', '0.10')], [S(result='void', revenue='0')]).markets['T1']
    assert m.incomplete and m.realized is None
    assert 'void_settlement_without_refund' in {f.code for f in m.flags}
    assert {f.severity for f in m.flags if f.code == 'void_settlement_without_refund'} == {'error'}


@pytest.mark.parametrize('settle,fills', [
    (S(result='scalar', revenue='100'), [F(1, 'yes', 'buy', 10, '0.40', '0')]),          # S9d: money from nothing
    (S(result='void', revenue='100'), [F(1, 'yes', 'buy', 10, '0.40'), F(2, 'yes', 'sell', 10, '0.40')]),  # S9c: no position
])
def test_settlement_paying_more_than_the_position_can_pay_is_incomplete(settle, fills):
    m = E.compute(fills, [settle]).markets['T1']
    assert m.incomplete and m.realized is None, 'a payout beyond 10 x $1 must never be shown as profit'


def test_every_settlement_fee_is_counted_even_when_settlements_conflict():
    """Review 1 S10: two settlement records, fees 0.03 and 0.05 plus the fill fee 0.10 = 0.18."""
    m = E.compute([F(1, 'yes', 'buy', 10, '0.50', '0.10')],
                  [S(i='a', result='yes', revenue='10', fee='0.03', ts=900),
                   S(i='b', result='yes', revenue='10', fee='0.05', ts=950)]).markets['T1']
    assert m.fees == D('0.18') and m.incomplete


def test_settlement_dated_before_its_fills_is_incomplete():
    """Review 1 S12c: a fill dated after settlement means the timestamps or the position are wrong."""
    m = E.compute([F(1, 'yes', 'buy', 5, '0.40', ts=2000)], [S(result='yes', revenue='5', ts=1000)]).markets['T1']
    assert m.incomplete and m.realized is None
    assert 'fill_after_settlement' in {f.code for f in m.flags}


def test_recorded_cost_that_disagrees_with_the_fills_is_flagged():
    """Review 1 RP: the settlement's recorded cost is cross-checked against the fills."""
    m = E.compute([F(1, 'yes', 'buy', 10, '0.40', '0.10')],
                  [S(result='yes', revenue='10', yc='3.00', nc='0')]).markets['T1']
    assert 'recorded_cost_mismatch' in {f.code for f in m.flags}
    clean = E.compute([F(1, 'yes', 'buy', 10, '0.40', '0.10')],
                      [S(result='yes', revenue='10', yc='4.00', nc='0')]).markets['T1']
    assert 'recorded_cost_mismatch' not in {f.code for f in clean.flags}


def test_revenue_that_disagrees_with_the_fills_never_becomes_a_headline_number():
    """Review 1 S11/S11b: cents typed as dollars previously printed +$995.90 as a confident total."""
    r = E.compute([F(1, 'yes', 'buy', 10, '0.40', '0.10')], [S(result='yes', revenue='1000')])
    assert r.markets['T1'].incomplete and r.realized_total is None


def test_marks_are_validated_never_crashed_and_never_float_noise():
    """Review 1 mark findings: crossed quotes, float types and binary-float Decimals must all be rejected."""
    good = E.compute([F(1, 'yes', 'buy', 10, '0.40')], marks={'T1': E.Mark(10.0, D('0.55'), D('0.60'))}, now=10.0).markets['T1']
    assert good.unrealized == D('1.50') and good.unrealized_reason == ''
    crossed = E.compute([F(1, 'yes', 'buy', 10, '0.40')], marks={'T1': E.Mark(10.0, D('0.60'), D('0.50'))}, now=10.0).markets['T1']
    assert crossed.unrealized is None and crossed.unrealized_reason == 'Crossed quote'
    flo = E.compute([F(1, 'yes', 'buy', 10, '0.40')], marks={'T1': E.Mark(10.0, 0.6, D('0.65'))}, now=10.0).markets['T1']
    assert flo.unrealized is None and 'Decimal' in flo.unrealized_reason
    artifact = E.compute([F(1, 'yes', 'buy', 10, '0.40')], marks={'T1': E.Mark(10.0, D(0.6), D('0.65'))}, now=10.0).markets['T1']
    assert artifact.unrealized is None and 'float' in artifact.unrealized_reason, \
        'Decimal(0.6) is a binary artifact and produced 1.99999999999999977 before this guard'


# ================================================================ records: duplicates and units
def test_economically_identical_records_are_duplicates_not_conflicts(tmp_path):
    """Review 1 S28: '0.40' vs '0.4', '10' vs '10.0' and '0' vs '0.00' are the same trade."""
    s = AccountStore(tmp_path / 'a.db')
    try:
        first = M.make_fill(dict(fill_id='F1', ticker='KXA', side='yes', action='buy', count='10', price='0.40', fee='0', ts='1792600000'))
        same = M.make_fill(dict(fill_id='F1', ticker='KXA', side='yes', action='buy', count='10.0', price='0.4', fee='0.00', ts='1792600000'))
        s.add_fills([first])
        again = s.add_fills([same])
        assert (again.n_new, again.n_dup, again.n_conflict) == (0, 1, 0)
        n1 = M.make_fill(dict(ticker='KXB', side='yes', action='buy', count='5', price='0.30', fee='0', ts='1792600100'))
        n2 = M.make_fill(dict(ticker='KXB', side='yes', action='buy', count='5.0', price='0.30', fee='0.0', ts='1792600100'))
        s.add_fills([n1])
        s.add_fills([n2])
        assert len([f for f in s.fills() if f.ticker == 'KXB']) == 1, 're-importing the same file must not double the position'
    finally:
        s.close()


def test_two_genuine_identical_manual_entries_are_both_recorded(svc):
    """Review 1 SVC E: two real fills with identical details in the same minute were collapsed into one."""
    svc.record_fill('KXREC-9', 'yes', 'buy', 1, '50', '0', '2026-10-01 10:00')
    svc.record_fill('KXREC-9', 'yes', 'buy', 1, '50', '0', '2026-10-01 10:00')
    rows = svc.positions()['rows']
    assert len(rows) == 1 and rows[0]['qty'] == '2', 'both executions really happened'


def test_ticker_case_is_normalised_to_one_market():
    """Review 1 TICK: 'kxabc' and 'KXABC' are the same market."""
    m = E.compute([F(1, 'yes', 'buy', 5, '0.40', ticker='kxabc'), F(2, 'yes', 'buy', 5, '0.40', ticker='KXABC')])
    assert list(m.markets) == ['KXABC'] and m.markets['KXABC'].qty == D(10)
    via_boundary = E.compute([M.make_fill(dict(ticker='kxabc', side='yes', action='buy', count='5', price='0.40', ts='1792600000')),
                               M.make_fill(dict(ticker='KXABC', side='yes', action='buy', count='5', price='0.40', ts='1792600100'))])
    assert list(via_boundary.markets) == ['KXABC'] and via_boundary.markets['KXABC'].qty == D(10)
    assert M.make_fill(dict(ticker='kxabc', side='yes', action='buy', count='1', price='0.4', ts='1792600000')).ticker == 'KXABC'


def test_decimal_comma_is_rejected_and_us_thousands_still_works():
    """Review 1 S26: '0,07' was silently read as 7. US grouping like $1,250.50 stays supported."""
    for bad in ('0,07', '1,5', '2,50', '10,0000'):
        with pytest.raises(M.LedgerError, match='comma'):
            M.dec(bad)
    assert M.dec('$1,250.50') == D('1250.50') and M.dec('1,234,567') == D('1234567')


def test_out_of_range_timestamps_are_rejected_and_formatting_never_crashes_on_them():
    """Review 1 S27: a millisecond epoch was accepted and then crashed the Positions page."""
    assert M.timestamp('1792600000') == 1792600000.0
    assert M.timestamp('2026-10-01 10:00') == pytest.approx(1790866800.0, abs=1.0)
    for bad in ('1760000000000', '99999999999', '1000'):
        with pytest.raises(M.LedgerError):
            M.timestamp(bad)
    assert FMT.stamp(10 ** 13) == 'Unavailable' and FMT.short_stamp(10 ** 13) == '—'


def test_absurd_amounts_degrade_to_unavailable_instead_of_crashing_a_page():
    """Review 1 FMT: money(Decimal('1E+30')) raised InvalidOperation and blanked the view."""
    out = FMT.money(D('1E+30'))
    assert out.startswith('$') and ',' in out, 'a stored value is shown as stored; it must not crash the page'
    assert FMT.count(D('2.5')) == '2.5', 'a fractional contract count must not be truncated to 2'


def test_json_with_native_floats_imports_as_exact_decimals(tmp_path, svc):
    """Review 1 S25j: JSON 0.4 is exact decimal text; rejecting it made JSON exports unusable."""
    f = tmp_path / 'fills.json'
    f.write_text('[{"ticker": "KXJ-1", "side": "yes", "action": "buy", "count": 2, "price": 0.4, "fee": 0.1, "ts": "2026-10-01 10:00"},'
                 ' {"ticker": "KXJ-1", "side": "yes", "action": "buy", "count": 1, "price": 0.35, "fee": 0.02, "ts": "2026-10-01 10:05"}]')
    r = svc.import_file(f)
    assert (r['new'], r['rejected']) == (2, 0)
    assert svc.positions()['rows'][0]['cost_basis'] == '$1.27'      # 2x0.40 + 0.10 fee + 1x0.35 + 0.02 fee


# ================================================================ account service: honesty
def test_voided_fill_stays_visible_in_history_without_counting(svc):
    """Review 1 VOID: a voided fill vanished from the transaction history entirely."""
    svc.record_fill('KXV-1', 'yes', 'buy', 2, '50', '0.02')
    store = svc._open()
    try:
        fid = store.fills()[0].fill_id
    finally:
        store.close()
    svc.void_record('fills', fid, 'entered twice')
    assert svc.positions()['rows'] == []
    row = next(r for r in svc.history('transactions')['rows'] if r['ref'] == fid)
    assert row['type'] == 'Fill (voided)' and row['cash'] == '—' and row['description'].startswith('VOIDED')
    assert svc.status()['counts']['voids'] == 1


def test_summary_never_claims_verified_while_records_are_quarantined_or_flagged(svc, var):
    """Review 1 SVC B/C/D: the headline said 'All markets verified' with conflicts, rejects and broken records."""
    clean = var / 'clean.csv'
    clean.write_text('ticker,side,action,count,price,fee,ts\nKXC-1,yes,buy,10,0.40,0.10,2026-10-01 10:00\n')
    svc.import_file(clean)
    settled = var / 's.csv'
    settled.write_text('ticker,market_result,settled_ts,revenue\nKXC-1,yes,2026-10-02 10:00,10.00\n')
    svc.import_file(settled)
    assert svc.positions()['summary']['realized_note'] == 'All markets verified', 'control: a clean ledger still says so'
    first = var / 'h1.csv'
    first.write_text('fill_id,ticker,side,action,count,price,fee,ts\nH1,KXC-1,yes,buy,10,0.40,0.10,2026-10-01 10:00\n')
    svc.import_file(first)
    clash = var / 'h2.csv'
    clash.write_text('fill_id,ticker,side,action,count,price,fee,ts\nH1,KXC-1,yes,buy,10,0.45,0.10,2026-10-01 10:00\nB2,,yes,buy,1,0.40,0,2026-10-01 10:05\n')
    out = svc.import_file(clash)
    assert (out['conflict'], out['rejected']) == (1, 1), out['summary']
    note = svc.positions()['summary']['realized_note']
    assert 'All markets verified' not in note and 'quarantined' in note, note


def test_millisecond_timestamps_in_a_file_are_rejected_row_by_row_not_swallowed(svc, var):
    f = var / 'ms.csv'
    f.write_text('ticker,side,action,count,price,fee,ts\nKXM-1,yes,buy,1,0.40,0,1760000000000\n')
    out = svc.import_file(f)
    assert out['new'] == 0 and out['rejected'] == 1 and 'milliseconds' in out['rejects'][0]['reason']


def test_sub_cent_prices_are_flagged_as_a_possible_unit_mistake(svc, var):
    """Review 1 SVC G: a dollars file imported as cents was accepted silently at 0.004."""
    f = var / 'dollars.csv'
    f.write_text('ticker,side,action,count,price,fee,ts\nKXU-1,yes,buy,10,0.004,0,2026-10-01 10:00\n')
    assert svc.import_file(f)['new'] == 1
    note = svc.positions()['summary']['realized_note']
    assert 'below 1¢' in note, note
    assert any('below 1¢' in i['message'] for i in svc.data_quality()['items'])


def test_a_market_traded_on_both_sides_does_not_blend_entry_averages(svc):
    """Review 1 SVC A: YES bought at 40c and NO bought at 55c were averaged into a meaningless 45c."""
    svc.record_fill('KXBOTH-1', 'yes', 'buy', 10, '40', '0', '2026-10-01 10:00')
    svc.record_fill('KXBOTH-1', 'no', 'buy', 15, '55', '0', '2026-10-01 11:00')
    svc.record_fill('KXBOTH-1', 'no', 'sell', 5, '50', '0', '2026-10-01 12:00')
    closed = next(r for r in svc.positions('closed')['rows'] if r['ticker'] == 'KXBOTH-1')
    assert closed['avg_entry'] == '—' and closed['avg_exit'] == '—', 'one average would blend two different prices'
    assert any('both YES and NO' in f for f in closed['flags'])
    assert closed['realized'] != 'Unavailable', 'the realized result itself is still known and shown'
    # a flipped market that is still open keeps the held leg's own honest entry price
    svc.record_fill('KBOTH-2', 'yes', 'buy', 10, '40', '0', '2026-10-01 10:00')
    svc.record_fill('KBOTH-2', 'no', 'buy', 12, '55', '0', '2026-10-01 11:00')
    open_row = next(r for r in svc.positions()['rows'] if r['ticker'] == 'KBOTH-2')
    assert open_row['side'] == 'NO' and open_row['avg_entry'] == '55.0¢'


# ================================================================ repository: data handling
def test_offset_is_clamped_to_the_last_page_and_never_crashes(repo):
    """Review 2 D4/D5: offset 2**63 raised OverflowError; a page past the end claimed 'no markets match'."""
    m = repo.markets('', 10 ** 6, scope='all')
    assert m['total'] == 167233 and len(m['rows']) == 167233 - 167200 and m['more'] is False
    assert m['offset'] == 167200 and m['page'] == 3345
    for bad in (float('nan'), None, 'abc'):
        m = repo.markets('', bad, scope='all')
        assert m['offset'] == 0 and len(m['rows']) == PAGE_SIZE, bad
    huge = repo.markets('', 2 ** 63, scope='all')            # OverflowError before; now clamped, not crashed
    assert huge['offset'] == 167200 and len(huge['rows']) > 0


def test_search_input_is_bounded_and_never_starves_the_worker_pool(repo):
    """Review 2 D4: a 60,000-character term raised 'pattern too complex'; 9,000 terms took minutes."""
    m = repo.markets('z' * 60000, 0, scope='all')
    assert m['rows'] == [] and m['total'] == 0
    m = repo.markets(' '.join(['a'] * 9000), 0, scope='all')
    assert m['total'] > 1000, 'the term cap keeps this a fast query, not a minute-long LIKE storm'


def test_spread_sort_breaks_ties_by_ticker_not_by_float_noise(repo):
    """Review 2 D3: equal displayed spreads appeared out of ticker order (float noise in the ORDER BY)."""
    pairs = violations = 0
    for offset in range(0, 1000, PAGE_SIZE):
        rows = repo.markets('', offset, scope='all', sort='spread', desc=False)['rows']
        for a, b in zip(rows, rows[1:]):
            if a['spread'] == b['spread']:
                pairs += 1
                violations += b['ticker'] < a['ticker']
    assert pairs > 100 and violations == 0, f'{violations} out-of-order pairs among {pairs}'


def test_forecast_card_pnl_matches_the_overview_reconciliation_rule():
    """Review 2 D2: a card showed the stored P&L ($999.00) even when it failed reconciliation (Overview said 'Mismatch')."""
    row = dict(outcome=1, side='yes', qty=D('10'), exec_price=D('0.40'), fee=D('0.01'), pnl=D('999.00'))
    assert _card_pnl(row) == 'Mismatch'
    row['pnl'] = D('5.99')
    assert _card_pnl(row) == '$5.99'
    row['outcome'] = None
    assert _card_pnl(row) == 'Unavailable'
    broken = dict(outcome=1, side='yes', qty=D('10'), exec_price=D('0.40'), fee=D('0.01'), pnl=None)
    assert _card_pnl(broken) == 'Mismatch'


def test_demo_forecasts_are_labelled_wherever_they_appear(repo):
    """Review 2 risk: forecasts 1-3 carry note='demo' and sat among real research with no marker."""
    cards = {c['ticker']: c for c in repo.forecast_cards('research')}
    demo = [c for c in cards.values() if c['note'] == 'demo']
    assert demo and all(c['status'].endswith('· demo run') for c in demo)
    real = [c for c in repo.forecast_cards('strategy')]
    assert real and not any('demo run' in c['status'] for c in real)


def test_quote_card_never_calls_archived_quotes_executable():
    """Review 2 D1: the heading said 'Executable quotes' above quotes the data layer marks non-executable."""
    text = (ROOT / 'desktop/qml/components/QuoteCard.qml').read_text()
    line = next(x for x in text.splitlines() if 'Executable quotes' in x)
    assert '.executable ?' in line, 'the claim must be conditional on the quote actually being executable'
    assert 'Archived quotes · not executable' in text


def test_index_cache_name_is_stable_across_processes():
    """Review 2 risk: Python's salted hash() renamed the per-snapshot cache on every launch (a ~90 MB leak)."""
    other = Path('/tmp/not-the-default-snapshot.db')
    r = Repository(path=other)
    r.ensure_index()                                    # switches to the per-snapshot name before building
    expected = hashlib.sha1(str(other.resolve()).encode()).hexdigest()[:10]
    assert r.cache.name == f'market_index_{expected}.db'
    again = Repository(path=other)
    again.ensure_index()
    assert again.cache == r.cache, 'the name must be identical in a later process, not salted'
    assert r.cache.name != Repository().cache.name, 'a different snapshot must never share the default cache'
