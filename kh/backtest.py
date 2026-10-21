"""Point-in-time backtest of MECHANICAL strategies on settled Kalshi markets (public endpoints only).

Data: GET /markets?status=settled (results), GET /series/{s}/markets/{t}/candlesticks?period_interval=60
(hourly yes_bid/yes_ask OHLC; end_period_ts = inclusive END of the candle). Only markets settled after the
historical cutoff are in the live set; older ones would need /historical/* (not used here).

Prediction time T = min(close_time, settlement_ts) - HORIZON. Features use ONLY candles with end_period_ts < T
(strict). Fills: buy YES at yes_ask close, buy NO at 1 - yes_bid close of that same pre-T candle, + taker fee.
Depth at those quotes is unknown from candles -> assume 1-contract fills (limitation, stated in report).
Hand-researched estimates are NOT backtested (impossible without look-ahead).
"""
import json, time, datetime as dt, sqlite3, os
from .fees import fee
from . import calibration as cal

HORIZON = 24 * 3600
MOM_LOOKBACK = 24 * 3600
DS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "backtest.db")


def iso(t): return dt.datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
def fl(x):
    try: return float(x)
    except (TypeError, ValueError): return None


AVAIL_BUFFER = 3600  # features must end >= 1h before T (candle end != guaranteed publication time)
CATS = ("Politics", "Elections", "Economics", "Financials", "Climate and Weather", "Science and Technology",
        "Companies", "Commodities", "Crypto", "Entertainment", "World", "Health")


def iter_settled(api, series_list, per_series):
    for s in series_list:
        try:
            ms = api.get("/markets", {"status": "settled", "series_ticker": s, "limit": 200}).get("markets") or []
        except Exception:
            continue
        for m in ms[: per_series * 4]: yield m


RULES = {
    # decision time from information known IN ADVANCE (listing data), never from the actual close:
    "sched24": "T = expected_expiration_time - 24h (scheduled expiry published at listing)",
    "open72": "T = open_time + 72h (fixed offset after listing)",
    # legacy, kept only as a reference: uses hindsight about when the market actually ended
    "close24_legacy": "T = min(close_time, settlement_ts) - 24h  [HINDSIGHT-BIASED; reference only]",
}
EARLY_CLOSE_GAP = 3 * 86400


def decision_time(m, rule):
    if rule == "sched24":
        e = m.get("expected_expiration_time")
        return iso(e) - HORIZON if e else None
    if rule == "open72":
        return iso(m["open_time"]) + 72 * 3600
    end = min(iso(m["close_time"]), iso(m["settlement_ts"]) if m.get("settlement_ts") else 9e12)
    return end - HORIZON


