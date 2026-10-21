"""Read-only research queries. Each call owns its SQLite connection (worker-thread safe).

Nothing here writes to evidence, imports a network client, or touches an account. Quotes always
carry their own as-of time; missing values stay missing ('—' / 'Unavailable'), never zero.

Legacy contract kept for the Phase 1-2 tests and QML: ``overview()``, ``markets(search, offset)``
and ``detail(ticker)`` still return every key they used to; new keys are additive.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from kh import db, perf, integrity, calibration
from kh.accounting import amount
from kh.cohorts import forecast_rows, LABELS

from . import index as market_index
from . import paths
from .formatting import (cents, spread_cents, percent, money, count, stamp, short_stamp, age_text, UNAVAILABLE, DASH)
from .freshness import classify, quote_executable

ROOT = paths.ROOT
SNAPSHOT = paths.snapshot_path()
PAGE_SIZE = 50

STATUS_FILTERS = {
    'any': None,
    'active': ('active',),
    'closed': ('closed',),
    'settled': ('determined', 'finalized'),
    'inactive': ('inactive', 'initialized'),
}
# UI sort key -> (index column, default descending?)
SORT_COLUMNS = {
    'ticker': ('ticker', False), 'title': ('title', False), 'status': ('status', False),
    'category': ('category', False), 'close': ('close_time', False), 'bid': ('yes_bid', True),
    'ask': ('yes_ask', False), 'spread': ('spread', False), 'volume': ('volume_24h', True),
    'open_interest': ('open_interest', True), 'last': ('last', True), 'quote_ts': ('quote_ts', True),
}
_LIKE_ESCAPE = str.maketrans({'\\': '\\\\', '%': '\\%', '_': '\\_'})
_URL = re.compile(r'^https?://[^\s]+$', re.I)


def iso_to_ts(text):
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00')).astimezone(timezone.utc).timestamp()
    except ValueError:
        return None


def _json_list(text):
    try:
        v = json.loads(text or '[]')
        return v if isinstance(v, list) else []
    except (TypeError, ValueError):
        return []


class Repository:
    def __init__(self, path=None, clock=time.time, cache=None):
        self.path = Path(path or paths.snapshot_path())
        self.clock = clock
        self.cache = Path(cache) if cache else market_index.cache_path()
        self._use_cache = False          # becomes True only after ensure_index() verified a current cache

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _snapshot_info(c):
        row = c.execute("SELECT * FROM scans WHERE status='ok' ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else {}

    def ensure_index(self):
        """Build/refresh the derived market index (cache only; evidence untouched)."""
        if self.path.resolve() != paths.snapshot_path().resolve() and self.cache == market_index.cache_path():
            # A different snapshot must never share the default cache file.
            self.cache = paths.cache_dir() / f'market_index_{abs(hash(str(self.path.resolve()))) % 10**8}.db'
        info = market_index.ensure(self.path, self.cache)
        self._use_cache = info['state'] in ('ready', 'built')
        return info

    @contextmanager
    def _index_conn(self):
        """Yield (connection, relation) exposing market_index.COLUMNS: the cache if usable, else direct."""
        if self._use_cache and self.cache.exists():
            con = None
            try:
                con = sqlite3.connect(self.cache.as_uri() + '?mode=ro', uri=True)
                con.row_factory = sqlite3.Row
                con.execute('SELECT 1 FROM market_index LIMIT 1')
            except sqlite3.DatabaseError:
                self._use_cache = False
                if con is not None:
                    con.close()
                con = None
            if con is not None:
                try:
                    yield con, 'market_index'
                finally:
                    con.close()
                return
        with db.readonly(self.path) as c:
            yield c, f'({market_index.select_sql("")})'

    # ------------------------------------------------------------------ overview
    def overview(self):
        with db.readonly(self.path) as c:
            last = self._snapshot_info(c)
            cohorts = {}
            for cohort in ('research', 'strategy'):
                s = perf.stats(c, cohort)
                rows = forecast_rows(c, cohort)
                s['cost'] = float(sum(amount(r['qty']) * amount(r['exec_price']) + amount(r['fee']) for r in rows))
                s['rows'] = [dict(r, price=cents(r['exec_price']), fee_text=money(r['fee']),
                                  pnl_text=money(r['pnl']) if r['id'] not in s['accounting_discrepancies'] else 'Mismatch',
                                  probability=f"{r['prob_yes'] * 100:.1f}%",
                                  status='Open · paper' if r['outcome'] is None else 'Resolved · paper') for r in rows]
                s['label'] = LABELS[cohort]
                cohorts[cohort] = s
            categories = [dict(name=r[0] or 'Uncategorized', count=r[1]) for r in c.execute(
                'SELECT e.category,count(*) FROM markets m JOIN events e USING(event_ticker) '
                'GROUP BY e.category ORDER BY count(*) DESC LIMIT 8')]
            scans = [dict(time=stamp(r['finished']), markets=r['markets'] or 0, status=r['status'])
                     for r in c.execute('SELECT * FROM scans ORDER BY id DESC LIMIT 8')]
            errors = integrity.verify(c) + integrity.verify_checkpoints(c)
            counts = {t: c.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
                      for t in ('markets', 'snapshots', 'alerts', 'hash_chain', 'research', 'research_queue', 'candidates',
                                'resolutions', 'scans')}
            classified = sum(v['forecasts_total'] for v in cohorts.values())
            unknown = c.execute('SELECT count(*) FROM forecasts').fetchone()[0] - classified
            statuses = [dict(name=r[0], count=r[1]) for r in c.execute(
                'SELECT status,count(*) FROM markets GROUP BY status ORDER BY count(*) DESC')]
            first_scan = c.execute('SELECT MIN(started) FROM scans').fetchone()[0]
            asof = last.get('finished')
            now = self.clock()
            fresh = classify(asof, now, 'archive')
            return dict(asof=stamp(asof), asof_ts=asof, last=last, cohorts=cohorts, categories=categories, scans=scans,
                        counts=counts, integrity_errors=errors, unknown_forecasts=unknown, statuses=statuses,
                        freshness=dict(level=fresh.level.value, label=fresh.label, detail=fresh.detail, warn=fresh.warn,
                                       age_s=fresh.age_s, age=age_text(fresh.age_s)),
                        coverage=dict(first=stamp(first_scan), last=stamp(asof), scans=counts['scans']),
                        integrity_checked=stamp(now))

    # ------------------------------------------------------------------ markets
    def categories(self):
        with self._index_conn() as (c, rel):
            return [dict(name=r[0], count=r[1]) for r in c.execute(
                f'SELECT category,COUNT(*) FROM {rel} mi GROUP BY category ORDER BY COUNT(*) DESC')]

    def markets(self, search='', offset=0, *, sort=None, desc=None, status='any', category='any',
                quotes_only=False, scope=None):
        terms = [t for t in (search or '').split() if t]
        filtered = bool(terms) or status != 'any' or category not in ('any', '', None) or bool(quotes_only)
        scope = scope or ('all' if filtered else 'watchlist')
        if scope not in ('all', 'watchlist'):
            raise ValueError('scope must be all or watchlist')
        if status not in STATUS_FILTERS:
            raise ValueError(f'unknown status filter {status!r}')
        if sort is None:
            sort = 'ticker' if scope == 'watchlist' else 'volume'
        if sort not in SORT_COLUMNS:
            raise ValueError(f'unknown sort {sort!r}')
        column, default_desc = SORT_COLUMNS[sort]
        descending = default_desc if desc is None else bool(desc)
        offset = max(0, int(offset))
        where, args = [], []
        for t in terms:
            like = '%' + t.translate(_LIKE_ESCAPE) + '%'
            where.append("(mi.ticker LIKE ? ESCAPE '\\' OR mi.title LIKE ? ESCAPE '\\' OR mi.yes_sub LIKE ? ESCAPE '\\' "
                         "OR mi.event_ticker LIKE ? ESCAPE '\\')")
            args += [like] * 4
        if scope == 'watchlist':
            where.append('mi.has_forecast=1')
        if STATUS_FILTERS[status]:
            vals = STATUS_FILTERS[status]
            where.append(f"mi.status IN ({','.join('?' * len(vals))})")
            args += list(vals)
        if category not in ('any', '', None):
            where.append('mi.category=?')
            args.append(category)
        if quotes_only:
            where.append('mi.two_sided=1')
        clause = ('WHERE ' + ' AND '.join(where)) if where else ''
        order = (f"(mi.{column} IS NULL OR mi.{column}=''), mi.{column} {'DESC' if descending else 'ASC'}, mi.ticker ASC")
        now = self.clock()
        with self._index_conn() as (c, rel):
            total = c.execute(f'SELECT COUNT(*) FROM {rel} mi {clause}', args).fetchone()[0]
            rows = c.execute(f'SELECT mi.* FROM {rel} mi {clause} ORDER BY {order} LIMIT {PAGE_SIZE + 1} OFFSET ?',
                             args + [offset]).fetchall()
        asof = self._asof()
        output = [self._market_row(r, now, asof) for r in rows[:PAGE_SIZE]]
        pages = max(1, -(-total // PAGE_SIZE))
        return dict(rows=output, more=len(rows) > PAGE_SIZE, offset=offset, total=total, page=offset // PAGE_SIZE + 1,
                    pages=pages, sort=sort, desc=descending, scope=scope, status=status, category=category or 'any',
                    quotes_only=bool(quotes_only), search=search or '')

    def _asof(self):
        """Completion time of the newest successful scan (None if unavailable)."""
        try:
            with db.readonly(self.path) as c:
                return self._snapshot_info(c).get('finished')
        except (sqlite3.Error, ValueError, OSError):
            return None

    @staticmethod
    def _market_row(r, now, asof=None):
        has_quote = r['quote_ts'] is not None
        # A quote far older than the snapshot's newest scan means the market dropped out of later scans
        # (closed, delisted or filtered). Its price is history, not the snapshot's current view.
        dropped = bool(has_quote and asof and r['quote_ts'] < asof - 2 * 300)
        return dict(ticker=r['ticker'], title=r['title'] or r['ticker'], subtitle=r['yes_sub'] or '', dropped=dropped,
                    category=r['category'] or 'Other',
                    status=r['status'], result=r['result'],
                    bid=cents(r['yes_bid']) if has_quote else DASH, ask=cents(r['yes_ask']) if has_quote else DASH,
                    no_bid=cents(r['no_bid']) if has_quote else DASH, no_ask=cents(r['no_ask']) if has_quote else DASH,
                    spread=spread_cents(r['yes_bid'], r['yes_ask']) if has_quote else DASH,
                    volume=f"{r['volume_24h']:,.0f}" if r['volume_24h'] is not None else DASH,
                    open_interest=f"{r['open_interest']:,.0f}" if r['open_interest'] is not None else DASH,
                    asof=stamp(r['quote_ts']) if has_quote else 'No quote snapshot',
                    age=age_text(now - r['quote_ts']) if has_quote else DASH,
                    close=short_stamp(iso_to_ts(r['close_time'])), has_forecast=bool(r['has_forecast']),
                    has_research=bool(r['has_research']), two_sided=bool(r['two_sided']))

    # ------------------------------------------------------------------ detail
    def detail(self, ticker):
        now = self.clock()
        with db.readonly(self.path) as c:
            m = c.execute('SELECT * FROM markets WHERE ticker=?', (ticker,)).fetchone()
            if m is None:
                return {}
            ev = c.execute('SELECT * FROM events WHERE event_ticker=?', (m['event_ticker'],)).fetchone()
            siblings = c.execute('SELECT COUNT(*) FROM markets WHERE event_ticker=?', (m['event_ticker'],)).fetchone()[0]
            total_snaps = c.execute('SELECT COUNT(*) FROM snapshots WHERE ticker=?', (ticker,)).fetchone()[0]
            raw = list(reversed(c.execute(
                'SELECT ts,yes_bid,yes_ask,no_bid,no_ask,yes_bid_size,yes_ask_size,last,volume_24h,open_interest '
                'FROM snapshots WHERE ticker=? ORDER BY ts DESC LIMIT 2000', (ticker,)).fetchall()))
            latest = raw[-1] if raw else None
            points = [dict(t=r['ts'], bid=r['yes_bid'], ask=r['yes_ask'], no_bid=r['no_bid'], no_ask=r['no_ask'])
                      for r in raw if r['yes_bid'] is not None and r['yes_ask'] is not None]
            if len(points) > 400:   # downsample for rendering, keep both endpoints
                points = points[::max(1, len(points) // 399)][:399] + [points[-1]]
            research = [dict(r) for r in c.execute('SELECT * FROM research WHERE ticker=? ORDER BY id', (ticker,))]
            for r in research:
                r['source_list'] = [s for s in _json_list(r['sources']) if isinstance(s, str)]
                r['secondhand_list'] = [s for s in _json_list(r['secondhand']) if isinstance(s, dict)]
                r['is_correction'] = (r.get('stage') == 'correction')
                ref = re.search(r'research\s*#(\d+)', r.get('method') or '')
                r['corrects'] = int(ref.group(1)) if r['is_correction'] and ref else None
                r['when'] = stamp(r['ts'])
                r['band'] = f"{percent(r['prob_lo'], 0)}–{percent(r['prob_hi'], 0)}" if r['prob_lo'] is not None else DASH
                r['probability'] = percent(r['prob_yes'])
            forecasts = []
            for cohort in ('research', 'strategy'):
                for r in forecast_rows(c, cohort):
                    if r['ticker'] == ticker:
                        forecasts.append(self._forecast_card(r, cohort))
            quote = None
            if latest is not None:
                fresh = classify(latest['ts'], now, 'archive')
                quote = dict(
                    ts=latest['ts'], asof=stamp(latest['ts']), age=age_text(now - latest['ts']),
                    freshness=fresh.label, executable=quote_executable(latest['ts'], now, 'archive'),
                    yes=dict(bid=cents(latest['yes_bid']), ask=cents(latest['yes_ask']),
                             bid_size=count(latest['yes_bid_size']) if latest['yes_bid'] is not None else DASH,
                             ask_size=count(latest['yes_ask_size']) if latest['yes_ask'] is not None else DASH),
                    no=dict(bid=cents(latest['no_bid']), ask=cents(latest['no_ask']),
                            # a NO bid rests against YES asks and a NO ask against YES bids (binary duality)
                            bid_size=count(latest['yes_ask_size']) if latest['no_bid'] is not None else DASH,
                            ask_size=count(latest['yes_bid_size']) if latest['no_ask'] is not None else DASH),
                    spread=spread_cents(latest['yes_bid'], latest['yes_ask']), last=cents(latest['last']),
                    volume_24h=count(latest['volume_24h']), open_interest=count(latest['open_interest']))
            span = (f"{stamp(points[0]['t'])} — {stamp(points[-1]['t'])}" if points else 'No two-sided quote history')
            close_ts = iso_to_ts(m['close_time'])
            return dict(
                ticker=ticker, title=m['title'], subtitle=m['yes_sub_title'] or '', event_ticker=m['event_ticker'],
                event_title=(ev['title'] if ev else '') or '', series=(ev['series_ticker'] if ev else '') or '',
                category=(ev['category'] if ev else '') or 'Other', siblings=siblings, status=m['status'],
                result=m['result'] or '', rules=m['rules_primary'] or 'No settlement rules in snapshot',
                secondary=m['rules_secondary'] or '', close=m['close_time'] or 'Unavailable',
                close_text=stamp(close_ts) if close_ts else 'Unavailable',
                time_to_close=(age_text(close_ts - now) if close_ts and close_ts > now else ('Closed' if close_ts else DASH)),
                expected_expiration=m['expected_expiration'] or '',
                strike=(f"{m['strike_type']} {m['strike']}" if m['strike_type'] else ''),
                points=points, n_points=len(points), n_snapshots=total_snaps, span=span, quote=quote,
                research=research, forecasts=forecasts, source='archive',
                freshness=(classify(latest['ts'], now, 'archive').label if latest is not None else 'NO DATA'))

    @staticmethod
    def _forecast_card(r, cohort):
        mid, exec_p = r['mid_p'], r['exec_implied_p']
        return dict(
            id=r['id'], cohort=cohort, cohort_label=LABELS[cohort], ticker=r['ticker'], side=r['side'],
            prob_yes=r['prob_yes'], prob_lo=r['prob_lo'], prob_hi=r['prob_hi'],
            probability=percent(r['prob_yes']),
            band=(f"{percent(r['prob_lo'], 0)}–{percent(r['prob_hi'], 0)}" if r['prob_lo'] != r['prob_hi'] else 'No band recorded'),
            has_band=r['prob_lo'] != r['prob_hi'], when=stamp(r['ts']), ts=r['ts'],
            price=cents(r['exec_price']), fee_text=money(r['fee']), qty=count(r['qty']),
            mid=percent(mid) if mid is not None else UNAVAILABLE,
            exec_implied=percent(exec_p) if exec_p is not None else UNAVAILABLE,
            mid_p=mid, exec_implied_p=exec_p,
            status='Open · paper' if r['outcome'] is None else 'Resolved · paper',
            outcome=r['outcome'], pnl_text=money(r['pnl']) if r['outcome'] is not None else UNAVAILABLE,
            research_id=r['research_id'], note=r['note'] or '')

    # ------------------------------------------------------------------ research & strategy cards
    def forecast_cards(self, cohort):
        with db.readonly(self.path) as c:
            titles = {r[0]: r[1] for r in c.execute(
                'SELECT ticker,title FROM markets WHERE ticker IN (SELECT ticker FROM forecasts)')}
            cards = []
            for r in forecast_rows(c, cohort):
                card = self._forecast_card(r, cohort)
                card['title'] = titles.get(r['ticker']) or r['ticker']
                card['series'] = r['series'] or ''
                fm = c.execute('SELECT yes_bid,yes_ask,edge_vs_mid,edge_vs_exec FROM forecast_market WHERE forecast_id=?',
                               (r['id'],)).fetchone()
                card['market_at_fill'] = (f"YES {cents(fm['yes_bid'])} / {cents(fm['yes_ask'])}" if fm else UNAVAILABLE)
                card['edge_vs_mid'] = percent(fm['edge_vs_mid']) if fm and fm['edge_vs_mid'] is not None else UNAVAILABLE
                card['edge_vs_exec'] = percent(fm['edge_vs_exec']) if fm and fm['edge_vs_exec'] is not None else UNAVAILABLE
                cards.append(card)
            return cards

    # ------------------------------------------------------------------ candidates / alerts
    def alerts(self):
        with db.readonly(self.path) as c:
            rows = [dict(r) for r in c.execute('SELECT * FROM alerts ORDER BY ts DESC')]
            return dict(alerts=[dict(a, when=stamp(a['ts']), price=cents(a['exec_price'])) for a in rows], count=len(rows))

    def candidates(self, offset=0, sort='edge'):
        order = {'edge': 'edge DESC', 'event': 'event_ticker ASC', 'newest': 'ts DESC'}.get(sort)
        if order is None:
            raise ValueError('unknown candidate sort')
        offset = max(0, int(offset))
        with db.readonly(self.path) as c:
            total = c.execute('SELECT COUNT(*) FROM candidates').fetchone()[0]
            rows = c.execute(f'SELECT id,ts,kind,event_ticker,edge,status,detail FROM candidates '
                             f'ORDER BY {order}, id LIMIT 31 OFFSET ?', (offset,)).fetchall()
            out = []
            for r in rows[:30]:
                d = json.loads(r['detail'] or '{}')
                legs = d.get('legs') or []
                out.append(dict(id=r['id'], kind=r['kind'], event=r['event_ticker'], edge=percent(r['edge']),
                                edge_raw=r['edge'], status=r['status'], n_legs=len(legs), cost=percent(d.get('cost')),
                                needs_exhaustive=bool(d.get('needs_exhaustive')), when=stamp(r['ts']),
                                legs=[dict(ticker=l[0], side=l[1], price=cents(l[2])) for l in legs if len(l) >= 3]))
            return dict(rows=out, total=total, more=len(rows) > 30, offset=offset, sort=sort)

    # ------------------------------------------------------------------ accuracy
    def accuracy(self):
        with db.readonly(self.path) as c:
            cohorts = {}
            for cohort in ('research', 'strategy'):
                s = perf.stats(c, cohort)
                all_rows = forecast_rows(c, cohort)
                done = [r for r in all_rows if r['outcome'] is not None]
                ps = [r['prob_yes'] for r in done]
                ys = [r['outcome'] for r in done]
                s['label'] = LABELS[cohort]
                s['log_loss'] = calibration.log_loss(ps, ys) if done else None
                s['reliability'] = calibration.reliability(ps, ys) if done else []
                s['bands'] = [dict(ticker=r['ticker'], lo=r['prob_lo'], hi=r['prob_hi'], p=r['prob_yes'], side=r['side'])
                              for r in all_rows]
                s['distinct_events'] = len({r['series'] for r in all_rows})
                cohorts[cohort] = s
        return dict(cohorts=cohorts, backtest=self.backtest_summary())

    @staticmethod
    def backtest_summary():
        path = paths.backtest_path()
        status = 'UNKNOWN'
        conclusions = paths.research_docs_dir() / 'CONCLUSIONS.md'
        if conclusions.exists() and 'INCONCLUSIVE' in conclusions.read_text(errors='replace'):
            status = 'INCONCLUSIVE'
        if not path.exists():
            return dict(available=False, status=status)
        try:
            with db.readonly(path) as c:
                rules = [dict(rule=r[0], rows=r[1]) for r in c.execute(
                    'SELECT rule,COUNT(*) FROM pit2 GROUP BY rule ORDER BY rule')]
                excl = c.execute('SELECT COUNT(*) FROM exclusions').fetchone()[0]
            return dict(available=True, status=status, rules=rules, exclusions=excl, total=sum(r['rows'] for r in rules))
        except (sqlite3.Error, ValueError) as exc:
            return dict(available=False, status=status, error=str(exc))

    # ------------------------------------------------------------------ documents
    @staticmethod
    def documents():
        d = paths.research_docs_dir()
        if not d.is_dir():
            return []
        return [dict(name=p.name, size=p.stat().st_size) for p in sorted(d.iterdir())
                if p.is_file() and p.suffix.lower() in ('.md', '.txt', '.csv')]

    def document(self, name):
        if name not in {x['name'] for x in self.documents()}:    # whitelist: no path traversal possible
            return dict(name=name, error='Unknown document')
        p = paths.research_docs_dir() / name
        with p.open('rb') as fh:
            data = fh.read(200_001)
        return dict(name=name, text=data[:200_000].decode('utf-8', 'replace'), truncated=len(data) > 200_000)

    @staticmethod
    def safe_url(text):
        """Only plain http(s) URLs may ever be handed to a browser."""
        return bool(isinstance(text, str) and _URL.match(text.strip()))
