import sqlite3, json, sys, datetime as dt
c = sqlite3.connect("data/backtest.db"); c.row_factory = sqlite3.Row
bad = []; n = 0
for r in c.execute("SELECT * FROM pit2"):
    n += 1; p = json.loads(r["provenance"]); T = r["pred_ts"]
    if not r["f_ts"] < T - 3600: bad.append((r["ticker"], r["rule"], "f_ts not < T-1h"))
    if r["f_prev_ts"] is not None and not r["f_prev_ts"] < T - 3600: bad.append((r["ticker"], r["rule"], "f_prev_ts not < T-1h"))
    if not r["close_ts"] > T + 3600: bad.append((r["ticker"], r["rule"], "market not open at T+1h"))
    if r["rule"] != "close24_legacy" and not p["decision_time"]["known_in_advance"]: bad.append((r["ticker"], r["rule"], "T not from advance info"))
    m = c.execute("SELECT json FROM mk_raw WHERE ticker=?", (r["ticker"],)).fetchone()
    if m and r["rule"] == "sched24":
        e = json.loads(m[0]).get("expected_expiration_time")
        if abs(dt.datetime.fromisoformat(e.replace("Z", "+00:00")).timestamp() - 86400 - T) > 1: bad.append((r["ticker"], r["rule"], "T != expected_expiration-24h"))
    if m and r["rule"] == "open72":
        o = json.loads(m[0])["open_time"]
        if abs(dt.datetime.fromisoformat(o.replace("Z", "+00:00")).timestamp() + 72 * 3600 - T) > 1: bad.append((r["ticker"], r["rule"], "T != open+72h"))
by = dict(c.execute("SELECT rule, COUNT(*) FROM pit2 GROUP BY rule").fetchall())
print(f"rows checked: {n} {by}\nviolations: {len(bad)}"); [print(b) for b in bad[:50]]
print("ASSUMED (not verifiable): candle with end_period_ts=e was queryable by e+3600s and has not been revised since.")
