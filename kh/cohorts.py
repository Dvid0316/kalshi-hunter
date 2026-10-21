"""New product names: Track A = research; Track B = strategy.
Archived A/B/C/C2 nomenclature is preserved only in legacy documents.
Unknown records are quarantined rather than silently pooled.
"""
LABELS = {'research': 'Track A · Research forecasts', 'strategy': 'Track B · Strategy forecasts'}


def predicate(cohort, alias='f'):
    if cohort == 'strategy':
        return f"{alias}.note='prereg_flb_v1'"
    if cohort == 'research':
        return f"substr(COALESCE({alias}.note,''),1,7)!='prereg_' AND ({alias}.research_id IS NOT NULL OR {alias}.note IN ('demo','routine research'))"
    raise ValueError('Choose research or strategy explicitly')


def forecast_rows(c, cohort):
    # Deliberately omit legacy outcome/pnl fields from the projection.
    return c.execute(f"""SELECT f.id,f.ts,f.ticker,f.side,f.prob_yes,f.prob_lo,f.prob_hi,
        f.est_price,f.exec_price,f.qty,f.fee,f.ev,f.note,f.research_id,
        z.outcome,z.pnl,z.ts AS resolved_ts,m.mid_p,m.exec_implied_p,
        e.series_ticker AS series
        FROM forecasts f LEFT JOIN resolutions z ON z.forecast_id=f.id
        LEFT JOIN forecast_market m ON m.forecast_id=f.id
        LEFT JOIN markets k ON k.ticker=f.ticker LEFT JOIN events e ON e.event_ticker=k.event_ticker
        WHERE {predicate(cohort)} ORDER BY f.id""").fetchall()
