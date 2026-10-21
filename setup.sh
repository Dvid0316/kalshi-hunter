#!/usr/bin/env bash
# Project-local setup and health check for the Kalshi Hunter desktop app.
#
#   ./setup.sh                 report the environment (default; changes nothing)
#   ./setup.sh --create-venv   create .venv, reusing host PySide6 when it is already installed
#   ./setup.sh --install-deps  pip-install the runtime requirements into .venv (needs network)
#   ./setup.sh --tests         run the full test suite
#
# Never uses sudo, never installs system-wide, never starts a scanner or a daemon, and never writes
# outside this project directory (the app itself writes only under var/).
set -u
cd -- "$(dirname -- "$(readlink -f -- "$0")")" || exit 4

PY=.venv/bin/python
RUNTIME=requirements-desktop.txt

say() { printf '%s\n' "$*"; }
ok() { printf '  ok      %s\n' "$*"; }
bad() { printf '  MISSING %s\n' "$*"; }

report() {
    local problems=0
    say "Kalshi Hunter — environment report ($(pwd))"
    if command -v python3 >/dev/null 2>&1; then
        ok "python3: $(python3 --version 2>&1)"
    else
        bad "python3 not found on PATH"
        problems=$((problems + 1))
    fi
    if [ -x "$PY" ]; then
        ok "project venv: $($PY --version 2>&1)"
        if "$PY" -c 'import PySide6, PySide6.QtQml' >/dev/null 2>&1; then
            ok "PySide6: $("$PY" -c 'import PySide6; print(PySide6.__version__)') ($( "$PY" -c 'import PySide6; print(PySide6.__file__)') )"
        else
            bad "PySide6 is not importable in .venv — run ./setup.sh --install-deps"
            problems=$((problems + 1))
        fi
        if "$PY" -c 'import pytest' >/dev/null 2>&1; then
            ok "pytest: $("$PY" -c 'import pytest; print(pytest.__version__)')"
        else
            bad "pytest is not importable (only needed to run the tests)"
        fi
    else
        bad "no .venv — run ./setup.sh --create-venv"
        problems=$((problems + 1))
    fi
    for f in data/kalshi.db data/backtest.db launch.sh; do
        if [ -r "$f" ]; then ok "$f"; else bad "$f"; problems=$((problems + 1)); fi
    done
    if [ -w . ] && [ -w data ]; then
        say "  note    this directory is writable; the app still refuses to write inside data/ or research/"
    fi
    say ""
    say "Evidence must stay read-only. Verify it with:"
    say "  find data research strategies -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum"
    say "  expected: 20bb34ab867b21d6cb5f76face37915eb12225873143ea720acf0fa0c59ae6e5"
    say ""
    if [ "$problems" -gt 0 ]; then
        say "$problems problem(s) found. The app may not start until they are fixed."
        return 1
    fi
    say "Everything the app needs is present. Start it with ./launch.sh"
    return 0
}

case "${1:-}" in
    ''|--check)
        report
        ;;
    --create-venv)
        [ -x "$PY" ] && { say ".venv already exists; nothing to do (use --install-deps to top it up)."; exit 0; }
        say "Creating .venv with --system-site-packages so an already-installed PySide6 is reused (no download)."
        python3 -m venv --system-site-packages .venv || exit 4
        "$PY" -c 'import PySide6' >/dev/null 2>&1 || say "note: PySide6 was not found on the host — run ./setup.sh --install-deps"
        say "Created. Now run: ./setup.sh"
        ;;
    --install-deps)
        [ -x "$PY" ] || { say "No .venv yet — run ./setup.sh --create-venv first."; exit 4; }
        say "Installing runtime requirements from $RUNTIME. This needs network access and downloads PySide6"
        say "unless it is already provided by the host interpreter."
        "$PY" -m pip install -r "$RUNTIME" || exit 4
        say "Done. Now run: ./setup.sh"
        ;;
    --tests)
        [ -x "$PY" ] || { say "No .venv yet — run ./setup.sh --create-venv first."; exit 4; }
        PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$PY" -m pytest -q -p no:cacheprovider tests
        ;;
    -h|--help)
        sed -n '2,10p' "$0"
        ;;
    *)
        say "Unknown option: $1 (see ./setup.sh --help)"; exit 2
        ;;
esac