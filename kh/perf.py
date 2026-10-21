import time, json
from .fees import fee
from . import quant


def record_forecast(api, c, ticker, side, prob_yes, lo, hi, research_id=None, qty=10, note=""):
    """Paper forecast: hypothetical taker fill at the CURRENT executable price (walks the live book)."""
    ob = api.orderbook(ticker, depth=20)
    avg, got = quant.executable_buy(ob, side, qty)
    top = quant.top_of_book(ob)
    est = top["yes_ask"] if side == "yes" else top["no_ask"]
    if avg is None: raise RuntimeError("no executable liquidity")
    f = fee(avg, got, 1.0)
    ev = quant.ev_per_contract(prob_yes, side, avg, got)
    now = time.time()
    cur = c.execute("""INSERT INTO forecasts(ts,ticker,side,prob_yes,prob_lo,prob_hi,est_price,exec_price,exec_ts,qty,fee,ev,
        research_id,note) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (now, ticker, side, prob_yes, lo, hi, est, round(avg, 4), now, got, f, ev, research_id, note))
    c.execute("INSERT INTO slippage(ts,ticker,side,est_price,exec_price,diff) VALUES(?,?,?,?,?,?)",
              (now, ticker, side, est, avg, avg - (est or avg)))
    record_market(c, cur.lastrowid, side, prob_yes, top, avg, got, f)
    c.commit()
    return cur.lastrowid, avg, got, f, ev, top


def market_implied(side, top, avg, got, f):
    """mid_p: (yes_bid+yes_ask)/2. exec_implied_p: the P(YES) at which our actual taker fill breaks even after spread
    (we pay the ask, walked by depth) and fees: YES side -> avg+fee/q ; NO side -> 1-(avg+fee/q)."""
    yb, ya = top["yes_bid"], top["yes_ask"]
    mid = (yb + ya) / 2 if yb is not None and ya is not None else None
    be = avg + f / got
    return mid, (be if side == "yes" else 1 - be)


def record_market(c, fid, side, prob_yes, top, avg, got, f, note=""):
    mid, ex = market_implied(side, top, avg, got, f)
    c.execute("""INSERT INTO forecast_market(ts,forecast_id,yes_bid,yes_ask,mid_p,exec_implied_p,edge_vs_mid,edge_vs_exec,note)
                 VALUES(?,?,?,?,?,?,?,?,?)""", (time.time(), fid, top["yes_bid"], top["yes_ask"], mid, ex,
              None if mid is None else (prob_yes - mid) * (1 if side == "yes" else -1),
              (prob_yes - ex) * (1 if side == "yes" else -1), note))


def resolve(api, c):
    n = 0
    for r in c.execute("SELECT f.* FROM forecasts f LEFT JOIN resolutions z ON z.forecast_id=f.id WHERE z.id IS NULL").fetchall():
        m = api.market(r["ticker"])
        res = m.get("result")
        if res in ("yes", "no"):
            outcome = 1 if res == "yes" else 0
            win = (outcome == 1) == (r["side"] == "yes")
            pnl = r["qty"] * ((1.0 if win else 0.0) - r["exec_price"]) - r["fee"]
            c.execute("INSERT INTO resolutions(ts,forecast_id,outcome,pnl) VALUES(?,?,?,?)",
                      (time.time(), r["id"], outcome, pnl)); n += 1
    c.commit(); return n


def stats(c):
    rows = c.execute("SELECT f.*, z.outcome AS outcome, z.pnl AS pnl FROM forecasts f JOIN resolutions z ON z.forecast_id=f.id").fetchall()
    total = c.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0]
    out = {"forecasts_total": total, "open": total - len(rows), "resolved": len(rows),
           "note": f"n={len(rows)} resolved forecasts: far too small to conclude anything about calibration or edge"}
    if rows:
        out["brier"] = sum(quant.brier(r["prob_yes"], r["outcome"]) for r in rows) / len(rows)
        # market benchmark: implied YES prob at fill time
        mk = [(r["exec_price"] if r["side"] == "yes" else 1 - r["exec_price"]) for r in rows]
        out["brier_market"] = sum(quant.brier(p, r["outcome"]) for p, r in zip(mk, rows)) / len(rows)
        out["net_pnl"] = sum(r["pnl"] for r in rows)
        bins = {}
        for r in rows:
            b = min(9, int(r["prob_yes"] * 10)); bins.setdefault(b, []).append(r["outcome"])
        out["calibration"] = {f"{b/10:.1f}-{(b+1)/10:.1f}": (len(v), sum(v) / len(v)) for b, v in sorted(bins.items())}
    out["mean_slippage"] = c.execute("SELECT AVG(diff) FROM slippage").fetchone()[0]
    return out
