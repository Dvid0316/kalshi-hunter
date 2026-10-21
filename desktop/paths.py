"""Filesystem layout and write guards.

Everything the desktop *writes* lives under VAR (default ``<project>/var``, override with
``KH_VAR_DIR``). Evidence (``data/`` and ``research/``) is never a write target: every
writer calls ``assert_writable_path`` first, and tests prove the guard rejects evidence.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIRS = (ROOT / 'data', ROOT / 'research', ROOT / 'strategies')


def var_dir() -> Path:
    return Path(os.environ.get('KH_VAR_DIR') or ROOT / 'var').expanduser()


def snapshot_path() -> Path:
    return Path(os.environ.get('KH_SNAPSHOT') or ROOT / 'data/kalshi.db').expanduser()


def backtest_path() -> Path:
    return Path(os.environ.get('KH_BACKTEST') or ROOT / 'data/backtest.db').expanduser()


def research_docs_dir() -> Path:
    return Path(os.environ.get('KH_RESEARCH_DOCS') or ROOT / 'research').expanduser()


def cache_dir() -> Path:
    return var_dir() / 'cache'


def log_dir() -> Path:
    return var_dir() / 'log'


def account_db_path() -> Path:
    return var_dir() / 'account.db'


def sample_dir() -> Path:
    """Sample-account fixtures live apart from the real account DB so they can never mix."""
    return var_dir() / 'sample'


class EvidenceWriteError(PermissionError):
    pass


def assert_writable_path(path) -> Path:
    """Raise unless ``path`` is outside every evidence directory and not an evidence DB."""
    p = Path(path).expanduser().resolve()
    snaps = {snapshot_path().resolve(), backtest_path().resolve()}
    if p in snaps or any(p.name.startswith(s.name) for s in snaps if p.parent == s.parent):
        raise EvidenceWriteError(f'Refusing to write to evidence database: {p}')
    for d in EVIDENCE_DIRS:
        d = d.resolve()
        if p == d or d in p.parents:
            raise EvidenceWriteError(f'Refusing to write inside evidence directory: {p}')
    return p
