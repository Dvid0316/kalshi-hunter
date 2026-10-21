"""Tiny project-local settings file (JSON under var/). No QSettings: nothing is written outside the project."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from . import paths

DEFAULTS = {
    # Opening a source link launches the user's own browser. Off by default: copying a link never needs this.
    'allow_open_links': False,
    'last_page': 'Overview',
}


def _file() -> Path:
    return paths.var_dir() / 'settings.json'


def load() -> dict:
    data = dict(DEFAULTS)
    try:
        raw = json.loads(_file().read_text())
        if isinstance(raw, dict):
            data.update({k: raw[k] for k in DEFAULTS if k in raw and isinstance(raw[k], type(DEFAULTS[k]))})
    except (OSError, ValueError):
        pass
    return data


def save(values: dict) -> bool:
    """Atomic write. Returns False (and never raises) if the file cannot be written."""
    try:
        f = paths.assert_writable_path(_file())
        f.parent.mkdir(parents=True, exist_ok=True)
        clean = {k: values[k] for k in DEFAULTS if k in values}
        fd, tmp = tempfile.mkstemp(dir=f.parent, prefix='.settings-', suffix='.tmp')
        with os.fdopen(fd, 'w') as fh:
            json.dump(clean, fh, indent=2)
        os.replace(tmp, f)
        return True
    except (OSError, ValueError, PermissionError):
        return False
