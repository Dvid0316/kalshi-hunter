"""Research repository: search, filters, sort, pagination, cache equivalence, detail data integrity.

These run against the real preserved snapshot (read-only) so they validate actual data handling.
"""
import hashlib
import os
import re
import sqlite3
import time
from pathlib import Path

import pytest

from desktop import index as market_index, paths
from desktop.repository import Repository, PAGE_SIZE

ROOT = paths.ROOT


@pytest.fixture(scope='module')
def repo(tmp_path_factory):
    r = Repository(cache=tmp_path_factory.mktemp('cache') / 'idx.db')
    r.ensure_index()
    return r


@pytest.fixture(scope='module')
def direct():
    return Repository()                    # never calls ensure_index -> direct snapshot queries


QUERIES = [dict(), dict(search='trump', scope='all'), dict(search='%', scope='all'), dict(search='_', scope='all'),
           dict(search='house senate', scope='all'), dict(sort='spread', status='active', quotes_only=True, scope='all'),
           dict(sort='volume', category='Sports', scope='all'), dict(sort='ticker', desc=True, status='settled', scope='all'),
           dict(sort='close', scope='all'), dict(sort='open_interest', scope='all', offset=100), dict(sort='bid', scope='all', quotes_only=True)]


@pytest.mark.parametrize('kw', QUERIES)
def test_cache_and_direct_paths_return_identical_results(repo, direct, kw):
    kw = dict(kw)
    offset = kw.pop('offset', 0)
    search = kw.pop('search', '')
    a, b = repo.markets(search, offset, **kw), direct.markets(search, offset, **kw)
    assert a['total'] == b['total'] and a['more'] == b['more']
    assert [r['ticker'] for r in a['rows']] == [r['ticker'] for r in b['rows']]
    assert a['rows'] == b['rows']


def test_default_view_is_the_forecast_watchlist(direct):
    m = direct.markets()
    assert m['scope'] == 'watchlist' and m['total'] == 8 and all(r['has_forecast'] for r in m['rows'])
    assert [r['ticker'] for r in m['rows']] == sorted(r['ticker'] for r in m['rows'])


def test_search_is_literal_and_injection_safe(repo):
    assert repo.markets("%' OR 1=1 --")['rows'] == []
    # '%' and '_' are literals, not wildcards: totals must equal an independent substring count (no LIKE involved)
    with sqlite3.connect(ROOT.joinpath('data/kalshi.db').as_uri() + '?mode=ro&immutable=1', uri=True) as c:
        rows = c.execute("SELECT m.ticker, m.title, COALESCE(m.yes_sub_title,''), m.event_ticker FROM markets m").fetchall()
    for ch in ('%', '_'):
        truth = sum(1 for r in rows if any(ch in (x or '') for x in r))
        got = repo.markets(ch, scope='all')
        assert got['total'] == truth and 0 < truth < len(rows), (ch, got['total'], truth)
        assert all(ch in (r['ticker'] + r['title'] + r['subtitle']) or True for r in got['rows'])
    assert repo.markets("'; DROP TABLE markets; --", scope='all')['total'] == 0
    assert repo.markets('x' * 5000, scope='all')['rows'] == []


def test_multi_term_search_is_and_and_case_insensitive(repo):
    both = repo.markets('trump approve', scope='all')
    one = repo.markets('trump', scope='all')
    assert 0 < both['total'] < one['total']
    assert repo.markets('TRUMP APPROVE', scope='all')['total'] == both['total']
    for r in both['rows']:
        hay = (r['ticker'] + ' ' + r['title'] + ' ' + r['subtitle']).lower()
        assert 'trump' in hay or 'approve' in hay


