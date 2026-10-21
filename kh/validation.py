"""Offline, versioned reports. New A=research, B=strategy; historical A is separate."""
import json, time
from pathlib import Path
from . import perf, calibration as cal, integrity
from .cohorts import forecast_rows, LABELS
ROOT = Path(__file__).resolve().parents[1]


def cohort_report(c, cohort):
    rows = forecast_rows(c, cohort)
    out = perf.stats(c, cohort)
    paired = [r for r in rows if r['outcome'] is not None and r['mid_p'] is not None]
    out['label'] = LABELS[cohort]
    out['comparison'] = cal.compare([r['prob_yes'] for r in paired], [r['mid_p'] for r in paired],
        [r['outcome'] for r in paired], clusters=[r['series'] or r['ticker'].split('-')[0] for r in paired]) if paired else None
    out['fills'] = [dict(r) for r in rows]
    return out


# Compatibility functions for historical callers; never expose these old names in new UI.
def track_b(c):
    out = cohort_report(c, 'research')
    return dict(out, n_forecasts=out['forecasts_total'], n_resolved=out['resolved'],
                edges_at_forecast_time=out['fills'])


def track_c(c):
    out = cohort_report(c, 'research')
    return dict(out, n_fills=out['forecasts_total'], n_resolved=out['resolved'])


def track_c_flb(c):
    out = cohort_report(c, 'strategy')
    return dict(out, n_entries=out['forecasts_total'], n_resolved=out['resolved'])


def generate(c, output_dir=None):
    # No sealing, migration, plots, or writes to research/data directories.
    destination = Path(output_dir or ROOT / 'artifacts' / 'reports') / str(time.time_ns())
    destination.mkdir(parents=True, exist_ok=False)
    out = {'research': cohort_report(c, 'research'), 'strategy': cohort_report(c, 'strategy'),
           'historical': {'status': 'INCONCLUSIVE', 'note': 'Legacy Track A, not new research Track A. No demonstrated advantage.'},
           'integrity_problems': integrity.verify(c) + integrity.verify_checkpoints(c)}
    (destination/'report.json').write_text(json.dumps(out, indent=2))
    lines = ['Kalshi Hunter — offline paper snapshot', '', 'Historical backtests: INCONCLUSIVE. No demonstrated trading advantage.', '']
    for name in ('research','strategy'):
        r = out[name]
        lines += [r['label'], f"Forecasts: {r['forecasts_total']}; resolved: {r['resolved']}; realized paper P&L: {r['net_pnl'] if r['net_pnl'] is not None else 'unavailable'}", '']
    path = destination/'report.md';path.write_text('\n'.join(lines))
    return str(path), out
