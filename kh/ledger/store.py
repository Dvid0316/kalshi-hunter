"""SQLite store for the personal ledger and journal (``account.db``).

Design rules
  * Separate file from research evidence. ``open_store`` refuses any path inside the evidence
    directories and any database that contains evidence tables (``hash_chain``, ``forecasts``).
  * Fills, settlements, cash transactions, journal revisions, conflicts and voids are append-only
    (triggers). A mistaken record is *voided* (kept, excluded from calculations) or corrected by a
    new record; nothing is rewritten, so the audit trail of what was entered survives.
  * Idempotent imports: the exchange record id is the primary key. Same id + same content = ignored;
    same id + different content = kept out of the books and listed as a conflict for review.
  * Amounts are stored as exact decimal text.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from . import models as M

SCHEMA_VERSION = 1
EVIDENCE_TABLES = ('hash_chain', 'forecasts', 'research', 'snapshots')
EVIDENCE_DIR_NAMES = ('data', 'research', 'strategies')

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS import_batches(
  id INTEGER PRIMARY KEY, ts REAL NOT NULL, kind TEXT NOT NULL, source TEXT NOT NULL, label TEXT, sha256 TEXT,
  n_total INT, n_new INT, n_dup INT, n_conflict INT, n_rejected INT, note TEXT);
CREATE TABLE IF NOT EXISTS fills(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, fill_id TEXT NOT NULL UNIQUE, ticker TEXT NOT NULL,
  side TEXT NOT NULL CHECK(side IN ('yes','no')), action TEXT NOT NULL CHECK(action IN ('buy','sell')),
  count TEXT NOT NULL, price TEXT NOT NULL, fee TEXT NOT NULL, ts REAL NOT NULL, order_id TEXT, is_taker INT,
  source TEXT NOT NULL, synthetic_id INT NOT NULL DEFAULT 0, batch_id INT, note TEXT, payload_hash TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS fills_ticker ON fills(ticker, ts);
CREATE TABLE IF NOT EXISTS settlements(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, settlement_id TEXT NOT NULL UNIQUE, ticker TEXT NOT NULL,
  market_result TEXT NOT NULL, settled_ts REAL NOT NULL, revenue TEXT NOT NULL, fee TEXT NOT NULL,
  yes_count TEXT, no_count TEXT, yes_total_cost TEXT, no_total_cost TEXT, source TEXT NOT NULL,
  synthetic_id INT NOT NULL DEFAULT 0, batch_id INT, payload_hash TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS settlements_ticker ON settlements(ticker);
CREATE TABLE IF NOT EXISTS cash_transactions(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, txn_id TEXT NOT NULL UNIQUE, ts REAL NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('deposit','withdrawal','adjustment','other')), amount TEXT NOT NULL, note TEXT,
  source TEXT NOT NULL, synthetic_id INT NOT NULL DEFAULT 0, batch_id INT, payload_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS conflicts(
  id INTEGER PRIMARY KEY, ts REAL NOT NULL, table_name TEXT NOT NULL, record_id TEXT NOT NULL,
  existing_hash TEXT, incoming_hash TEXT, incoming TEXT, batch_id INT);
CREATE TABLE IF NOT EXISTS rejects(id INTEGER PRIMARY KEY, ts REAL NOT NULL, batch_id INT, line TEXT, reason TEXT);
CREATE TABLE IF NOT EXISTS voids(
  id INTEGER PRIMARY KEY, ts REAL NOT NULL, table_name TEXT NOT NULL CHECK(table_name IN ('fills','settlements','cash_transactions')),
  record_id TEXT NOT NULL, reason TEXT NOT NULL, UNIQUE(table_name, record_id));
CREATE TABLE IF NOT EXISTS journal_entries(
  id INTEGER PRIMARY KEY, created REAL NOT NULL, ticker TEXT, entry_type TEXT NOT NULL
  CHECK(entry_type IN ('pre_trade','post_trade','note')), forecast_id INT, fill_id TEXT);
CREATE TABLE IF NOT EXISTS journal_revisions(
  id INTEGER PRIMARY KEY, entry_id INT NOT NULL REFERENCES journal_entries(id), ts REAL NOT NULL, title TEXT NOT NULL,
  body TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '', planned_side TEXT CHECK(planned_side IN ('yes','no') OR planned_side IS NULL),
  planned_price TEXT, my_prob TEXT, deleted INT NOT NULL DEFAULT 0);
"""
_APPEND_ONLY = ('fills', 'settlements', 'cash_transactions', 'conflicts', 'rejects', 'voids', 'journal_entries',
                'journal_revisions', 'import_batches')


