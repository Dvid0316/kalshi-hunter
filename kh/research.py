"""Research step for SCREENED candidates only.

Flow: service enqueues (capped per day) -> the 30-min routine's agent claims an item, does real web research,
writes a JSON submission -> submit() validates every source URL live, requires a separate contrarian pass,
requires second-hand figures to name the original source, records the paper forecast at the live executable
price, runs the auditor and creates an alert row only if the edge survives the worst case of the uncertainty band.
Anything unsourced is rejected. No estimate is ever generated here; estimates come only from sourced submissions.
"""
import json, time, requests
from . import perf, auditor
from .fees import fee

DAILY_CAP = 3
ALERT_MIN_WORST_EV = 0.03      # $/contract after fees at the unfavourable edge of the band
MIN_PRIMARY_SOURCES = 2
MAX_BAND_WIDTH = 0.30


def enqueue(c, now=None):
    """Queue up to DAILY_CAP screened candidates per rolling 24h. Screening = (a) structural candidates that the
    auditor re-verified, or (b) liquid politics/econ markets with a >=10pt 24h move (price may lag news)."""
    now = now or time.time()
    used = c.execute("SELECT COUNT(*) FROM research_queue WHERE ts>?", (now - 86400,)).fetchone()[0]
    room = DAILY_CAP - used; added = []
    if room <= 0: return added
    picks = []
    for r in c.execute("""SELECT k.detail FROM candidates k JOIN candidate_audits a ON a.candidate_id=k.id
                             WHERE a.status='alert' AND a.ts>? ORDER BY k.edge DESC LIMIT 5""", (now - 86400,)):
        for t, _, _ in json.loads(r[0])["legs"][:1]: picks.append((t, "structural candidate passed re-verification"))
    sid = c.execute("SELECT MAX(id) FROM scans WHERE status='ok'").fetchone()[0]
    if sid:
        q = """SELECT s.ticker, s.yes_bid, s.yes_ask, s.volume_24h, (SELECT p.yes_ask FROM snapshots p WHERE p.ticker=s.ticker
               AND p.ts < s.ts-86000 ORDER BY p.ts DESC LIMIT 1) prev FROM snapshots s JOIN markets m USING(ticker)
               JOIN events e USING(event_ticker) WHERE s.scan_id=? AND e.category IN ('Politics','Elections','Economics')
               AND s.volume_24h>=5000 AND s.yes_ask BETWEEN 0.05 AND 0.95 AND s.yes_ask-s.yes_bid<=0.03"""
        for t, yb, ya, v, prev in c.execute(q, (sid,)).fetchall():
            if prev is not None and abs(ya - prev) >= 0.10:
                picks.append((t, f"24h move {prev:.2f}->{ya:.2f}, vol24h {v:.0f}"))
    for t, why in picks:
        if len(added) >= room: break
        if c.execute("SELECT 1 FROM research_queue WHERE ticker=? AND ts>?", (t, now - 7 * 86400)).fetchone(): continue
        c.execute("INSERT INTO research_queue(ts,ticker,reason) VALUES(?,?,?)", (now, t, why)); added.append(t)
    c.commit(); return added


def claim(c):
    r = c.execute("SELECT * FROM research_queue WHERE status='queued' ORDER BY id LIMIT 1").fetchone()
    if r: c.execute("UPDATE research_queue SET status='claimed', claimed_at=? WHERE id=?", (time.time(), r["id"])); c.commit()
    return dict(r) if r else None


def verify_url(url, fetch=None):
    fetch = fetch or (lambda u: requests.get(u, timeout=20, headers={"User-Agent": "Mozilla/5.0 kalshi-hunter-research"}).status_code)
    try: return fetch(url) < 400
    except Exception: return False


def validate(sub, fetch=None):
    """Returns (ok, errors, verified_count, failed_count)."""
    errs = []
    for k in ("ticker", "side", "prob_yes", "prob_lo", "prob_hi", "method", "sources", "contrarian"):
        if k not in sub: errs.append(f"missing {k}")
    if errs: return False, errs, 0, 0
    p, lo, hi = sub["prob_yes"], sub["prob_lo"], sub["prob_hi"]
    if not (0 < lo <= p <= hi < 1): errs.append("need 0<lo<=p<=hi<1")
    if hi - lo > MAX_BAND_WIDTH: errs.append("uncertainty band too wide to support any edge")
    if sub["side"] not in ("yes", "no"): errs.append("side must be yes/no")
    con = sub["contrarian"]
    if not con.get("findings") or not con.get("sources"): errs.append("contrarian pass needs findings and its own sources")
    for s in sub.get("secondhand", []):
        if not s.get("figure") or not s.get("via_url") or not s.get("original_source"):
            errs.append(f"second-hand figure must name figure, via_url and original_source: {s}")
    prim = [verify_url(u, fetch) for u in sub["sources"]]
    cons = [verify_url(u, fetch) for u in (con.get("sources") or [])]
    ok_n = sum(prim) + sum(cons); bad_n = len(prim) + len(cons) - ok_n
    if sum(prim) < MIN_PRIMARY_SOURCES: errs.append(f"fewer than {MIN_PRIMARY_SOURCES} primary sources could be verified live")
    if con.get("sources") and not any(cons): errs.append("no contrarian source could be verified live")
    return not errs, errs, ok_n, bad_n


