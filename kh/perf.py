import time, json
from .fees import fee
from . import quant
from .accounting import settlement_pnl, amount
from .cohorts import forecast_rows


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
            pnl = float(settlement_pnl(r["side"], r["qty"], r["exec_price"], r["fee"], outcome))
            c.execute("INSERT INTO resolutions(ts,forecast_id,outcome,pnl) VALUES(?,?,?,?)",
                      (time.time(), r["id"], outcome, pnl)); n += 1
    c.commit(); return n


def stats(c, cohort="research"):
    """One cohort only. Reconcile stored settlement against accounting inputs."""
    from . import calibration as cal
    rows = forecast_rows(c, cohort)
    done = [r for r in rows if r['outcome'] is not None]
    discrepancies = []
    pnl = []
    for r in done:
        expected = settlement_pnl(r['side'], r['qty'], r['exec_price'], r['fee'], r['outcome'])
        if r['pnl'] is None or abs(amount(r['pnl']) - expected) > amount('0.00000001'):
            discrepancies.append(r['id'])
        pnl.append(expected)
    sl = [r['exec_price']-r['est_price'] for r in rows if r['est_price'] is not None]
    paired = [r for r in done if r['mid_p'] is not None]
    out = dict(cohort=cohort, forecasts_total=len(rows), open=len(rows)-len(done), resolved=len(done),
               net_pnl=float(sum(pnl)) if done and not discrepancies else None,
               accounting_discrepancies=discrepancies,
               brier=cal.brier([r['prob_yes'] for r in done], [r['outcome'] for r in done]),
               brier_market=cal.brier([r['mid_p'] for r in paired], [r['outcome'] for r in paired]),
               brier_paired=cal.brier([r['prob_yes'] for r in paired], [r['outcome'] for r in paired]),
               n_brier=len(done), n_brier_paired=len(paired),
               mean_slippage=sum(sl)/len(sl) if sl else None,
               note=f"n={len(done)} resolved; too small to claim an advantage. Paper only.")
    return out