class StoreError(RuntimeError):
    pass


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _guard(path: Path):
    """Refuse anything that could be (or sit beside) research evidence."""
    p = Path(path).expanduser().resolve()
    for name in EVIDENCE_DIR_NAMES:
        d = (PROJECT_ROOT / name).resolve()
        if p == d or d in p.parents:
            raise StoreError(f'Refusing to use a path inside evidence directory {name!r}: {p}')
    if (p.parent / 'kalshi.db').exists() or p.name.startswith(('kalshi', 'backtest')):
        raise StoreError(f'Refusing to place an account store beside or named like research evidence: {p}')
    if p.exists():
        with sqlite3.connect(p.as_uri() + '?mode=ro', uri=True) as c:
            names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if names & set(EVIDENCE_TABLES):
            raise StoreError(f'Refusing to open a research-evidence database as an account store: {p}')
    return p


def payload_hash(*parts) -> str:
    return hashlib.sha256('\x1f'.join(str(p) for p in parts).encode()).hexdigest()


@dataclass
class BatchResult:
    kind: str
    n_total: int = 0
    n_new: int = 0
    n_dup: int = 0
    n_conflict: int = 0
    n_rejected: int = 0
    rejected: list = field(default_factory=list)
    batch_id: int | None = None
    source: str = ''
    label: str = ''
    sha256: str | None = None

    def summary(self) -> str:
        return (f'{self.kind}: {self.n_total} records — {self.n_new} new, {self.n_dup} already present, '
                f'{self.n_conflict} conflicting, {self.n_rejected} rejected')