def build_dataset(api, series_list, per_series=8, min_volume=200, path=DS, rules=tuple(RULES)):
    c = sqlite3.connect(path)
    c.executescript("""CREATE TABLE IF NOT EXISTS pit2(ticker TEXT, rule TEXT, series TEXT, category TEXT, pred_ts REAL, close_ts REAL,
        exp_ts REAL, early_closed INT, f_ts REAL, yes_bid REAL, yes_ask REAL, f_prev_ts REAL, prev_mid REAL, outcome INT, volume REAL,
        built REAL, provenance TEXT, PRIMARY KEY(ticker, rule));
      CREATE TABLE IF NOT EXISTS exclusions(ticker TEXT, rule TEXT, reason TEXT, ts REAL, PRIMARY KEY(ticker, rule));
      CREATE TABLE IF NOT EXISTS mk_raw(ticker TEXT PRIMARY KEY, series TEXT, json TEXT);""")
    def excl(t, rule, why):
        c.execute("INSERT OR REPLACE INTO exclusions VALUES(?,?,?,?)", (t, rule, why, time.time()))
    seen = {}; n = 0; cat_of = dict(series_list) if isinstance(series_list, dict) else {}
    for m in iter_settled(api, series_list, per_series):
        s = m["ticker"].split("-")[0]; t = m["ticker"]
        if m.get("result") not in ("yes", "no"): excl(t, "*", f"result={m.get('result')!r} (not binary yes/no)"); continue
        if (fl(m.get("volume_fp")) or 0) < min_volume: excl(t, "*", f"volume {m.get('volume_fp')} < {min_volume}"); continue
        if seen.get(s, 0) >= per_series: excl(t, "*", f"per-series cap {per_series} reached"); continue
        seen[s] = seen.get(s, 0) + 1
        c.execute("INSERT OR REPLACE INTO mk_raw VALUES(?,?,?)", (t, s, json.dumps(m)))
        end = min(iso(m["close_time"]), iso(m["settlement_ts"]) if m.get("settlement_ts") else 9e12)
        exp = iso(m["expected_expiration_time"]) if m.get("expected_expiration_time") else None
        early = int(exp is not None and end < exp - EARLY_CLOSE_GAP)
        for rule in rules:
            T = decision_time(m, rule)
            if T is None: excl(t, rule, "no expected_expiration_time"); continue
            if end <= T + 3600: excl(t, rule, "market already closed/settled at (or within 1h after) decision time T: no decision possible"); continue
            if iso(m["open_time"]) > T - MOM_LOOKBACK - 3600: excl(t, rule, "opened < 25h before T (no momentum history)"); continue
            try:
                cs = api.get(f"/series/{s}/markets/{t}/candlesticks",
                             {"start_ts": int(T - MOM_LOOKBACK - 6 * 3600), "end_ts": int(T), "period_interval": 60})["candlesticks"]
            except Exception as e:
                excl(t, rule, f"candlestick fetch failed: {str(e)[:80]}"); continue
            pre = [x for x in cs if x["end_period_ts"] < T - AVAIL_BUFFER and fl(x["yes_bid"].get("close_dollars")) is not None]
            if not pre: excl(t, rule, "no candle ending before T-1h"); continue
            last = pre[-1]; yb, ya = fl(last["yes_bid"]["close_dollars"]), fl(last["yes_ask"]["close_dollars"])
            if not (yb and ya and 0 < yb < ya < 1): excl(t, rule, f"no two-sided quote at last pre-T candle (bid={yb}, ask={ya})"); continue
            old = [x for x in pre if x["end_period_ts"] < T - MOM_LOOKBACK - AVAIL_BUFFER]
            pm = pts = None
            if old:
                ob, oa = fl(old[-1]["yes_bid"]["close_dollars"]), fl(old[-1]["yes_ask"]["close_dollars"])
                if ob and oa and 0 < ob < oa < 1: pm = (ob + oa) / 2; pts = old[-1]["end_period_ts"]
            prov = {"features": {"endpoint": f"GET /series/{s}/markets/{t}/candlesticks?period_interval=60",
                                 "fields": "yes_bid.close_dollars, yes_ask.close_dollars", "ts_field": "end_period_ts",
                                 "ts_semantics": "EVENT time (inclusive end of hourly quote window); publication time not published by "
                                                 "Kalshi; fetched retrospectively -> availability at T NOT verifiable. Mitigation: end_period_ts < T-1h."},
                    "label": {"endpoint": "GET /markets?status=settled&series_ticker=..", "field": "result", "used_as": "label only"},
                    "decision_time": {"rule": rule, "definition": RULES[rule],
                                      "fields": {"sched24": "expected_expiration_time", "open72": "open_time",
                                                 "close24_legacy": "close_time/settlement_ts"}[rule],
                                      "known_in_advance": rule != "close24_legacy"},
                    "fetched_at": time.strftime("%FT%T%z")}
            c.execute("INSERT OR REPLACE INTO pit2 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (t, rule, s, cat_of.get(s), T, end, exp, early,
                      last["end_period_ts"], yb, ya, pts, pm, 1 if m["result"] == "yes" else 0, fl(m.get("volume_fp")), time.time(), json.dumps(prov)))
            c.execute("DELETE FROM exclusions WHERE ticker=? AND rule=?", (t, rule)); n += 1
        if n % 50 == 0: c.commit()
    c.commit(); return n


def load(path=DS, rule="sched24"):
    c = sqlite3.connect(path); c.row_factory = sqlite3.Row
    return [dict(r) for r in c.execute("SELECT * FROM pit2 WHERE rule=? AND yes_bid>0 AND yes_ask<1 AND yes_ask>yes_bid ORDER BY pred_ts", (rule,))]


def leakage_violations(rows):
    """Any feature timestamp >= prediction timestamp is look-ahead."""
    return [r["ticker"] for r in rows if r["f_ts"] >= r["pred_ts"] - AVAIL_BUFFER or (r["f_prev_ts"] is not None and r["f_prev_ts"] >= r["pred_ts"] - AVAIL_BUFFER)]


def split(rows, frac=0.6):
    """Time-based: train = earliest predictions, test = later. Also excludes from train any market whose
    OUTCOME was known after the first test prediction time (outcome-time purge)."""
    rows = sorted(rows, key=lambda r: r["pred_ts"]); k = int(len(rows) * frac)
    test = rows[k:]; t0 = test[0]["pred_ts"] if test else 9e12
    train = [r for r in rows[:k] if r["close_ts"] < t0]
    return train, test


def mid(r): return (r["yes_bid"] + r["yes_ask"]) / 2


