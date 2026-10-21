# Kalshi Hunter: research and paper trading only

> ## STOP — read this first
> **This README describes the LEGACY cloud system** (the scanner that produced the snapshots), not the desktop
> application on this machine. **Do not run `start.sh` or `run.py` here** — they scan over the network and
> `start.sh` leaves a scanner + supervisor running, duplicating Grok's cloud jobs, which is forbidden on this box.
>
> **Desktop application** (what you launch): `./setup.sh` then `./launch.sh`. Docs: `docs/ARCHITECTURE.md`,
> `docs/TROUBLESHOOTING.md`, `docs/KNOWN_LIMITATIONS.md`, `CONTINUATION.md`. It is read-only, offline, holds no
> credentials and cannot place orders.
>
> The legacy text below is kept because it documents how the preserved evidence was produced.

There's no order code, no keys and no auth. `kh/api.py` asserts that only public GET paths are used, and a test checks this.

Ops (for the 30-minute routine):
- Start (idempotent, safe to rerun, uses flock and a PID check): `/workspace/kalshi-hunter/start.sh`
- Health: `.venv/bin/python run.py health` prints JSON `{last_ok_scan_age_s, healthy, errors_last_hour}`. Exit code 1 means unhealthy (no successful scan in 15 min); restart with `pkill -f supervise.sh; pkill -f "run.py loop"; ./start.sh`
- Logs: `data/service.log` (rotating, 5 MB × 5) and `data/stderr.log` (rotated at 5 MB). DB: `data/kalshi.db`. Dashboard: `dashboard/index.html`

Research (screened candidates only, capped at 3 per 24h):
1. `run.py claim` returns the next queued item, or null.
2. Do real web research and write `sub.json` with these fields:
   - `ticker`, `side`, `prob_yes`, `prob_lo`, `prob_hi`, `method`
   - `sources`: at least 2 primary URLs that load live
   - `contrarian`: `{findings, sources}`, a separate pass with its own sources
   - `secondhand`: `[{figure, via_url, original_source}]`
   - `usage`: `{tool_calls, web_searches, web_fetches, seconds, est_cost_usd}`
3. `run.py submit sub.json <queue_id>` validates the submission and rejects it if it's unsourced. It then records the paper forecast at the live ask and runs the auditor.

Alerts:
- `run.py pending-alerts` lists approved, unalerted alerts after re-checking the live book. Any alert whose price moved more than 2c gets revoked.
- After posting an alert, run `run.py mark-alerted <id>`.
- To be approved, an alert's EV after fees must be ≥ $0.03/contract at the unfavourable edge of the uncertainty band, with depth of at least 10 contracts, no ambiguous rules, and more than 1h until close.

Immutability: `forecasts`, `research`, `research_runs`, `resolutions` and `research_audits` are append-only (SQLite triggers). A correction must be a new row.
