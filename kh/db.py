import sqlite3, json, time, os
SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS scans(id INTEGER PRIMARY KEY, started REAL, finished REAL, events INT, markets INT,
  candidates INT, status TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS api_log(id INTEGER PRIMARY KEY, ts REAL, path TEXT, status INT, ms REAL);
CREATE TABLE IF NOT EXISTS errors(id INTEGER PRIMARY KEY, ts REAL, where_ TEXT, msg TEXT);
CREATE TABLE IF NOT EXISTS events(event_ticker TEXT PRIMARY KEY, series_ticker TEXT, title TEXT, category TEXT,
  mutually_exclusive INT, updated REAL);
CREATE TABLE IF NOT EXISTS markets(ticker TEXT PRIMARY KEY, event_ticker TEXT, title TEXT, yes_sub_title TEXT,
  status TEXT, close_time TEXT, strike_type TEXT, strike REAL, rules_primary TEXT, rules_secondary TEXT,
  result TEXT, updated REAL);
CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY, ts REAL, scan_id INT, ticker TEXT, yes_bid REAL,
  yes_ask REAL, no_bid REAL, no_ask REAL, yes_ask_size REAL, yes_bid_size REAL, last REAL, volume REAL,
  volume_24h REAL, open_interest REAL, liquidity REAL);
