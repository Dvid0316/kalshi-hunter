"""Contrarian / auditor checks. Re-verifies prices from the live orderbook before anything is flagged as an alert."""
import json, time, re, datetime as dt
from . import quant
from .fees import fee

AMBIG = re.compile(r"sole discretion|may be determined|in the event of ambiguity|at kalshi's discretion|unclear|"
                   r"reasonable judgment|if .* cannot be determined", re.I)
MIN_QTY = 10          # depth required at the quoted price, per leg
ALERT_EDGE = 0.02     # $ per set after fees, after re-verification
MIN_HOURS_TO_CLOSE = 1


def hours_to_close(close_time):
    try:
        t = dt.datetime.fromisoformat(close_time.replace("Z", "+00:00"))
        return (t - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600
    except Exception:
        return None


def audit_structural(api, c, cand_row, mult=1.0):
    d = json.loads(cand_row["detail"]); notes = []; ok = True
    legs_exec = []; total = 0.0
    for t, side, quoted in d["legs"]:
        ob = api.orderbook(t, depth=20)
        avg, got = quant.executable_buy(ob, side, MIN_QTY)
        m = c.execute("SELECT * FROM markets WHERE ticker=?", (t,)).fetchone()
        if got < MIN_QTY:
            ok = False; notes.append(f"{t} {side}: only {got} contracts available (<{MIN_QTY})")
        if avg is None:
            ok = False; continue
        legs_exec.append((t, side, quoted, round(avg, 4)))
        total += avg + fee(avg, MIN_QTY, mult) / MIN_QTY
        c.execute("INSERT INTO slippage(ts,ticker,side,est_price,exec_price,diff) VALUES(?,?,?,?,?,?)",
                  (time.time(), t, side, quoted, avg, avg - quoted))
        if m is not None:
            h = hours_to_close(m["close_time"])
            if h is not None and h < MIN_HOURS_TO_CLOSE: ok = False; notes.append(f"{t} closes in {h:.2f}h")
            if AMBIG.search((m["rules_primary"] or "") + " " + (m["rules_secondary"] or "")):
                notes.append(f"{t}: rules contain discretionary/ambiguous language - manual read required")
    edge = d["payout_min"] - total
    if d.get("needs_exhaustive"):
        notes.append("Buy-all-YES only pays if exactly one outcome resolves YES; exhaustiveness (incl. 'other'/no-winner/"
                     "cancellation states) NOT verified -> cannot be called riskless")
        ok = False
    if edge > 0.25:
        ok = False; notes.append("edge implausibly large for a structural arb; treat as probable data/model error until a human reads the rules")
    if edge < ALERT_EDGE: ok = False; notes.append(f"re-verified edge {edge:.4f} < {ALERT_EDGE}")
    audit = {"ts": time.time(), "legs_exec": legs_exec, "reverified_edge": round(edge, 4), "qty": MIN_QTY, "notes": notes}
    status = "alert" if ok else "rejected"
    c.execute("INSERT INTO candidate_audits(ts,candidate_id,status,audit) VALUES(?,?,?,?)",
              (time.time(), cand_row["id"], status, json.dumps(audit))); c.commit()
    return status, audit


def audit_model(prob_yes, lo, hi, side, exec_price, h_close, depth, ambiguous, qty=10):
    """Rejects model-based edges that aren't robust to the researcher's own uncertainty band."""
    notes = []
    worst = lo if side == "yes" else 1 - hi        # worst-case win prob within band
    ev_worst = worst - exec_price - fee(exec_price, qty) / qty  # same order size as the paper fill
    if ev_worst <= 0: notes.append(f"edge disappears at edge of uncertainty band (worst-case EV {ev_worst:+.3f})")
    if depth < MIN_QTY: notes.append(f"thin book: {depth} contracts at best ask")
    if h_close is not None and h_close < MIN_HOURS_TO_CLOSE: notes.append("closes within 1h; price may be stale")
    if ambiguous: notes.append("settlement language ambiguous")
    return (len(notes) == 0), notes, ev_worst
