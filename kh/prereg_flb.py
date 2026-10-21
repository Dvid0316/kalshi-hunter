"""Forward paper strategy flb_v1. Parameters are read ONLY from the frozen strategies/flb_v1.json, whose hash must match."""
import json, os, time, hashlib, datetime as dt
from . import quant, perf
from .fees import fee
ROOT = os.path.dirname(os.path.dirname(__file__))
SPEC = os.path.join(ROOT, "strategies", "flb_v1.json")
EXPECTED_SHA = open(SPEC + ".sha256").read().split()[0]


def params():
    raw = open(SPEC, "rb").read()
    if hashlib.sha256(raw).hexdigest() != EXPECTED_SHA: raise RuntimeError("flb_v1.json changed after registration")
    return json.loads(raw)


def run(api, c, now=None):
    P = params(); now = now or time.time(); tag = "prereg_" + P["name"]
    used = c.execute("SELECT COUNT(*) FROM forecasts WHERE note=? AND ts>?", (tag, now - 86400)).fetchone()[0]
    lo, hi = P["decision_window_hours_before_expected_expiration"]
    q = """SELECT m.ticker, m.expected_expiration FROM markets m JOIN events e USING(event_ticker)
           WHERE m.status='active' AND m.expected_expiration IS NOT NULL AND e.category IN (%s)""" % ",".join("?" * len(P["universe_categories"]))
    n = 0
    for t, exp in c.execute(q, P["universe_categories"]).fetchall():
        if any(t.startswith(p) for p in P["exclude_ticker_prefixes"]): continue
        h = (dt.datetime.fromisoformat(exp.replace("Z", "+00:00")).timestamp() - now) / 3600
        if not (lo <= h <= hi): continue
        if c.execute("SELECT 1 FROM forecasts WHERE note=? AND ticker=?", (tag, t)).fetchone(): continue
        ob = api.orderbook(t, 20); top = quant.top_of_book(ob)
        if P["require_two_sided_book"] and (top["yes_bid"] is None or top["yes_ask"] is None): continue
        mid = (top["yes_bid"] + top["yes_ask"]) / 2
        side = "no" if mid <= P["buy_no_if_mid_lte"] else ("yes" if mid >= P["buy_yes_if_mid_gte"] else None)
        if not side: continue
        if used + n >= P["max_entries_per_rolling_24h"]:
            c.execute("INSERT INTO errors(ts,where_,msg) VALUES(?,?,?)", (now, "flb_v1", f"cap reached, skipped {t}")); continue
        perf.record_forecast(api, c, t, side, mid, mid, mid, None, qty=P["contracts"], note=tag)
        n += 1
    c.commit(); return n
