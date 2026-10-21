#!/usr/bin/env bash
# Kalshi Hunter launcher — offline research viewer and personal trading ledger.
# No order placement, no credentials, no scanner, no network access at run time.
#
#   ./launch.sh                 start the desktop application
#   ./launch.sh --diagnose      print an environment report and exit (makes no changes)
#   ./launch.sh --smoke         visit every page, print JSON, exit non-zero on any QML warning
#   ./launch.sh --interaction-test   drive search/sort/paging/keyboard/journal and assert on the result
#   ./launch.sh --smoke --screenshots DIR [--size WxH]    save one screenshot per page
#   ./launch.sh --sample-account    start with clearly-bannered invented demo data (never your account)
#
# Exit codes: 0 ok · 1 self-test failure · 2 bad arguments · 3 already running · 4 setup problem.
set -u
cd -- "$(dirname -- "$(readlink -f -- "$0")")" || exit 4

PY=.venv/bin/python
LOG_TAIL='var/log/kalshi-hunter.log'

die() {
    printf 'Kalshi Hunter: %s\n' "$1" >&2
    if command -v notify-send >/dev/null 2>&1; then
        notify-send -a 'Kalshi Hunter' 'Kalshi Hunter could not start' "$1 See $LOG_TAIL." 2>/dev/null || true
    fi
    exit 4
}

[ -x "$PY" ] || die "no project-local Python environment at .venv. Run ./setup.sh to see what is missing."
"$PY" -c 'import PySide6' >/dev/null 2>&1 || die "PySide6 is not importable in .venv. Run ./setup.sh."
[ -r data/kalshi.db ] || die "the preserved snapshot data/kalshi.db is missing (this app reads it read-only and can never rebuild it)."

export PYTHONDONTWRITEBYTECODE=1
exec "$PY" -m desktop.app "$@"