import time, json, re
from . import quant
from .db import upsert_candidate, log_error

PRIORITY = ["Politics", "Elections", "Economics", "Financials", "Science and Technology", "Climate and Weather"]


def f(x):
    try: return float(x) if x not in (None, "") else None
    except (TypeError, ValueError): return None


def px(m, k):
    v = f(m.get(k));  # Kalshi reports 0 ask/bid when no level exists
    return v if v is not None and 0 < v < 1 else None


def refresh_series(api, c, max_age=6 * 3600):
    row = c.execute("SELECT v FROM kv WHERE k='series_ts'").fetchone()
    if row and time.time() - float(row[0]) < max_age: return
    mult = {}
    for s in api.get("/series").get("series") or []:
        mult[s["ticker"]] = {"m": s.get("fee_multiplier", 1), "type": s.get("fee_type"), "cat": s.get("category")}
    c.execute("INSERT OR REPLACE INTO kv VALUES('series',?)", (json.dumps(mult),))
    c.execute("INSERT OR REPLACE INTO kv VALUES('series_ts',?)", (str(time.time()),)); c.commit()


def series_info(c):
    row = c.execute("SELECT v FROM kv WHERE k='series'").fetchone()
    return json.loads(row[0]) if row else {}


def fee_mult(info, series):
    s = info.get(series) or {}
    if s.get("type") in ("fee_free", "free") : return 0.0
    return float(s.get("m") if s.get("m") is not None else 1)


NUM = re.compile(r"[-+]?\$?\d[\d,]*\.?\d*%?")


THRESH = re.compile(r"above|greater than|more than|at least|or more|below|less than|under|fewer than|or less|or fewer")
NOT_THRESH = re.compile(r"exactly|between|range")


def rules_template(m):
    return NUM.sub("#", (m.get("rules_primary") or "")).strip()


def scan(api, c, max_pages=250):
    t0 = time.time()
    cur = c.execute("INSERT INTO scans(started,status) VALUES(?, 'running')", (t0,)); sid = cur.lastrowid; c.commit()
    refresh_series(api, c); info = series_info(c)
    nev = nm = ncand = ntrad = 0; ok0, fail0 = api.ok, api.fail
    events = []
    for ev in api.paged("/events", "events", {"status": "open", "with_nested_markets": "true", "limit": 200}, max_pages):
        if ev["event_ticker"].startswith("KXMVE"): continue
        events.append(ev)
    rank = {cat: i for i, cat in enumerate(PRIORITY)}
    events.sort(key=lambda e: rank.get(e.get("category"), 99))
    for ev in events:
        nev += 1
        c.execute("INSERT OR REPLACE INTO events VALUES(?,?,?,?,?,?)", (ev["event_ticker"], ev.get("series_ticker"),
                  ev.get("title"), ev.get("category"), int(bool(ev.get("mutually_exclusive"))), t0))
        mk = []
        for m in ev.get("markets") or []:
            nm += 1
            strike = f(m.get("floor_strike")) if m.get("strike_type") == "greater" else f(m.get("cap_strike")) if m.get("strike_type") == "less" else None
            c.execute("""INSERT OR REPLACE INTO markets(ticker,event_ticker,title,yes_sub_title,status,close_time,strike_type,strike,
                      rules_primary,rules_secondary,result,updated,expected_expiration) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (m["ticker"], ev["event_ticker"],
                      m.get("title"), m.get("yes_sub_title"), m.get("status"), m.get("close_time"), m.get("strike_type"),
                      strike, m.get("rules_primary"), m.get("rules_secondary"), m.get("result"), t0, m.get("expected_expiration_time")))
            ya, yb, na, nb = px(m, "yes_ask_dollars"), px(m, "yes_bid_dollars"), px(m, "no_ask_dollars"), px(m, "no_bid_dollars")
            if (f(m.get("volume_24h_fp")) or 0) > 0 or ev.get("category") in ("Politics", "Elections") and (ya or yb):
              c.execute("""INSERT INTO snapshots(ts,scan_id,ticker,yes_bid,yes_ask,no_bid,no_ask,yes_ask_size,yes_bid_size,last,
                      volume,volume_24h,open_interest,liquidity) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (t0, sid, m["ticker"], yb, ya, nb, na, f(m.get("yes_ask_size_fp")), f(m.get("yes_bid_size_fp")),
                       f(m.get("last_price_dollars")), f(m.get("volume_fp")), f(m.get("volume_24h_fp")),
                       f(m.get("open_interest_fp")), f(m.get("liquidity_dollars"))))
            if m.get("status") == "active" and (ya or yb or na or nb):
                ntrad += 1  # TRADABLE = status 'active' AND at least one live bid/ask level (non-empty book)
            if m.get("status") == "active":
                mk.append({"ticker": m["ticker"], "yes_ask": ya, "no_ask": na, "yes_bid": yb, "no_bid": nb,
                           "strike": strike, "strike_type": m.get("strike_type"), "tmpl": rules_template(m)})
        mult = fee_mult(info, ev.get("series_ticker"))
        finds = []
        if ev.get("mutually_exclusive") and len(mk) == len(ev.get("markets") or []):
            finds += quant.mutex_arbs(mk, mult=mult, min_edge=0.0)
        # ladders only within markets that share an identical rules template (same underlying, only the number differs)
        groups = {}
        for x in mk: groups.setdefault(x["tmpl"], []).append(x)
        for g in groups.values():
            t = g[0]["tmpl"].lower()
            # only true threshold ladders: rules must say above/below-type language, never 'exactly'/'between'
            if len(g) >= 2 and t and THRESH.search(t) and not NOT_THRESH.search(t):
                finds += quant.ladder_violations(g, mult=mult, min_edge=0.0)
        for fd in finds:
            ncand += 1
            key = ev["event_ticker"] + "|" + ",".join(f"{t}:{s}" for t, s, _ in fd["legs"])
            upsert_candidate(c, fd["kind"], key, ev["event_ticker"], fd["edge"], fd, {"notes": ["needs exhaustiveness; not riskless"]} if fd["needs_exhaustive"] else {}, "info_nonexhaustive" if fd["needs_exhaustive"] else "screened")
    c.execute("UPDATE scans SET finished=?,events=?,markets=?,candidates=?,tradable=?,api_ok=?,api_fail=?,status='ok' WHERE id=?",
              (time.time(), nev, nm, ncand, ntrad, api.ok - ok0, api.fail - fail0, sid)); c.commit()
    return sid, nev, nm, ncand