def submit(api, c, sub, queue_id=None, usage=None, fetch=None):
    usage = usage or {}
    ok, errs, nv, nf = validate(sub, fetch)
    run = dict(tool_calls=usage.get("tool_calls"), web_searches=usage.get("web_searches"), web_fetches=usage.get("web_fetches"),
               seconds=usage.get("seconds"), est_cost_usd=usage.get("est_cost_usd"))
    def log(stage, outcome, note):
        c.execute("""INSERT INTO research_runs(ts,queue_id,ticker,stage,tool_calls,web_searches,web_fetches,urls_verified,
            urls_failed,seconds,est_cost_usd,outcome,note,payload) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (time.time(), queue_id, sub.get("ticker"), stage, run["tool_calls"], run["web_searches"], run["web_fetches"],
             nv, nf, run["seconds"], run["est_cost_usd"], outcome, note, json.dumps(sub)))
    if not ok:
        log("validate", "rejected", "; ".join(errs))
        if queue_id: c.execute("UPDATE research_queue SET status='rejected', done_at=?, note=? WHERE id=?", (time.time(), "; ".join(errs), queue_id))
        c.commit(); return {"status": "rejected", "errors": errs}
    cur = c.execute("""INSERT INTO research(ts,ticker,prob_yes,prob_lo,prob_hi,method,sources,counter_evidence,auditor,author,
        secondhand,stage,queue_id,contrarian) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (time.time(), sub["ticker"], sub["prob_yes"], sub["prob_lo"], sub["prob_hi"], sub["method"], json.dumps(sub["sources"]),
         sub["contrarian"]["findings"], "", sub.get("author", "routine"), json.dumps(sub.get("secondhand", [])), "primary+contrarian",
         queue_id, json.dumps(sub["contrarian"])))
    rid = cur.lastrowid
    m = api.market(sub["ticker"])
    fid, avg, got, f, ev, top = perf.record_forecast(api, c, sub["ticker"], sub["side"], sub["prob_yes"], sub["prob_lo"],
                                                     sub["prob_hi"], rid, qty=10, note="routine research")
    depth = top["no_ask_size"] if sub["side"] == "no" else top["yes_ask_size"]
    amb = bool(auditor.AMBIG.search((m.get("rules_primary") or "") + " " + (m.get("rules_secondary") or "")))
    aok, notes, evw = auditor.audit_model(sub["prob_yes"], sub["prob_lo"], sub["prob_hi"], sub["side"], avg,
                                          auditor.hours_to_close(m.get("close_time")), depth, amb, qty=got)
    if sub.get("secondhand"): notes.append("relies on second-hand figures: " + "; ".join(s["figure"] for s in sub["secondhand"]))
    if evw < ALERT_MIN_WORST_EV and not any("worst-case" in n for n in notes):
        notes.append(f"worst-case EV {evw:+.3f} below alert bar {ALERT_MIN_WORST_EV}")
    approved = int(aok and evw >= ALERT_MIN_WORST_EV)
    c.execute("INSERT INTO research_audits(ts,research_id,notes) VALUES(?,?,?)", (time.time(), rid, json.dumps(notes)))
    payload = {"ticker": sub["ticker"], "event_ticker": m.get("event_ticker"), "side": sub["side"], "exec_price": round(avg, 4),
               "ts": time.strftime("%F %T %Z"), "prob": [sub["prob_lo"], sub["prob_yes"], sub["prob_hi"]],
               "ev_after_fees": round(ev, 4), "ev_worst": round(evw, 4), "depth_at_ask": depth, "sources": sub["sources"],
               "secondhand": sub.get("secondhand", []), "contrarian": sub["contrarian"], "auditor_notes": notes,
               "rules": m.get("rules_primary")}
    if approved:
        c.execute("""INSERT INTO alerts(ts,ticker,side,research_id,forecast_id,exec_price,ev,ev_worst,payload,approved_by_auditor)
            VALUES(?,?,?,?,?,?,?,?,?,1)""", (time.time(), sub["ticker"], sub["side"], rid, fid, avg, ev, evw, json.dumps(payload)))
    log("submit", "approved" if approved else "no_edge", "; ".join(notes))
    if queue_id: c.execute("UPDATE research_queue SET status=?, done_at=? WHERE id=?", ("approved" if approved else "done", time.time(), queue_id))
    c.commit()
    return {"status": "approved" if approved else "no_edge", "research_id": rid, "forecast_id": fid, "payload": payload}


def pending_alerts(api, c, max_drift=0.02):
    """Unalerted approved alerts, re-verified against the live book right before the routine posts them."""
    from . import quant
    out = []
    for a in c.execute("SELECT * FROM alerts WHERE approved_by_auditor=1 AND alerted_at IS NULL").fetchall():
        avg, got = quant.executable_buy(api.orderbook(a["ticker"], 20), a["side"], 10)
        if avg is None or avg - a["exec_price"] > max_drift:
            c.execute("UPDATE alerts SET approved_by_auditor=0 WHERE id=?", (a["id"],)); continue
        p = json.loads(a["payload"]); p["reverified_price"] = round(avg, 4); p["alert_id"] = a["id"]; out.append(p)
    c.commit(); return out


def mark_alerted(c, alert_id):
    c.execute("UPDATE alerts SET alerted_at=? WHERE id=? AND alerted_at IS NULL", (time.time(), alert_id)); c.commit()
