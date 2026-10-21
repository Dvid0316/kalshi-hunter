#!/bin/bash
# Idempotent: safe to rerun any time. Starts the supervisor only if one isn't already alive.
cd "$(dirname "$0")"
exec 9>data/start.lock; flock -n 9 || { echo "another start in progress"; exit 0; }
if [ -f data/supervisor.pid ] && kill -0 "$(cat data/supervisor.pid)" 2>/dev/null && pgrep -f "run.py loop" >/dev/null; then
  echo "already running (supervisor $(cat data/supervisor.pid))"; exit 0
fi
pkill -f "supervise.sh" 2>/dev/null; pkill -f "run.py loop" 2>/dev/null; sleep 1
nohup setsid ./supervise.sh >/dev/null 2>&1 9>&- &
sleep 2; echo "started (supervisor $(cat data/supervisor.pid))"
