"""Read-only paper research view for Kalshi Hunter."""
import json
import os
import sqlite3
import sys
from pathlib import Path

from flask import Flask, render_template

PROJECT = Path(os.environ.get("KALSHI_HUNTER_DIR", Path(__file__).resolve().parents[1])).resolve()
DB_PATH = Path(os.environ.get("KALSHI_HUNTER_DB", PROJECT / "data" / "kalshi.db")).resolve()
sys.path.insert(0, str(PROJECT))
from kh import calibration, quant  # noqa: E402
from kh.fees import fee  # noqa: E402

app = Flask(__name__)


def readonly_connection(path=DB_PATH):
    """Open an existing SQLite database without permitting or making writes."""
    uri = Path(path).resolve(strict=True).as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def display_math(side, price, prob_yes, prob_lo, prob_hi, qty=10, multiplier=1.0):
    """Dollar amounts per contract. Price is the stored price of the selected side."""
    side = side.lower()
    if side not in ("yes", "no"):
        raise ValueError("side must be yes or no")
    per_contract_fee = fee(price, qty, multiplier) / qty
    p_win = prob_yes if side == "yes" else 1 - prob_yes
    p_worst = prob_lo if side == "yes" else 1 - prob_hi
    return {
        "p_win": p_win,
        "payout": 1 - price,
        "profit_if_win": 1 - price - per_contract_fee,
        "ev": quant.ev_per_contract(prob_yes, side, price, qty, multiplier),
        "ev_worst": quant.ev_per_contract(p_worst if side == "yes" else 1 - p_worst, side, price, qty, multiplier),
        "fee": per_contract_fee,
    }


def _json(value, default=None):
    try:
        return json.loads(value) if value else default
    except (TypeError, ValueError):
        return default


def load_page_data():
    conn = readonly_connection()
    try:
        approved = conn.execute("""SELECT a.*, f.prob_yes, f.prob_lo, f.prob_hi, f.qty, r.method,
            r.counter_evidence, r.contrarian, m.title, m.close_time, m.expected_expiration
            FROM alerts a LEFT JOIN forecasts f ON f.id=a.forecast_id
            LEFT JOIN research r ON r.id=a.research_id LEFT JOIN markets m ON m.ticker=a.ticker
            WHERE a.approved_by_auditor=1 ORDER BY a.ev_worst DESC, a.ts DESC""").fetchall()
        picks = []
        for row in approved:
            d = dict(row)
            if d["exec_price"] is None or d["prob_yes"] is None:
                continue
            payload = _json(d.get("payload"), {}) or {}
            math = display_math(d["side"], d["exec_price"], d["prob_yes"], d["prob_lo"], d["prob_hi"], d["qty"] or 10)
            d.update(math)
            d["depth"] = payload.get("depth_at_ask")
            d["title"] = d["title"] or d["ticker"]
            d["why_for"] = (d["method"] or "Sourced research passed the auditor.").split("\n")[0]
            d["why_against"] = (d["counter_evidence"] or "Auditor reviewed counter-evidence.").split("\n")[0]
            d["contracts"] = int(d["depth"] or d["qty"] or 0)
            d["settles"] = d["expected_expiration"] or d["close_time"] or "Settlement date unavailable"
            picks.append(d)

        # Submitted research that was not approved by the auditor (or did not reach an alert).
        rejected = conn.execute("""SELECT r.*, f.side, f.exec_price, f.prob_yes, f.prob_lo, f.prob_hi, f.qty,
            m.title, m.close_time, m.expected_expiration,
            (SELECT notes FROM research_audits x WHERE x.research_id=r.id ORDER BY x.id DESC LIMIT 1) audit_notes
            FROM research r LEFT JOIN forecasts f ON f.research_id=r.id
            LEFT JOIN markets m ON m.ticker=r.ticker
            WHERE NOT EXISTS (SELECT 1 FROM alerts a WHERE a.research_id=r.id AND a.approved_by_auditor=1)
            AND (f.id IS NOT NULL OR r.auditor!='')
            ORDER BY r.id DESC""").fetchall()
        passed = []
        for row in rejected:
            d = dict(row)
            notes = _json(d.get("audit_notes"), []) or []
            d["reason"] = (notes[0] if notes else d.get("auditor") or "Did not receive auditor approval.").split("\n")[0]
            d["title"] = d["title"] or d["ticker"]
            d["market_url"] = "https://kalshi.com/markets/" + d["ticker"].lower()
            passed.append(d)
        # Some submissions are rejected during source/format validation and never
        # become a research row or forecast. Keep those visible from the run log.
        for row in conn.execute("""SELECT ticker, outcome, note, payload FROM research_runs
                WHERE outcome='rejected' ORDER BY id DESC"""):
            d = dict(row)
            d["title"] = d["ticker"] or "Research submission"
            d["reason"] = (d.get("note") or "Submission did not pass research validation.").split("\n")[0]
            d["market_url"] = "https://kalshi.com/markets/" + str(d.get("ticker") or "").lower()
            passed.append(d)

        track = conn.execute("""SELECT f.prob_yes, f.side, COALESCE(z.outcome,f.outcome) outcome,
            COALESCE(z.pnl,f.pnl) pnl, fm.mid_p
            FROM forecasts f LEFT JOIN resolutions z ON z.forecast_id=f.id
            LEFT JOIN forecast_market fm ON fm.forecast_id=f.id
            WHERE substr(COALESCE(f.note,''),1,7)!='prereg_' AND
            (f.research_id IS NOT NULL OR f.note IN ('demo','routine research')) AND
            COALESCE(z.outcome,f.outcome) IN (0,1)""").fetchall()
        resolved = [dict(r) for r in track]
        wins = sum((r["side"] == "yes" and r["outcome"] == 1) or (r["side"] == "no" and r["outcome"] == 0) for r in resolved)
        paired = [r for r in resolved if r["mid_p"] is not None]
        stats = {
            "n": len(resolved),
            "win_rate": wins / len(resolved) if resolved else None,
            "pnl": sum(float(r["pnl"] or 0) for r in resolved),
            "brier_market": calibration.brier([r["mid_p"] for r in paired], [r["outcome"] for r in paired]),
            "brier_n": len(paired),
        }
        return {"picks": picks, "passed": passed, "stats": stats}
    finally:
        conn.close()


@app.get("/")
def index():
    return render_template("index.html", **load_page_data())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), debug=False)
