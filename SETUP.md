# SETUP: Kalshi Hunter (research and paper trading only, no real orders)

> ## STOP — read this first
> **This file describes the LEGACY cloud scanner (the backend that produced the snapshots), not the desktop
> application on this machine.**
>
> - **Do not run `start.sh`, `supervise.sh` or `run.py` here.** They scan Kalshi over the network and `start.sh`
>   would leave a scanner + supervisor running in the background — a duplicate of Grok's cloud jobs, which is
>   explicitly forbidden on this box.
> - **To set up and use the desktop app** (the thing you actually launch):
>   `./setup.sh` to check the environment, then `./launch.sh` to start it. See `docs/ARCHITECTURE.md`,
>   `docs/TROUBLESHOOTING.md` and `CONTINUATION.md`.
> - The desktop app never connects to the network, holds no credentials and cannot place orders. It reads
>   `data/` and `research/` read-only and writes only under `var/`.
>
> The commands below are kept for reference because they document how the preserved snapshots were produced.

Requirements: Linux, Python 3.13 (tested on 3.13.5), outbound HTTPS to api.elections.kalshi.com. No credentials are needed or used. _(Legacy cloud scanner — not the desktop app.)_

```bash
tar xzf kalshi-hunter-handoff-2026-10-21.tar.gz && cd kalshi-hunter-handoff-2026-10-21
sha256sum -c MANIFEST.sha256            # every file should say OK
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q tests     # expect: 37 passed
.venv/bin/python run.py health          # JSON; exit 0 = a successful scan within 15 min (a restored old DB reports unhealthy until it scans)
.venv/bin/python run.py once            # one scan cycle against ./data/kalshi.db (public GETs only)
./start.sh                              # idempotent: starts supervise.sh -> run.py loop in the background if not already running
```
Every path is relative to the repo root (`data/`, `research/`, `dashboard/`). Nothing is written outside the repo.

Also included:
- the Track B fix, pending (not yet applied): `research/pending_fixes/`. Apply it with `patch -p0 < research/pending_fixes/trackB_exclude_prereg.patch`, then copy `test_trackB_excludes_prereg.py` into `tests/`.
- the dashboard: `dashboard/index.html`, regenerated every cycle
- the report: `.venv/bin/python run.py validate`