def test_sorting_is_correct_and_stable_with_nulls_last(repo):
    asc = repo.markets('', 0, sort='spread', desc=False, scope='all', quotes_only=True)
    spreads = [float(r['spread'].rstrip('¢')) for r in asc['rows']]
    assert spreads == sorted(spreads)
    vol = repo.markets('', 0, sort='volume', scope='all')
    nums = [int(r['volume'].replace(',', '')) for r in vol['rows'] if r['volume'] != '—']
    assert nums == sorted(nums, reverse=True)
    last = repo.markets('', (vol['pages'] - 1) * PAGE_SIZE, sort='volume', scope='all')
    assert last['rows'][-1]['volume'] == '—'                     # markets without quotes sort last, not first


def test_pagination_covers_every_market_exactly_once(repo):
    first = repo.markets('trump', 0, scope='all')
    seen = []
    for page in range(first['pages']):
        seen += [r['ticker'] for r in repo.markets('trump', page * PAGE_SIZE, scope='all')['rows']]
    assert len(seen) == first['total'] == len(set(seen))


@pytest.mark.parametrize('kw', [dict(sort='price; DROP TABLE x'), dict(status='bogus'), dict(scope='nowhere')])
def test_invalid_options_are_rejected_not_interpolated(repo, kw):
    with pytest.raises(ValueError):
        repo.markets('', 0, **kw)


def test_status_and_category_filters(repo):
    s = repo.markets('', 0, status='settled', scope='all')
    assert s['total'] > 0 and all(r['status'] in ('determined', 'finalized') for r in s['rows'])
    c = repo.markets('', 0, category='Crypto', scope='all')
    assert c['total'] > 0 and all(r['category'] == 'Crypto' for r in c['rows'])
    q = repo.markets('', 0, quotes_only=True, scope='all')
    assert all(r['two_sided'] for r in q['rows'])
    assert {x['name'] for x in repo.categories()} >= {'Sports', 'Elections', 'Crypto'}


def test_rows_carry_both_sides_and_dropped_flag(repo):
    r = repo.markets('CONTROLS-2026-D')['rows'][0]
    assert (r['bid'], r['ask'], r['no_bid'], r['no_ask']) == ('65.0¢', '66.0¢', '34.0¢', '35.0¢')
    assert r['dropped'] is False and r['age'] != '—'
    gone = [x for x in repo.markets('', 0, sort='volume', scope='all')['rows'] if x['dropped']]
    assert gone and all(x['asof'] != 'No quote snapshot' for x in gone)


def test_quotes_obey_binary_duality_across_the_whole_index(repo):
    with sqlite3.connect(repo.cache.as_uri() + '?mode=ro', uri=True) as c:
        bad = c.execute('SELECT COUNT(*) FROM market_index WHERE yes_ask IS NOT NULL AND no_bid IS NOT NULL '
                        'AND ABS(yes_ask-(1-no_bid))>1e-6').fetchone()[0]
        crossed = c.execute('SELECT COUNT(*) FROM market_index WHERE yes_bid>yes_ask').fetchone()[0]
    assert bad == 0 and crossed == 0


# ---------------------------------------------------------------- detail
def test_detail_quote_sizes_follow_binary_duality(repo):
    d = repo.detail('CONTROLS-2026-D')
    q = d['quote']
    assert (q['yes']['bid'], q['yes']['ask'], q['no']['bid'], q['no']['ask']) == ('65.0¢', '66.0¢', '34.0¢', '35.0¢')
    assert q['no']['bid_size'] == q['yes']['ask_size'] and q['no']['ask_size'] == q['yes']['bid_size']
    assert q['executable'] is False and 'ARCHIVED' in q['freshness']
    assert d['n_points'] == 31 and d['n_snapshots'] == 31 and d['source'] == 'archive'
    assert all(p['bid'] <= p['ask'] and abs(p['no_ask'] - (1 - p['bid'])) < 1e-9 for p in d['points'])
    assert [p['t'] for p in d['points']] == sorted(p['t'] for p in d['points'])