def fit_bins(train, bins=10):
    """Empirical calibration map of market mid -> observed frequency (Laplace-smoothed), fit on TRAIN only."""
    agg = {}
    for r in train:
        b = min(bins - 1, int(mid(r) * bins)); a = agg.setdefault(b, [0, 0]); a[0] += r["outcome"]; a[1] += 1
    return {b: (a[0] + (b + .5) / bins * 2) / (a[1] + 2) for b, a in agg.items()}, bins


def model_p(r, fitted):
    m, bins = fitted; b = min(bins - 1, int(mid(r) * bins)); return m.get(b, mid(r))


STRATS = {
    # favourite-longshot: sell longshots (buy NO when mid<=0.10), buy favourites (YES when mid>=0.90)
    "flb": lambda r: "no" if mid(r) <= 0.10 else ("yes" if mid(r) >= 0.90 else None),
    "momentum": lambda r: None if r["prev_mid"] is None or abs(mid(r) - r["prev_mid"]) < 0.10 else ("yes" if mid(r) > r["prev_mid"] else "no"),
    "mean_reversion": lambda r: None if r["prev_mid"] is None or abs(mid(r) - r["prev_mid"]) < 0.10 else ("no" if mid(r) > r["prev_mid"] else "yes"),
    "calibrated_edge": None,  # filled at runtime: trade when train-fitted calibration map beats exec price after fees
}


def trade(r, side):
    px = r["yes_ask"] if side == "yes" else 1 - r["yes_bid"]
    f = fee(px, 1)
    win = (r["outcome"] == 1) == (side == "yes")
    return {"ticker": r["ticker"], "side": side, "price": px, "fee": f, "win": win, "pnl": (1 if win else 0) - px - f,
            "pred_ts": r["pred_ts"], "mid": mid(r), "outcome": r["outcome"], "series": r.get("series"),
            "early_closed": r.get("early_closed")}


def run(rows, reps=2000):
    assert not leakage_violations(rows), "look-ahead detected"
    train, test = split(rows); fitted = fit_bins(train)
    def ce(r):
        p = model_p(r, fitted)
        for side, px in (("yes", r["yes_ask"]), ("no", 1 - r["yes_bid"])):
            if ((p if side == "yes" else 1 - p) - px - fee(px, 1)) > 0.03: return side
        return None
    strats = dict(STRATS); strats["calibrated_edge"] = ce
    out = {"n_all": len(rows), "n_train": len(train), "n_test": len(test),
           "train_span": [min(r["pred_ts"] for r in train), max(r["pred_ts"] for r in train)] if train else None,
           "test_span": [min(r["pred_ts"] for r in test), max(r["pred_ts"] for r in test)] if test else None}
    def prob(rows_):
        return cal.compare([model_p(r, fitted) for r in rows_], [mid(r) for r in rows_], [r["outcome"] for r in rows_], reps,
                           clusters=[r.get("series") for r in rows_]) if rows_ else {"n": 0}
    out["probability_test"] = prob(test)
    out["probability_test_by_subset"] = {} if any(r.get("early_closed") is None for r in test) else \
        {"on_schedule": prob([r for r in test if r["early_closed"] == 0]), "early_closed": prob([r for r in test if r["early_closed"] == 1])}
    out["strategies"] = {}
    for name, fn in strats.items():
        for part, data in (("train", train), ("test", test)):
            tr_all = [trade(r, s) for r in data for s in [fn(r)] if s]
            subs = [("all", tr_all)]
            if all(t["early_closed"] is not None for t in tr_all):   # subset flag unknown for the archived original data
                subs += [("on_schedule", [t for t in tr_all if t["early_closed"] == 0]), ("early_closed", [t for t in tr_all if t["early_closed"] == 1])]
            for sub, tr in subs:
                pn = [t["pnl"] for t in tr]
                out["strategies"].setdefault(name, {})[part if sub == "all" else f"{part}:{sub}"] = {
                    "n": len(tr), "n_series": len({t["series"] for t in tr}), "hit_rate": (sum(t["win"] for t in tr) / len(tr)) if tr else None,
                    "net_pnl": sum(pn), "mean_pnl": (sum(pn) / len(pn)) if pn else None,
                    "mean_pnl_ci": cal.bootstrap(lambda i: sum(pn[j] for j in i) / len(i), len(pn), reps, clusters=[t["series"] for t in tr]),
                    "wins": sum(t["win"] for t in tr), "losses": sum(not t["win"] for t in tr), "trades": tr}
    out["_test_rows"] = test; out["_fitted"] = {str(k): v for k, v in fitted[0].items()}
    return out
