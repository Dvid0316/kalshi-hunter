"""Kalshi Hunter desktop entry point (offline research + personal ledger).

    ./launch.sh                    normal launch
    ./launch.sh --sample-account   same, with clearly-labelled SAMPLE account data (never your real account)
    ./launch.sh --diagnose         print environment/data checks and exit (no window)
    ./launch.sh --smoke            headless: load every page, report QML warnings (used by the test suite)
    ./launch.sh --interaction-test headless: click/type/shortcut through the UI
    ./launch.sh --screenshots DIR  capture every page to DIR (add --size 1100x760 for compact layouts)

Nothing here starts a scanner, contacts a network, reads credentials, or places orders.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

from . import logging_setup, paths

ROOT = paths.ROOT
log = logging.getLogger('kh.app')
EXIT_LOCKED = 3
TEST_FLAGS = ('smoke', 'interaction_test', 'screenshots')


def _parse(argv):
    p = argparse.ArgumentParser(prog='kalshi-hunter', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--smoke', action='store_true')
    p.add_argument('--interaction-test', action='store_true', dest='interaction_test')
    p.add_argument('--screenshots', '--capture-dir', type=Path, dest='screenshots')
    p.add_argument('--compact', action='store_true', help='shortcut for --size 1100x760')
    p.add_argument('--size', default=None, help='window size WxH, e.g. 1100x760')
    p.add_argument('--sample-account', action='store_true')
    p.add_argument('--diagnose', action='store_true')
    p.add_argument('--no-lock', action='store_true')
    return p.parse_args(argv)


def diagnose() -> int:
    """Human-readable health check. Exit 0 = everything the app needs is present."""
    import sqlite3
    info = logging_setup.environment_report()
    problems = []
    if not info.get('snapshot_exists'):
        problems.append(f"research snapshot missing: {info['snapshot']}")
    else:
        try:
            with sqlite3.connect(paths.snapshot_path().as_uri() + '?mode=ro&immutable=1', uri=True) as c:
                info['snapshot_tables'] = c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
                info['snapshot_markets'] = c.execute('SELECT COUNT(*) FROM markets').fetchone()[0]
        except sqlite3.Error as exc:
            problems.append(f'snapshot unreadable: {exc}')
    info['account_db'] = str(paths.account_db_path())
    info['account_db_exists'] = paths.account_db_path().exists()
    info['display'] = dict(DISPLAY=os.environ.get('DISPLAY'), WAYLAND_DISPLAY=os.environ.get('WAYLAND_DISPLAY'),
                           QT_QPA_PLATFORM=os.environ.get('QT_QPA_PLATFORM'))
    try:
        import PySide6.QtQuick  # noqa: F401
    except ImportError as exc:
        problems.append(f'PySide6 QtQuick missing: {exc}')
    info['scanner_processes'] = 'none started by this app (it has no scanner)'
    info['problems'] = problems
    print(json.dumps(info, indent=2, default=str))
    return 1 if problems else 0


def main(argv=None) -> int:
    args = _parse(argv)
    logging_setup.setup()
    if args.diagnose:
        return diagnose()
    if args.compact and not args.size:
        args.size = '1100x760'
    testing = any(getattr(args, f) for f in TEST_FLAGS)

    os.environ.setdefault('QT_QUICK_CONTROLS_STYLE', 'Basic')       # we draw every control; avoid native-style warnings
    from PySide6.QtCore import QLockFile, QTimer, QUrl
    from PySide6.QtGui import QFont, QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuick import QQuickWindow  # noqa: F401  (registers the QQuickWindow wrapper so rootObjects() has grabWindow/contentItem)

    from .account_service import AccountService
    from .bridge import Bridge, PAGES
    from .repository import Repository

    app = QGuiApplication(sys.argv[:1])
    app.setApplicationName('Kalshi Hunter')
    app.setOrganizationName('Local Research')
    app.setApplicationVersion('1.0.0')
    app.setDesktopFileName('kalshi-hunter')
    app.setFont(QFont(['Inter', 'Noto Sans', 'DejaVu Sans'], 10))
    qt_messages = logging_setup.install_qt_handler()

    lock = None
    if not testing and not args.no_lock:
        paths.var_dir().mkdir(parents=True, exist_ok=True)
        lock = QLockFile(str(paths.var_dir() / 'kalshi-hunter.lock'))
        lock.setStaleLockTime(0)
        if not lock.tryLock(100):
            print('Kalshi Hunter is already running (lock: var/kalshi-hunter.lock).', file=sys.stderr)
            return EXIT_LOCKED

    repo = Repository()
    account = AccountService(repo, sample=args.sample_account)
    try:
        account.prepare()
    except Exception as exc:                                # a broken sample must not stop the research views
        log.error('sample account unavailable: %s', exc)
    bridge = Bridge(repo, sample=args.sample_account, account_service=account)
    engine = QQmlApplicationEngine()
    ctx = engine.rootContext()
    ctx.setContextProperty('backend', bridge)
    ctx.setContextProperty('appVersion', app.applicationVersion())
    errors: list[str] = []
    engine.warnings.connect(lambda ws: errors.extend(w.toString() for w in ws))
    engine.load(QUrl.fromLocalFile(str(ROOT / 'desktop/qml/Main.qml')))
    if not engine.rootObjects():
        log.error('QML failed to load: %s', errors)
        print('\n'.join(errors) or 'QML failed to load', file=sys.stderr)
        bridge.close()
        return 1
    window = engine.rootObjects()[0]
    if args.size:
        try:
            w, h = (int(x) for x in args.size.lower().split('x'))
            window.resize(w, h)
        except ValueError:
            print(f'bad --size {args.size!r}; expected WxH', file=sys.stderr)
            return 2

    shutdown_started = []

    def shutdown(*_):
        if not shutdown_started:
            shutdown_started.append(1)
            log.info('shutdown requested')
            app.quit()

    app.aboutToQuit.connect(bridge.close)
    app.aboutToQuit.connect(lambda: lock.unlock() if lock else None)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, shutdown)
    pump = QTimer()                                          # lets Python signal handlers run inside the Qt loop
    pump.start(250)
    pump.timeout.connect(lambda: None)
    QTimer.singleShot(0, bridge.load)
    log.info('started (sample=%s, testing=%s)', args.sample_account, testing)

    if testing:
        from . import selftest
        selftest.install(app, window, bridge, errors, qt_messages, args, PAGES)
    code = app.exec()
    log.info('exited with code %s', code)
    return code


if __name__ == '__main__':
    sys.exit(main())