CREATE INDEX IF NOT EXISTS snap_t ON snapshots(ticker, ts);
CREATE TABLE IF NOT EXISTS candidates(id INTEGER PRIMARY KEY, ts REAL, kind TEXT, key TEXT, event_ticker TEXT,
  edge REAL, detail TEXT, audit TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS research(id INTEGER PRIMARY KEY, ts REAL, ticker TEXT, prob_yes REAL, prob_lo REAL,
  prob_hi REAL, method TEXT, sources TEXT, counter_evidence TEXT, auditor TEXT, author TEXT);
CREATE TABLE IF NOT EXISTS forecasts(id INTEGER PRIMARY KEY, ts REAL, ticker TEXT, side TEXT, prob_yes REAL,
  prob_lo REAL, prob_hi REAL, est_price REAL, exec_price REAL, exec_ts REAL, qty REAL, fee REAL, ev REAL,
  research_id INT, note TEXT, resolved INT DEFAULT 0, outcome INT, pnl REAL, resolved_ts REAL);
CREATE TABLE IF NOT EXISTS slippage(id INTEGER PRIMARY KEY, ts REAL, ticker TEXT, side TEXT, est_price REAL,
  exec_price REAL, diff REAL);
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
"""
DEFAULT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "kalshi.db")


def connect(path=DEFAULT):
    c = sqlite3.connect(path, timeout=30)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def log_error(c, where, msg):
    c.execute("INSERT INTO errors(ts,where_,msg) VALUES(?,?,?)", (time.time(), where, str(msg)[:2000])); c.commit()


def upsert_candidate(c, kind, key, event_ticker, edge, detail, audit, status):
    """Append-only: a new row whenever a screen result is new or its edge changed (or hourly heartbeat)."""
    last = c.execute("SELECT ts, edge FROM candidates WHERE kind=? AND key=? ORDER BY id DESC LIMIT 1", (kind, key)).fetchone()
    if last and last[1] == edge and time.time() - last[0] < 3600: return None
    return c.execute("""INSERT INTO candidates(ts,kind,key,event_ticker,edge,detail,audit,status) VALUES(?,?,?,?,?,?,?,?)""",
              (time.time(), kind, key, event_ticker, edge, json.dumps(detail), json.dumps(audit), status)).lastrowid

EXTRA = """
CREATE TABLE IF NOT EXISTS research_queue(id INTEGER PRIMARY KEY, ts REAL, ticker TEXT, reason TEXT, status TEXT DEFAULT 'queued',
  claimed_at REAL, done_at REAL, note TEXT);
CREATE TABLE IF NOT EXISTS research_runs(id INTEGER PRIMARY KEY, ts REAL, queue_id INT, ticker TEXT, stage TEXT, tool_calls INT,
  web_searches INT, web_fetches INT, urls_verified INT, urls_failed INT, seconds REAL, est_cost_usd REAL, outcome TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY, ts REAL, ticker TEXT, side TEXT, research_id INT, forecast_id INT,
  exec_price REAL, ev REAL, ev_worst REAL, payload TEXT, approved_by_auditor INT, alerted_at REAL);
"""
MIGRATIONS = [("research", "secondhand", "TEXT"), ("research", "stage", "TEXT"), ("research", "queue_id", "INT"),
              ("research", "contrarian", "TEXT"), ("research_runs", "payload", "TEXT"), ("scans", "tradable", "INT"),
              ("scans", "api_ok", "INT"), ("scans", "api_fail", "INT"), ("markets", "expected_expiration", "TEXT")]
APPEND_ONLY = ["forecasts", "research", "research_runs", "resolutions", "research_audits", "forecast_market",
               "candidates", "candidate_audits", "candidates_legacy"]
EXTRA2 = """
CREATE TABLE IF NOT EXISTS resolutions(id INTEGER PRIMARY KEY, ts REAL, forecast_id INT UNIQUE, outcome INT, pnl REAL);
CREATE TABLE IF NOT EXISTS research_audits(id INTEGER PRIMARY KEY, ts REAL, research_id INT, notes TEXT);
CREATE TABLE IF NOT EXISTS forecast_market(id INTEGER PRIMARY KEY, ts REAL, forecast_id INT UNIQUE, yes_bid REAL, yes_ask REAL,
  mid_p REAL, exec_implied_p REAL, edge_vs_mid REAL, edge_vs_exec REAL, note TEXT);
CREATE TABLE IF NOT EXISTS candidate_audits(id INTEGER PRIMARY KEY, ts REAL, candidate_id INT, status TEXT, audit TEXT);
CREATE TABLE IF NOT EXISTS service_starts(id INTEGER PRIMARY KEY, ts REAL, pid INT);
"""
_connect = connect


def _migrate_candidates(c):
    sql = (c.execute("SELECT sql FROM sqlite_master WHERE name='candidates'").fetchone() or [""])[0]
    if "UNIQUE" in sql:  # old mutable schema -> keep as legacy, start append-only log
        c.execute("ALTER TABLE candidates RENAME TO candidates_legacy"); c.commit()


def connect(path=DEFAULT):
    c0 = sqlite3.connect(path, timeout=30); _migrate_candidates(c0); c0.close()
    c = _connect(path); c.executescript(EXTRA); c.executescript(EXTRA2)
    for t, col, typ in MIGRATIONS:
        if col not in [r[1] for r in c.execute(f"PRAGMA table_info({t})")]:
            c.execute(f"ALTER TABLE {t} ADD COLUMN {col} {typ}")
    have = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in [x for x in APPEND_ONLY if x in have]:  # immutable history: corrections must be new rows
        for op in ("UPDATE", "DELETE"):
            c.execute(f"CREATE TRIGGER IF NOT EXISTS ro_{t}_{op.lower()} BEFORE {op} ON {t} "
                      f"BEGIN SELECT RAISE(ABORT, '{t} is append-only'); END")
    c.commit(); return c


from contextlib import contextmanager


@contextmanager
def readonly(path):
    """Open an existing database without schema changes or sidecar creation.

    Only for the static offline snapshot; never a live WAL database.
    """
    from pathlib import Path
    p = Path(path).resolve(strict=True)
    if Path(str(p)+'-wal').exists():
        raise ValueError('Offline snapshot must not have an active WAL')
    c = sqlite3.connect(p.as_uri()+'?mode=ro&immutable=1', uri=True)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA query_only=ON')
    try:
        yield c
    finally:
        c.close()