class AccountStore:
    def __init__(self, path):
        self.path = Path(path)
        try:
            self.path = _guard(path)                                    # raises StoreError (not caught below) for evidence paths
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.c = sqlite3.connect(self.path, timeout=10)
            self.c.row_factory = sqlite3.Row
            self.c.execute('PRAGMA journal_mode=WAL')
            self.c.execute('PRAGMA foreign_keys=ON')
            self.c.executescript(_SCHEMA)
            for t in _APPEND_ONLY:
                for op in ('UPDATE', 'DELETE'):
                    self.c.execute(f"CREATE TRIGGER IF NOT EXISTS ro_{t}_{op.lower()} BEFORE {op} ON {t} "
                                   f"BEGIN SELECT RAISE(ABORT, '{t} is append-only'); END")
            self.c.execute("INSERT OR IGNORE INTO meta VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))
            self.c.execute("INSERT OR IGNORE INTO meta VALUES('created', ?)", (str(time.time()),))
            self.c.commit()
        except sqlite3.DatabaseError as exc:
            self.close()
            raise M.LedgerError(
                f'The personal ledger file {path} cannot be opened ({exc}). It was not modified or replaced. '
                'Restore it from a backup, or move it aside to start a new ledger. Nothing has been deleted.') from exc

    def close(self):
        try:
            self.c.close()
        except (AttributeError, sqlite3.Error):
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---------------------------------------------------------------- batches
    def _record_batch_counts(self, result: BatchResult):
        # import_batches is append-only: write the final row once, after counting.
        cur = self.c.execute('INSERT INTO import_batches(ts,kind,source,label,sha256,n_total,n_new,n_dup,n_conflict,n_rejected)'
                             ' VALUES(?,?,?,?,?,?,?,?,?,?)',
                             (time.time(), result.kind, result.source, result.label, result.sha256, result.n_total,
                              result.n_new, result.n_dup, result.n_conflict, result.n_rejected))
        result.batch_id = int(cur.lastrowid or 0)
        return result.batch_id

    # ---------------------------------------------------------------- inserts
    def _upsert(self, table, rid_col, rid, h, values: dict, result: BatchResult, incoming_json: str):
        row = self.c.execute(f'SELECT payload_hash FROM {table} WHERE {rid_col}=?', (rid,)).fetchone()
        if row is None:
            cols = ', '.join(values)
            self.c.execute(f'INSERT INTO {table}({rid_col}, {cols}, payload_hash) VALUES(?,{",".join("?" * len(values))},?)',
                           (rid, *values.values(), h))
            result.n_new += 1
        elif row['payload_hash'] == h:
            result.n_dup += 1
        else:
            self.c.execute('INSERT INTO conflicts(ts,table_name,record_id,existing_hash,incoming_hash,incoming,batch_id) '
                           'VALUES(?,?,?,?,?,?,NULL)', (time.time(), table, rid, row['payload_hash'], h, incoming_json))
            result.n_conflict += 1

    @staticmethod
    def _new_result(kind, source, label, sha, total) -> BatchResult:
        return BatchResult(kind=kind, n_total=total, source=source, label=label, sha256=sha)

    def add_fills(self, fills, *, source='manual', label='', sha256=None, rejected=()) -> BatchResult:
        """Insert validated Fill objects. Fills with an empty id get a deterministic synthetic id so
        re-importing the same file is idempotent; identical fills inside one batch get distinct ordinals."""
        res = self._new_result('fills', source, label, sha256, len(fills) + len(rejected))
        res.n_rejected = len(rejected)
        res.rejected = list(rejected)
        seen: dict[str, int] = {}
        with self.c:
            for f in fills:
                synthetic = not f.fill_id
                content = (f.ticker, f.side, f.action, M.s(f.count), M.s(f.price), M.s(f.fee), f'{f.ts:.6f}', f.order_id)
                if synthetic:
                    base = payload_hash(*content)[:20]
                    seen[base] = seen.get(base, 0) + 1
                    rid = f'syn:{base}:{seen[base]}'
                else:
                    rid = f.fill_id
                h = payload_hash(*content)
                values = dict(ticker=f.ticker, side=f.side, action=f.action, count=M.s(f.count), price=M.s(f.price),
                              fee=M.s(f.fee), ts=f.ts, order_id=f.order_id, is_taker=None if f.is_taker is None else int(f.is_taker),
                              source=source, synthetic_id=int(synthetic), batch_id=None, note=f.note)
                self._upsert('fills', 'fill_id', rid, h, values, res, json.dumps(dict(zip(
                    ('ticker', 'side', 'action', 'count', 'price', 'fee', 'ts', 'order_id'), content))))
            self._log_rejects(res)
            self._record_batch_counts(res)
        return res

    def add_settlements(self, items, *, source='manual', label='', sha256=None, rejected=()) -> BatchResult:
        res = self._new_result('settlements', source, label, sha256, len(items) + len(rejected))
        res.n_rejected = len(rejected)
        res.rejected = list(rejected)
        with self.c:
            for x in items:
                synthetic = not x.settlement_id
                content = (x.ticker, x.market_result, f'{x.settled_ts:.6f}', M.s(x.revenue), M.s(x.fee),
                           *(M.s(v) if v is not None else '' for v in (x.yes_count, x.no_count, x.yes_total_cost, x.no_total_cost)))
                rid = x.settlement_id or f'syn:{payload_hash(x.ticker)[:12]}:{x.ticker}'
                h = payload_hash(*content)
                values = dict(ticker=x.ticker, market_result=x.market_result, settled_ts=x.settled_ts,
                              revenue=M.s(x.revenue), fee=M.s(x.fee),
                              yes_count=None if x.yes_count is None else M.s(x.yes_count),
                              no_count=None if x.no_count is None else M.s(x.no_count),
                              yes_total_cost=None if x.yes_total_cost is None else M.s(x.yes_total_cost),
                              no_total_cost=None if x.no_total_cost is None else M.s(x.no_total_cost),
                              source=source, synthetic_id=int(synthetic), batch_id=None)
                self._upsert('settlements', 'settlement_id', rid, h, values, res, json.dumps(content))
            self._log_rejects(res)
            self._record_batch_counts(res)
        return res

    def add_cash(self, items, *, source='manual', label='', sha256=None, rejected=()) -> BatchResult:
        res = self._new_result('cash', source, label, sha256, len(items) + len(rejected))
        res.n_rejected = len(rejected)
        res.rejected = list(rejected)
        seen: dict[str, int] = {}
        with self.c:
            for x in items:
                content = (f'{x.ts:.6f}', x.kind, M.s(x.amount), x.note)
                synthetic = not x.txn_id
                if synthetic:
                    base = payload_hash(*content)[:20]
                    seen[base] = seen.get(base, 0) + 1
                    rid = f'syn:{base}:{seen[base]}'
                else:
                    rid = x.txn_id
                h = payload_hash(*content)
                values = dict(ts=x.ts, kind=x.kind, amount=M.s(x.amount), note=x.note, source=source,
                              synthetic_id=int(synthetic), batch_id=None)
                self._upsert('cash_transactions', 'txn_id', rid, h, values, res, json.dumps(content))
            self._log_rejects(res)
            self._record_batch_counts(res)
        return res

    def _log_rejects(self, res: BatchResult):
        for line, reason in res.rejected:
            self.c.execute('INSERT INTO rejects(ts,batch_id,line,reason) VALUES(?,NULL,?,?)', (time.time(), str(line)[:500], reason))

    def void(self, table: str, record_id: str, reason: str):
        if not reason.strip():
            raise M.LedgerError('A reason is required to void a record')
        col = {'fills': 'fill_id', 'settlements': 'settlement_id', 'cash_transactions': 'txn_id'}.get(table)
        if col is None:
            raise M.LedgerError('Only fills, settlements and cash transactions can be voided')
        if self.c.execute(f'SELECT 1 FROM {table} WHERE {col}=?', (record_id,)).fetchone() is None:
            raise M.LedgerError(f'No such {table} record: {record_id}')
        with self.c:
            self.c.execute('INSERT OR IGNORE INTO voids(ts,table_name,record_id,reason) VALUES(?,?,?,?)',
                           (time.time(), table, record_id, reason.strip()))

    # ---------------------------------------------------------------- reads
    def voided(self, table):
        return {r[0] for r in self.c.execute('SELECT record_id FROM voids WHERE table_name=?', (table,))}

    def fills(self, include_voided=False):
        voided = set() if include_voided else self.voided('fills')
        out = []
        for r in self.c.execute('SELECT * FROM fills ORDER BY ts, seq'):
            if r['fill_id'] in voided:
                continue
            out.append(M.Fill(fill_id=r['fill_id'], ticker=r['ticker'], side=r['side'], action=r['action'],
                              count=Decimal(r['count']), price=Decimal(r['price']), fee=Decimal(r['fee']), ts=r['ts'],
                              order_id=r['order_id'] or '', is_taker=None if r['is_taker'] is None else bool(r['is_taker']),
                              source=r['source'], synthetic_id=bool(r['synthetic_id']), note=r['note'] or '', seq=r['seq']))
        return out

    def settlements(self):
        voided = self.voided('settlements')
        dd = lambda v: None if v is None else Decimal(v)
        return [M.Settlement(settlement_id=r['settlement_id'], ticker=r['ticker'], market_result=r['market_result'],
                             settled_ts=r['settled_ts'], revenue=Decimal(r['revenue']), fee=Decimal(r['fee']),
                             yes_count=dd(r['yes_count']), no_count=dd(r['no_count']), yes_total_cost=dd(r['yes_total_cost']),
                             no_total_cost=dd(r['no_total_cost']), source=r['source'])
                for r in self.c.execute('SELECT * FROM settlements ORDER BY settled_ts, seq') if r['settlement_id'] not in voided]

    def cash(self):
        voided = self.voided('cash_transactions')
        return [M.CashTransaction(txn_id=r['txn_id'], ts=r['ts'], kind=r['kind'], amount=Decimal(r['amount']),
                                  note=r['note'] or '', source=r['source'])
                for r in self.c.execute('SELECT * FROM cash_transactions ORDER BY ts, seq') if r['txn_id'] not in voided]

    def conflicts(self):
        return [dict(r) for r in self.c.execute('SELECT * FROM conflicts ORDER BY id')]

    def rejects(self):
        return [dict(r) for r in self.c.execute('SELECT * FROM rejects ORDER BY id')]

    def batches(self):
        return [dict(r) for r in self.c.execute('SELECT * FROM import_batches ORDER BY id DESC')]

    def counts(self):
        q = lambda t: self.c.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
        return dict(fills=q('fills'), settlements=q('settlements'), cash=q('cash_transactions'), conflicts=q('conflicts'),
                    rejects=q('rejects'), voids=q('voids'), journal=q('journal_entries'), batches=q('import_batches'))

    def is_empty(self):
        c = self.counts()
        return not (c['fills'] or c['settlements'] or c['cash'])

    # ---------------------------------------------------------------- journal
    def journal_add(self, *, title, body='', ticker=None, entry_type='note', tags='', forecast_id=None, fill_id=None,
                    planned_side=None, planned_price=None, my_prob=None) -> int:
        title = (title or '').strip()
        if not title:
            raise M.LedgerError('A journal entry needs a title')
        if entry_type not in ('pre_trade', 'post_trade', 'note'):
            raise M.LedgerError('entry_type must be pre_trade, post_trade or note')
        tk = M.ticker(ticker) if ticker else None
        side = M.choice(planned_side, M.SIDES, 'planned_side') if planned_side else None
        pp = M.s(M.price(planned_price)) if planned_price not in (None, '') else None
        prob = None
        if my_prob not in (None, ''):
            p = M.dec(my_prob, 'my_prob')
            if not (M.ZERO <= p <= M.ONE):
                raise M.LedgerError('my_prob must be between 0 and 1')
            prob = M.s(p)
        now = time.time()
        with self.c:
            cur = self.c.execute('INSERT INTO journal_entries(created,ticker,entry_type,forecast_id,fill_id) VALUES(?,?,?,?,?)',
                                 (now, tk, entry_type, forecast_id, fill_id))
            self.c.execute('INSERT INTO journal_revisions(entry_id,ts,title,body,tags,planned_side,planned_price,my_prob) '
                           'VALUES(?,?,?,?,?,?,?,?)', (cur.lastrowid, now, title[:200], body[:20000], tags[:200], side, pp, prob))
        return cur.lastrowid

    def journal_revise(self, entry_id, *, title, body='', tags='', planned_side=None, planned_price=None, my_prob=None,
                       deleted=False):
        if self.c.execute('SELECT 1 FROM journal_entries WHERE id=?', (entry_id,)).fetchone() is None:
            raise M.LedgerError(f'No such journal entry {entry_id}')
        side = M.choice(planned_side, M.SIDES, 'planned_side') if planned_side else None
        pp = M.s(M.price(planned_price)) if planned_price not in (None, '') else None
        prob = M.s(M.dec(my_prob, 'my_prob')) if my_prob not in (None, '') else None
        with self.c:
            self.c.execute('INSERT INTO journal_revisions(entry_id,ts,title,body,tags,planned_side,planned_price,my_prob,deleted) '
                           'VALUES(?,?,?,?,?,?,?,?,?)', (entry_id, time.time(), (title or '').strip()[:200] or '(untitled)',
                                                         body[:20000], tags[:200], side, pp, prob, int(bool(deleted))))

    def journal(self, *, ticker=None, query=None, include_deleted=False, include_history=False):
        out = []
        for e in self.c.execute('SELECT * FROM journal_entries ORDER BY created DESC, id DESC'):
            revs = list(self.c.execute('SELECT * FROM journal_revisions WHERE entry_id=? ORDER BY id', (e['id'],)))
            cur = revs[-1]
            if cur['deleted'] and not include_deleted:
                continue
            if ticker and e['ticker'] != ticker:
                continue
            if query:
                hay = ' '.join(filter(None, (cur['title'], cur['body'], cur['tags'], e['ticker'] or ''))).lower()
                if not all(t in hay for t in query.lower().split()):
                    continue
            item = dict(id=e['id'], created=e['created'], updated=cur['ts'], ticker=e['ticker'], entry_type=e['entry_type'],
                        forecast_id=e['forecast_id'], fill_id=e['fill_id'], title=cur['title'], body=cur['body'], tags=cur['tags'],
                        planned_side=cur['planned_side'], planned_price=cur['planned_price'], my_prob=cur['my_prob'],
                        revisions=len(revs), deleted=bool(cur['deleted']))
            if include_history:
                item['history'] = [dict(r) for r in revs]
            out.append(item)
        return out


def open_store(path) -> AccountStore:
    return AccountStore(path)
