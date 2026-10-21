"""Derived, rebuildable market index.

The evidence snapshot has one index, so sorting 167k markets by volume or spread costs
~150-200 ms per click. This module materialises the *latest quote per market* into a
disposable cache file under ``var/cache`` (never inside evidence). If the cache is missing,
stale or unreadable the repository falls back to the same SELECT run directly against the
snapshot, so the cache can only ever make things faster, never change results.

The snapshot is attached read-only and immutable while building; writes to it are impossible.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import time
from pathlib import Path

from . import paths

log = logging.getLogger('kh.index')
INDEX_VERSION = 2

LATEST = """(SELECT s.* FROM {p}snapshots s
             JOIN (SELECT ticker t, MAX(ts) mts FROM {p}snapshots GROUP BY ticker) l
               ON s.ticker = l.t AND s.ts = l.mts)"""

SELECT = """SELECT m.ticker AS ticker, m.event_ticker AS event_ticker, e.series_ticker AS series_ticker,
    COALESCE(m.title, m.ticker) AS title, COALESCE(m.yes_sub_title, '') AS yes_sub,
    COALESCE(e.title, '') AS event_title, COALESCE(NULLIF(e.category, ''), 'Other') AS category,
    COALESCE(m.status, '') AS status, COALESCE(m.result, '') AS result,
    COALESCE(m.close_time, '') AS close_time, COALESCE(m.expected_expiration, '') AS expected_expiration,
    q.ts AS quote_ts, q.yes_bid AS yes_bid, q.yes_ask AS yes_ask, q.no_bid AS no_bid, q.no_ask AS no_ask,
    q.yes_bid_size AS yes_bid_size, q.yes_ask_size AS yes_ask_size, q.last AS last,
    q.volume AS volume, q.volume_24h AS volume_24h, q.open_interest AS open_interest,
    CASE WHEN q.yes_bid IS NOT NULL AND q.yes_ask IS NOT NULL THEN q.yes_ask - q.yes_bid END AS spread,
    CASE WHEN q.yes_bid IS NOT NULL AND q.yes_ask IS NOT NULL THEN 1 ELSE 0 END AS two_sided,
    EXISTS(SELECT 1 FROM {p}forecasts f WHERE f.ticker = m.ticker) AS has_forecast,
    EXISTS(SELECT 1 FROM {p}research r WHERE r.ticker = m.ticker) AS has_research
  FROM {p}markets m
  LEFT JOIN {p}events e ON e.event_ticker = m.event_ticker
  LEFT JOIN """ + LATEST + " q ON q.ticker = m.ticker"

COLUMNS = ['ticker', 'event_ticker', 'series_ticker', 'title', 'yes_sub', 'event_title', 'category', 'status',
           'result', 'close_time', 'expected_expiration', 'quote_ts', 'yes_bid', 'yes_ask', 'no_bid', 'no_ask',
           'yes_bid_size', 'yes_ask_size', 'last', 'volume', 'volume_24h', 'open_interest', 'spread',
           'two_sided', 'has_forecast', 'has_research']


def select_sql(prefix: str = '') -> str:
    return SELECT.format(p=prefix)


def cache_path() -> Path:
    return paths.cache_dir() / 'market_index.db'


def _signature(snapshot: Path) -> str:
    st = snapshot.stat()
    with sqlite3.connect(snapshot.as_uri() + '?mode=ro&immutable=1', uri=True) as c:
        top = c.execute('SELECT COALESCE(MAX(id), 0) FROM snapshots').fetchone()[0]
    return f'v{INDEX_VERSION}:{st.st_size}:{st.st_mtime_ns}:{top}'


def is_current(snapshot: Path | None = None, cache: Path | None = None) -> bool:
    snapshot = Path(snapshot or paths.snapshot_path())
    cache = Path(cache or cache_path())
    if not cache.exists():
        return False
    try:
        with sqlite3.connect(cache.as_uri() + '?mode=ro', uri=True) as c:
            got = c.execute("SELECT v FROM meta WHERE k='signature'").fetchone()
        return bool(got) and got[0] == _signature(snapshot)
    except sqlite3.Error:
        return False


def ensure(snapshot: Path | None = None, cache: Path | None = None) -> dict:
    """Build the cache if needed. Never raises: returns {'state': 'ready'|'built'|'unavailable', ...}."""
    snapshot = Path(snapshot or paths.snapshot_path()).resolve()
    cache = Path(cache or cache_path())
    t0 = time.perf_counter()
    try:
        paths.assert_writable_path(cache)
        if is_current(snapshot, cache):
            return {'state': 'ready', 'seconds': 0.0}
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_name(f'{cache.name}.tmp-{os.getpid()}')
        tmp.unlink(missing_ok=True)
        sig = _signature(snapshot)
        con = sqlite3.connect(tmp.as_uri(), uri=True)
        try:
            con.execute('ATTACH DATABASE ? AS ev', (snapshot.as_uri() + '?mode=ro&immutable=1',))
            cols = ', '.join(COLUMNS)
            con.execute(f'CREATE TABLE market_index AS {select_sql("ev.")}')
            for name, col in (('status', 'status'), ('category', 'category'), ('volume', 'volume_24h'), ('spread', 'spread'),
                              ('close', 'close_time'), ('title', 'title'), ('ticker', 'ticker'), ('bid', 'yes_bid'),
                              ('ask', 'yes_ask'), ('oi', 'open_interest'), ('fc', 'has_forecast')):
                con.execute(f'CREATE INDEX ix_{name} ON market_index({col})')
            con.execute('CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT)')
            rows = con.execute('SELECT COUNT(*) FROM market_index').fetchone()[0]
            con.execute("INSERT INTO meta VALUES('signature', ?), ('rows', ?), ('built', ?)", (sig, str(rows), str(time.time())))
            con.commit()
            con.execute('DETACH DATABASE ev')
        finally:
            con.close()
        os.replace(tmp, cache)
        secs = round(time.perf_counter() - t0, 2)
        log.info('market index built: %s rows in %ss', rows, secs)
        return {'state': 'built', 'rows': rows, 'seconds': secs}
    except Exception as exc:                      # cache is an optimisation; never fatal
        log.warning('market index unavailable (%s); using direct queries', exc)
        return {'state': 'unavailable', 'error': str(exc)}