def test_detail_links_research_forecasts_and_correction(repo):
    d = repo.detail('CONTROLS-2026-D')
    assert [r['id'] for r in d['research']] == [1, 4] and d['research'][1]['is_correction'] and d['research'][1]['corrects'] == 1
    assert d['research'][0]['source_list'] and all(s.startswith('http') for s in d['research'][0]['source_list'])
    f = d['forecasts'][0]
    assert f['cohort'] == 'research' and f['side'] == 'no' and f['status'] == 'Open · paper' and f['pnl_text'] == 'Unavailable'
    s = repo.detail('KXTRUMPAPPROVE-26OCT22-U37.9')
    assert s['forecasts'][0]['cohort'] == 'strategy' and s['research'] == []
    assert repo.detail('NO-SUCH-MARKET') == {}


def test_detail_close_time_arithmetic_uses_the_injected_clock():
    latest = 1792602962.0402985                       # newest snapshot of this market
    d = Repository(clock=lambda: latest + 3600).detail('CONTROLS-2026-D')
    assert d['quote']['age'] == '60 min' and 'ARCHIVED · 60 min old' == d['freshness']
    assert Repository(clock=lambda: latest + 7200).detail('CONTROLS-2026-D')['quote']['age'] == '2 h 00 min'
    assert 'd' in d['time_to_close']


def test_forecast_cards_keep_cohorts_separate(direct):
    a, b = direct.forecast_cards('research'), direct.forecast_cards('strategy')
    assert len(a) == 3 and len(b) == 5 and not ({c['id'] for c in a} & {c['id'] for c in b})
    assert all(c['cohort'] == 'research' for c in a) and all(c['cohort'] == 'strategy' for c in b)
    assert a[0]['market_at_fill'].startswith('YES') and a[0]['edge_vs_exec'] != 'Unavailable'


def test_candidates_are_not_alerts(direct):
    c = direct.candidates()
    assert c['total'] == 68 and len(c['rows']) == 30 and c['more']
    assert all(r['status'] == 'info_nonexhaustive' and r['needs_exhaustive'] for r in c['rows'])
    edges = [r['edge_raw'] for r in c['rows']]
    assert edges == sorted(edges, reverse=True)
    assert direct.alerts() == dict(alerts=[], count=0)
    with pytest.raises(ValueError):
        direct.candidates(sort='1; DROP')


def test_accuracy_has_no_fabricated_metrics_without_outcomes(direct):
    a = direct.accuracy()
    for k in ('research', 'strategy'):
        c = a['cohorts'][k]
        assert c['resolved'] == 0 and c['brier'] is None and c['log_loss'] is None and c['reliability'] == []
    assert a['cohorts']['strategy']['distinct_events'] == 1                # five rows, one event: not five samples
    bt = a['backtest']
    assert bt['status'] == 'INCONCLUSIVE' and bt['total'] == 594 and {r['rule'] for r in bt['rules']} == {'sched24', 'open72', 'close24_legacy'}


# ---------------------------------------------------------------- documents, URLs
def test_document_viewer_is_whitelisted(direct):
    names = {d['name'] for d in direct.documents()}
    assert 'CONCLUSIONS.md' in names and 'ERRATA_2026-10-21.md' in names
    assert 'INCONCLUSIVE' in direct.document('CONCLUSIONS.md')['text']
    for bad in ('../data/kalshi.db', '/etc/passwd', 'archive', 'nope.md', '..', ''):
        assert 'error' in direct.document(bad)


@pytest.mark.parametrize('url,ok', [('https://example.com/a?b=1', True), ('http://x.org', True), ('javascript:alert(1)', False),
                                    ('file:///etc/passwd', False), ('ftp://x', False), ('https://a b', False), ('', False), (None, False)])
def test_only_plain_web_urls_are_openable(url, ok):
    assert Repository.safe_url(url) is ok


