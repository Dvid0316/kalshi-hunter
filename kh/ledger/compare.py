"""Compare the owner's own decisions with Grok's recorded research. Descriptive only.

Joins on exact ticker. Actual (ledger) and paper (research DB) numbers are returned in separate
fields and are never added together. Nothing here judges who was right; a market that has not
resolved has no winner.
"""
from __future__ import annotations

from .engine import Report


def compare(report: Report, forecasts: list[dict], journal: list[dict] | None = None) -> list[dict]:
    """``forecasts``: dicts with ticker, cohort, cohort_label, side, prob_yes, ts, exec_price(float), id."""
    journal = journal or []
    by_ticker: dict[str, list[dict]] = {}
    for f in forecasts:
        by_ticker.setdefault(f['ticker'], []).append(f)
    tickers = sorted(set(by_ticker) | set(report.markets))
    rows = []
    for t in tickers:
        m = report.markets.get(t)
        fs = by_ticker.get(t, [])
        if not fs and not any(j.get('ticker') == t for j in journal):
            continue                      # user-only market with no research and no note: nothing to compare
        mine = [j for j in journal if j.get('ticker') == t and j.get('my_prob') not in (None, '')]
        research: list[dict] = []
        row = dict(ticker=t, traded=m is not None and (m.opened_qty > 0 or m.settled_ts is not None),
                   research=research, journal_estimates=[dict(id=j['id'], my_prob=j['my_prob'], title=j['title']) for j in mine])
        if m is not None:
            row.update(actual_status=m.status, actual_side=m.side, actual_qty=m.qty, actual_avg_entry=m.avg_entry_price,
                       actual_realized=m.realized, actual_incomplete=m.incomplete,
                       first_fill_ts=m.first_ts, result=m.result)
        for f in fs:
            rel = 'research_only'
            lag = None
            if m is not None and m.first_ts is not None:
                first_side = _first_side(m, report)
                rel = 'same_side' if first_side == f['side'] else ('opposite_side' if first_side else 'research_only')
                lag = m.first_ts - f['ts']
            research.append(dict(
                id=f['id'], cohort=f['cohort'], cohort_label=f['cohort_label'], side=f['side'], prob_yes=f['prob_yes'],
                ts=f['ts'], paper_price=f.get('exec_price'), relation=rel, my_entry_after_seconds=lag,
                outcome=f.get('outcome'), paper_pnl_text=f.get('pnl_text')))
        rows.append(row)
    return rows


def _first_side(m, report: Report):
    """Side of the earliest opening trade in this market (current side, else from realised history)."""
    if m.side:
        return m.side
    evs = [e for e in report.events if e.ticker == m.ticker]
    return evs[0].side if evs else None
