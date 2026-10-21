# OPERATIONS
## How the scanner runs on the current box
- `start.sh` is idempotent. It takes `flock` on `data/start.lock`. If `data/supervisor.pid` is alive and `run.py loop` is running, it prints "already running" and exits. Otherwise it kills any stray supervise.sh or run.py loop, then starts `nohup setsid ./supervise.sh` in the background.
- `supervise.sh` writes its PID to `data/supervisor.pid` and loops forever: it runs `.venv/bin/python run.py loop`, and if that exits it logs to `data/stderr.log` (rotated at 5 MB) and restarts after 15 s.
- `run.py loop` runs one cycle every 300 s:
  - a scan of public events and markets
  - structural screens and an audit re-check
  - resolutions
  - research enqueue
  - flb_v1 forward paper entries
  - hash-chain seal plus the external checkpoint
  - hourly validation
  - the dashboard
  On startup it marks any `running` scan as `interrupted` and logs a `service_starts` row. Logs go to `data/service.log` (rotating, 5 MB × 5).
- Health: `.venv/bin/python run.py health` prints `{last_ok_scan_age_s, healthy, errors_last_hour}` and exits 1 if no successful scan has run in 15 min.
- **Watchdog:** a Grok Bot routine named **"Kalshi Hunter watchdog and alerts"** runs every 30 min. It runs `run.py health`, restarts with `./start.sh` if unhealthy, and handles research claims and alerts (`run.py claim | submit | pending-alerts | mark-alerted`). The routine lives in Grok Bot, not in this repo.
- Not reboot-persistent: there's no systemd or cron. After a reboot, only the watchdog routine (or someone running start.sh) brings it back.

## Safely migrating or disabling (in this order)
1. **Stop the watchdog routine first** ("Kalshi Hunter watchdog and alerts" in Grok Bot). Otherwise it will restart the service within 30 min.
2. Stop the supervisor, then the worker, by PID:
   `kill $(cat data/supervisor.pid)`, then `kill $(pgrep -f "run.py loop")`. Confirm both are gone with `pgrep -af "supervise.sh|run.py loop"`.
3. Take a final consistent DB backup, using the SQLite online backup API (safe even if something is still open):
   `.venv/bin/python -c "import sqlite3;s=sqlite3.connect('file:data/kalshi.db?mode=ro',uri=True);d=sqlite3.connect('kalshi-final.db');s.backup(d);print(d.execute('pragma integrity_check').fetchone())"`
4. Verify:
   - `sha256sum kalshi-final.db`
   - `python -c "import sys;sys.path.insert(0,'.');from kh import db,integrity;c=db.connect('kalshi-final.db');print(integrity.verify(c), integrity.verify_checkpoints(c))"` should give `[] []`
   - run `pytest` on the new host
5. On the new host: restore the files, `./start.sh`, wait about 5 min, check `run.py health`, and only then create a new watchdog pointing at the new path.
6. Log the start and end times and the backup hash in `research/INCIDENTS.md` (see the procedure in INC-2026-10-21-01).