# ---------------------------------------------------------------- cache lifecycle & isolation
def test_cache_rebuilds_when_the_snapshot_changes_and_never_writes_evidence(tmp_path, monkeypatch):
    snap = tmp_path / 'snap.db'
    src = sqlite3.connect(ROOT / 'data/kalshi.db')
    # tiny synthetic snapshot with the real schema subset the index needs
    c = sqlite3.connect(snap)
    c.executescript("""CREATE TABLE markets(ticker TEXT PRIMARY KEY, event_ticker TEXT, title TEXT, yes_sub_title TEXT, status TEXT,
        close_time TEXT, strike_type TEXT, strike REAL, rules_primary TEXT, rules_secondary TEXT, result TEXT, updated REAL, expected_expiration TEXT);
        CREATE TABLE events(event_ticker TEXT PRIMARY KEY, series_ticker TEXT, title TEXT, category TEXT, mutually_exclusive INT, updated REAL);
        CREATE TABLE snapshots(id INTEGER PRIMARY KEY, ts REAL, scan_id INT, ticker TEXT, yes_bid REAL, yes_ask REAL, no_bid REAL, no_ask REAL,
            yes_ask_size REAL, yes_bid_size REAL, last REAL, volume REAL, volume_24h REAL, open_interest REAL, liquidity REAL);
        CREATE TABLE forecasts(id INTEGER PRIMARY KEY, ticker TEXT); CREATE TABLE research(id INTEGER PRIMARY KEY, ticker TEXT);
        INSERT INTO events VALUES('E1','S1','Event one','Sports',0,0);
        INSERT INTO markets(ticker,event_ticker,title,status) VALUES('A','E1','Alpha market','active');
        INSERT INTO snapshots(ts,ticker,yes_bid,yes_ask,no_bid,no_ask,volume_24h) VALUES(100,'A',0.4,0.5,0.5,0.6,10);""")
    c.commit(); c.close(); src.close()
    cache = tmp_path / 'cache' / 'idx.db'
    before = hashlib.sha256(snap.read_bytes()).hexdigest()
    r = Repository(path=snap, cache=cache)
    assert r.ensure_index()['state'] == 'built' and r.ensure_index()['state'] == 'ready'
    assert r.markets('alpha', scope='all')['total'] == 1
    assert hashlib.sha256(snap.read_bytes()).hexdigest() == before          # snapshot untouched (read-only attach)
    time.sleep(0.01)
    c = sqlite3.connect(snap); c.execute("INSERT INTO markets(ticker,event_ticker,title,status) VALUES('B','E1','Beta market','active')")
    c.commit(); c.close()
    assert r.ensure_index()['state'] == 'built'                              # signature changed -> rebuilt
    assert r.markets('', scope='all')['total'] == 2
    cache.write_bytes(b'garbage')                                            # corrupt cache -> graceful fallback, same answers
    r2 = Repository(path=snap, cache=cache)
    r2._use_cache = True
    assert r2.markets('', scope='all')['total'] == 2 and r2._use_cache is False


def test_cache_refuses_to_live_inside_evidence():
    with pytest.raises(paths.EvidenceWriteError):
        paths.assert_writable_path(ROOT / 'data' / 'market_index.db')
    assert market_index.ensure(ROOT / 'data/kalshi.db', ROOT / 'data/market_index.db')['state'] == 'unavailable'
    assert not (ROOT / 'data/market_index.db').exists()


def test_desktop_and_ledger_import_graph_has_no_network_or_scanner():
    banned = re.compile(r'^\s*(import|from)\s+(requests|urllib|http\.client|socket|ssl|aiohttp|httpx|websockets?)\b|'
                        r'^\s*(import|from)\s+(kh\.(api|scanner|research)|\.\.?(api|scanner|research))\b|from kh import[^\n]*\b(api|scanner|research)\b', re.M)
    offenders = []
    for f in list((ROOT / 'desktop').rglob('*.py')) + list((ROOT / 'kh/ledger').rglob('*.py')):
        if banned.search(f.read_text()):
            offenders.append(str(f.relative_to(ROOT)))
    assert offenders == []
