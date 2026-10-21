import html, json, time, datetime as dt, os
from . import perf
OUT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard", "index.html")


def ts(t):
    return dt.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M CT") if t else ""


def table(rows, cols):
    h = "<tr>" + "".join(f"<th>{c}</th>" for c in cols) + "</tr>"
    for r in rows:
        h += "<tr>" + "".join(f"<td>{html.escape(str(x))}</td>" for x in r) + "</tr>"
    return f"<table>{h}</table>"


def render(c):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    scans = [(ts(r["started"]), r["status"], r["events"], r["markets"], r["candidates"],
              round((r["finished"] or r["started"]) - r["started"], 1)) for r in
             c.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 12")]
    day = time.time() - 86400
    api = c.execute("SELECT COUNT(*), SUM(status!=200) FROM api_log WHERE ts>?", (day,)).fetchone()
    cands = []
    for r in c.execute("""SELECT k.*, a.status AS astatus, a.audit AS aaudit FROM candidates k LEFT JOIN candidate_audits a
                          ON a.id=(SELECT MAX(id) FROM candidate_audits WHERE candidate_id=k.id) ORDER BY k.id DESC LIMIT 40"""):
        a = json.loads(r["aaudit"] or r["audit"] or "{}")
        cands.append((ts(r["ts"]), r["astatus"] or r["status"], r["kind"], r["event_ticker"], r["edge"], a.get("reverified_edge", ""),
                      "; ".join(a.get("notes", []))[:300]))
    fc = [(ts(r["ts"]), r["ticker"], r["side"], r["prob_yes"], f"{r['prob_lo']}-{r['prob_hi']}", r["exec_price"],
           r["qty"], r["fee"], round(r["ev"], 4), "" if r["outcome"] is None else r["outcome"], r["pnl"],
           " ".join(json.loads(r["sources"] or "[]")), r["secondhand"] or "") for r in
          c.execute("""SELECT f.*, z.outcome AS outcome, z.pnl AS pnl, rs.sources, rs.secondhand FROM forecasts f
                       LEFT JOIN resolutions z ON z.forecast_id=f.id LEFT JOIN research rs ON rs.id=f.research_id ORDER BY f.id DESC""")]
    errs = [(ts(r["ts"]), r["where_"], r["msg"][:200]) for r in c.execute("SELECT * FROM errors ORDER BY id DESC LIMIT 15")]
    st = perf.stats(c)
    last = c.execute("SELECT * FROM scans WHERE status='ok' ORDER BY id DESC LIMIT 1").fetchone()
    starts = c.execute("SELECT COUNT(*), MAX(ts) FROM service_starts").fetchone()
    a24 = c.execute("SELECT SUM(status=200), SUM(status!=200), SUM(status=429) FROM api_log WHERE ts>?", (day,)).fetchone()
    rel = [("Last successful scan", ts(last["finished"]) if last else "never"),
           ("Last scan age (min)", round((time.time() - last["finished"]) / 60, 1) if last else ""),
           ("Tradable markets last cycle (status active AND >=1 live bid/ask level)", last["tradable"] if last else ""),
           ("All markets / events scanned last cycle", f"{last['markets']} / {last['events']}" if last else ""),
           ("API ok / failed last cycle", f"{last['api_ok']} / {last['api_fail']}" if last else ""),
           ("API ok / failed (of which 429) last 24h", f"{a24[0] or 0} / {a24[1] or 0} ({a24[2] or 0})"),
           ("Scanner uptime since last (re)start", f"{(time.time() - starts[1]) / 3600:.1f} h" if starts[1] else ""),
           ("Service starts recorded (1 = no restarts)", starts[0])]
    rr = [(ts(r["ts"]), r["ticker"], r["stage"], r["outcome"], r["tool_calls"], r["web_searches"], r["web_fetches"],
           f"{r['urls_verified']}/{(r['urls_verified'] or 0)+(r['urls_failed'] or 0)}", r["seconds"], r["est_cost_usd"], (r["note"] or "")[:200])
          for r in c.execute("SELECT * FROM research_runs ORDER BY id DESC LIMIT 30")]
    cost = c.execute("SELECT COUNT(*), SUM(est_cost_usd), SUM(tool_calls) FROM research_runs WHERE ts>?", (time.time()-86400,)).fetchone()
    rq = [(ts(r["ts"]), r["ticker"], r["reason"], r["status"], r["note"] or "") for r in c.execute("SELECT * FROM research_queue ORDER BY id DESC LIMIT 20")]
    al = [(ts(r["ts"]), r["ticker"], r["side"], r["exec_price"], round(r["ev"],4), round(r["ev_worst"],4), r["approved_by_auditor"], ts(r["alerted_at"]))
          for r in c.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT 20")]
    vj = os.path.join(os.path.dirname(OUT), "..", "data", "validation_v2.json")
    V = json.load(open(vj)) if os.path.exists(vj) else {}
    A, B, C = V.get("A", {}), V.get("B", {}), V.get("C", {})
    arows = [(rs, k, p, d["n"], d["n_series"], d["hit_rate"] and round(d["hit_rate"], 3), d["wins"], d["losses"], round(d["net_pnl"], 2),
              d["mean_pnl"] and round(d["mean_pnl"], 4), str(d["mean_pnl_ci"])) for rs, R in A.get("rulesets", {}).items()
             for k, st in R.get("strategies", {}).items() for p, d in st.items() if ":" not in p or not rs.startswith("original")]
    pt = A.get("rulesets", {}).get("corrected:sched24", {}).get("probability_test", {})
    trackA = (f"<p>sched24 test: Brier calibration map {pt.get('ours',{}).get('brier')} "
              f"vs market mid {pt.get('market',{}).get('brier')}; diff CI {pt.get('brier_diff_ci')}</p>" +
              table(arows, ["ruleset","strategy","part:subset","n","series","hit","wins","losses","net P&L $","mean/trade","cluster 95% CI"]) +
              "<p>close24_legacy and original use hindsight about close timing (reference only). flb: 0 losses observed, so tail risk is uncaptured (see report). Caveats: top-of-book candles only (no depth), 1-lot fills, availability time not verifiable (1h buffer), correlated markets.</p>")
    trackB = f"<p>forecasts {B.get('n_forecasts')}, resolved {B.get('n_resolved')} &mdash; n far too small to conclude anything.</p>" + table(
        [tuple(e.values()) for e in B.get("edges_at_forecast_time", [])], ["id","ticker","side","our p","mid p","exec-implied p","edge vs mid","edge vs exec","outcome"])
    trackC = (f"<p>fills {C.get('n_fills')}, open {C.get('n_open')}, resolved {C.get('n_resolved')}, wins {C.get('wins')}, losses {C.get('losses')}, "
              f"net P&L {C.get('net_pnl')}, slippage n={C.get('slippage_n')} mean {C.get('slippage_mean')}</p>")
    body = f"""<html><head><meta charset=utf-8><meta http-equiv=refresh content=60><title>Kalshi Hunter</title>
<style>body{{font-family:sans-serif;margin:20px}}table{{border-collapse:collapse;font-size:12px;margin-bottom:18px}}
td,th{{border:1px solid #ccc;padding:3px 6px}}h2{{margin-top:24px}}.w{{background:#fff3cd;padding:8px}}</style></head><body>
<h1>Kalshi Hunter (research and paper trading only)</h1>
<p class=w>No real orders. Unauthenticated public data. There is no out-of-sample evidence of an edge until enough paper forecasts resolve.</p>
<p>Generated {ts(time.time())}. API calls last 24h: {api[0]} (non-200: {api[1] or 0}).</p>
<h2>Validation: A) Mechanical backtest (historical)</h2>{trackA}
<h2>Validation: B) Forecast calibration (researched forecasts vs market)</h2>{trackB}
<h2>Validation: C) Forward paper trading (prospective)</h2>{trackC}
<p><b>Advantage over market: NOT demonstrated.</b> Tracks are never pooled. Integrity problems: {V.get('integrity_problems')}</p>
<h2>Reliability</h2>{table(rel, ["metric","value"])}
<h2>Performance (append-only; every forecast counted, incl. rejected-by-auditor)</h2><pre>{html.escape(json.dumps(st, indent=1))}</pre>
<h2>Alerts</h2>{table(al, ["time","ticker","side","fill","EV","worst-case EV","approved","alerted"])}
<h2>Research queue</h2>{table(rq, ["time","ticker","why screened","status","note"])}
<h2>Research runs (last 24h: {cost[0]} runs, est cost ${cost[1] or 0:.2f}, tool calls {cost[2] or 0})</h2>{table(rr, ["time","ticker","stage","outcome","tool calls","searches","fetches","URLs ok","secs","est $","note"])}
<h2>Paper forecasts</h2>{table(fc, ["time","ticker","side","p(yes)","band","fill","qty","fee $","EV/contract","outcome","P&L $","sources","second-hand figures"])}
<h2>Structural candidates (screened, then audited)</h2>{table(cands, ["time","status","kind","event","screen edge","re-verified edge","auditor notes"])}
<h2>Scans</h2>{table(scans, ["start","status","events","markets","candidates","secs"])}
<h2>Errors</h2>{table(errs, ["time","where","msg"])}
</body></html>"""
    open(OUT + ".tmp", "w").write(body); os.replace(OUT + ".tmp", OUT)
    return OUT
