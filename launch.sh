#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
export PYTHONDONTWRITEBYTECODE=1
exec .venv/bin/python -m desktop.app "$@"
