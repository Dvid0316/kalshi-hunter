"""Rotating diagnostic log under var/log plus Qt message capture.

The log never contains credentials (there are none) or full account records: account events log
counts and file names only.
"""
from __future__ import annotations

import logging
import logging.handlers
import platform
import sys

from . import paths

LOG_NAME = 'kalshi-hunter.log'
_configured = False


def setup(level=logging.INFO) -> logging.Logger:
    global _configured
    root = logging.getLogger('kh')
    if _configured:
        return root
    root.setLevel(level)
    fmt = logging.Formatter('%(asctime)s %(levelname)-7s %(name)s: %(message)s')
    try:
        d = paths.log_dir()
        paths.assert_writable_path(d / LOG_NAME)
        d.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(d / LOG_NAME, maxBytes=1_000_000, backupCount=4, encoding='utf-8')
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        pass                                   # logging must never stop the app from starting
    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.WARNING)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    _configured = True
    return root


def install_qt_handler():
    """Route Qt warnings/errors into the log file (and keep a list for the smoke tests)."""
    from PySide6.QtCore import qInstallMessageHandler, QtMsgType
    log = logging.getLogger('kh.qt')
    seen: list[str] = []

    def handler(mode, ctx, message):
        level = {QtMsgType.QtDebugMsg: logging.DEBUG, QtMsgType.QtInfoMsg: logging.INFO,
                 QtMsgType.QtWarningMsg: logging.WARNING}.get(mode, logging.ERROR)
        if level >= logging.WARNING:
            seen.append(message)
        log.log(level, '%s (%s:%s)', message, getattr(ctx, 'file', '') or '?', getattr(ctx, 'line', 0))

    qInstallMessageHandler(handler)
    return seen


def environment_report() -> dict:
    import sqlite3
    info: dict = dict(python=sys.version.split()[0], platform=platform.platform(), sqlite=sqlite3.sqlite_version,
                snapshot=str(paths.snapshot_path()), var=str(paths.var_dir()), log=str(paths.log_dir() / LOG_NAME))
    try:
        import PySide6
        from PySide6.QtCore import qVersion
        info.update(pyside=PySide6.__version__, qt=qVersion())
    except ImportError:
        info.update(pyside='missing', qt='missing')
    sp = paths.snapshot_path()
    info['snapshot_exists'] = sp.exists()
    if sp.exists():
        st = sp.stat()
        info.update(snapshot_bytes=st.st_size, snapshot_mtime=st.st_mtime)
    return info
