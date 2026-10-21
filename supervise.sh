#!/bin/bash
# Auto-restart supervisor. Use ./start.sh (idempotent) rather than running this directly.
cd "$(dirname "$0")"
echo $$ > data/supervisor.pid
while true; do
  .venv/bin/python run.py loop >> data/stderr.log 2>&1
  echo "$(date '+%F %T') service exited ($?), restarting in 15s" >> data/stderr.log
  [ "$(stat -c%s data/stderr.log)" -gt 5000000 ] && mv -f data/stderr.log data/stderr.log.1
  sleep 15
done
