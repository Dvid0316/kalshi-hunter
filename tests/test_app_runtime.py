"""Whole-application tests: real processes, real Qt/QML (offscreen), real files.

Every subprocess gets its own temporary KH_VAR_DIR, so no test can read or write the user's real ledger,
settings or logs. The evidence directories are hashed before and after the whole module.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = [ROOT / 'data', ROOT / 'research', ROOT / 'strategies']


def tree_hash() -> str:
    h = hashlib.sha256()
    for base in EVIDENCE:
        for p in sorted(base.rglob('*')):
            if p.is_file():
                h.update(str(p.relative_to(ROOT)).encode())
                with p.open('rb') as f:
                    for chunk in iter(lambda: f.read(1 << 20), b''):
                        h.update(chunk)
    return h.hexdigest()


@pytest.fixture(scope='module', autouse=True)
def evidence_untouched():
    before = tree_hash()
    yield
    assert tree_hash() == before, 'running the application changed the preserved evidence'


def env_for(var: Path, **extra):
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software', PYTHONDONTWRITEBYTECODE='1', KH_VAR_DIR=str(var))
    env.pop('WAYLAND_DISPLAY', None)
    env.update(extra)
    return env


def run_app(args, var, timeout=150, **env):
    return subprocess.run([sys.executable, '-u', '-m', 'desktop.app', *args], cwd=ROOT, env=env_for(var, **env),
                          capture_output=True, text=True, timeout=timeout)


def last_json(text: str) -> dict:
    for line in reversed(text.strip().splitlines()):
        if line.startswith('{'):
            return json.loads(line)
    raise AssertionError('no JSON result in output:\n' + text[-2000:])


# ------------------------------------------------------------------ startup: every page, no warnings
def test_smoke_loads_every_page_without_qml_warnings(tmp_path):
    p = run_app(['--smoke'], tmp_path)
    assert p.returncode == 0, p.stdout + p.stderr
    r = last_json(p.stdout)
    assert r['pages'] == 10 and r['qml_warnings'] == [] and r['ui_errors'] == {} and r['problems'] == []
    assert r['visited'] == ['Overview', 'Markets', 'Research', 'Strategy', 'Alerts', 'Positions', 'History', 'Journal', 'Accuracy', 'Evidence']


def test_smoke_at_minimum_window_size(tmp_path):
    p = run_app(['--smoke', '--size', '1100x760', '--sample-account'], tmp_path)
    assert p.returncode == 0, p.stdout + p.stderr
    r = last_json(p.stdout)
    assert r['size'] == [1100, 760] and r['qml_warnings'] == []


def test_smoke_in_a_large_window(tmp_path):
    p = run_app(['--smoke', '--size', '1920x1080'], tmp_path)
    assert p.returncode == 0, p.stdout + p.stderr
    assert last_json(p.stdout)['qml_warnings'] == []


def test_interaction_search_sort_select_filter_paging_keyboard_and_a11y(tmp_path):
    p = run_app(['--interaction-test', '--sample-account'], tmp_path, timeout=240)
    assert p.returncode == 0, p.stdout + p.stderr
    r = last_json(p.stdout)
    assert r['interaction_test'] == 'passed' and r['qml_warnings'] == [] and r['ui_errors'] == {}
    for step in ('debounced search', 'sort toggle', 'row select', 'escape clears search', 'ctrl+3', 'ctrl+k', 'status filter',
                 'keyboard paging', 'positions tabs', 'journal save/delete', 'F1 help'):
        assert step in r['steps'], step
    assert any(s.startswith('all pages via nav + accessibility audit') for s in r['steps'])


def test_the_tests_never_wrote_outside_their_temp_var_dir(tmp_path):
    before = {p for p in (ROOT / 'var').rglob('*')} if (ROOT / 'var').exists() else set()
    run_app(['--smoke'], tmp_path)
    after = {p for p in (ROOT / 'var').rglob('*')} if (ROOT / 'var').exists() else set()
    assert after == before, 'the app wrote into the project var/ although KH_VAR_DIR pointed elsewhere'
    assert (tmp_path / 'log' / 'kalshi-hunter.log').exists()


# ------------------------------------------------------------------ diagnostics
def test_diagnose_reports_environment_and_makes_no_changes(tmp_path):
    p = run_app(['--diagnose'], tmp_path)
    assert p.returncode == 0, p.stdout + p.stderr
    info = json.loads(p.stdout[p.stdout.index('{'):])
    assert info['problems'] == [] and 'none started' in info['scanner_processes']
    assert not (tmp_path / 'account.db').exists()


# ------------------------------------------------------------------ startup / shutdown / single instance
def start(var, *args):
    return subprocess.Popen([sys.executable, '-u', '-m', 'desktop.app', *args], cwd=ROOT, env=env_for(var),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def wait_for(cond, timeout=60.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.2)
    return False


def test_clean_shutdown_on_sigterm_releases_the_lock(tmp_path):
    app = start(tmp_path)
    try:
        lock = tmp_path / 'kalshi-hunter.lock'
        log = tmp_path / 'log' / 'kalshi-hunter.log'
        assert wait_for(lambda: lock.exists() and log.exists() and 'started (' in log.read_text(errors='replace'), 60), 'app did not start'
        assert app.poll() is None
        app.send_signal(signal.SIGTERM)
        assert app.wait(timeout=20) == 0, 'SIGTERM must lead to a clean exit'
        assert wait_for(lambda: not lock.exists(), 5), 'the lock file must be released'
    finally:
        if app.poll() is None:
            app.kill()
            app.wait()


def test_second_instance_is_refused_without_disturbing_the_first(tmp_path):
    app = start(tmp_path)
    try:
        lock = tmp_path / 'kalshi-hunter.lock'
        assert wait_for(lambda: lock.exists(), 60)
        second = run_app([], tmp_path, timeout=60)
        assert second.returncode == 3 and 'already running' in second.stderr
        assert app.poll() is None, 'the first instance must keep running'
    finally:
        app.send_signal(signal.SIGTERM)
        try:
            app.wait(timeout=20)
        except subprocess.TimeoutExpired:
            app.kill()


def test_a_lock_left_by_a_killed_run_does_not_block_the_next_start(tmp_path):
    lock = tmp_path / 'kalshi-hunter.lock'
    log = tmp_path / 'log' / 'kalshi-hunter.log'
    first = start(tmp_path)
    try:
        assert wait_for(lambda: lock.exists() and log.exists() and 'started (' in log.read_text(errors='replace'), 60)
        first.kill()                                                       # a hard crash: no chance to clean up
        first.wait(timeout=20)
        assert lock.exists(), 'precondition: the crash must have left its lock file behind'
        second = start(tmp_path)
        try:
            assert wait_for(lambda: log.read_text(errors='replace').count('started (') >= 2, 60), 'a stale lock must not stop the app starting'
            assert second.poll() is None
        finally:
            second.send_signal(signal.SIGTERM)
            try:
                second.wait(timeout=20)
            except subprocess.TimeoutExpired:
                second.kill()
    finally:
        if first.poll() is None:
            first.kill()


# ------------------------------------------------------------------ error recovery
def test_corrupt_settings_fall_back_to_defaults(tmp_path):
    (tmp_path / 'settings.json').write_text('{broken json')
    p = run_app(['--smoke'], tmp_path)
    assert p.returncode == 0, p.stdout + p.stderr
    assert (tmp_path / 'settings.json.corrupt').read_text() == '{broken json', 'the damaged file is preserved for diagnosis, not silently destroyed'
    assert 'settings file unreadable' in (tmp_path / 'log' / 'kalshi-hunter.log').read_text()


def test_corrupt_ledger_shows_errors_but_research_pages_still_work(tmp_path):
    bad = tmp_path / 'account.db'
    bad.write_bytes(b'not a database at all')
    digest = hashlib.sha256(bad.read_bytes()).hexdigest()
    probe = ROOT / 'tests' / 'helpers' / 'bridge_probe.py'
    p = subprocess.run([sys.executable, '-u', str(probe)], cwd=ROOT, env=env_for(tmp_path), capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stdout + p.stderr
    r = last_json(p.stdout)
    assert r['ready'] is True and r['overview_loaded'] is True and r['markets_loaded'] is True, 'research views must survive a broken ledger'
    assert set(r['errors']) >= {'positions', 'history'}
    assert all('cannot be opened' in msg and 'not modified' in msg for msg in r['errors'].values())
    assert hashlib.sha256(bad.read_bytes()).hexdigest() == digest


# ------------------------------------------------------------------ no network, ever
def test_application_opens_no_network_connections(tmp_path):
    code = (
        "import socket, sys\n"
        "def deny(*a, **k):\n"
        "    raise AssertionError('NETWORK ACCESS ATTEMPTED: %r' % (a,))\n"
        "socket.socket.connect = deny\n"
        "socket.socket.connect_ex = deny\n"
        "socket.create_connection = deny\n"
        "socket.getaddrinfo = deny\n"
        "from desktop import app\n"
        "sys.exit(app.main(['--smoke', '--sample-account']))\n")
    p = subprocess.run([sys.executable, '-u', '-c', code], cwd=ROOT, env=env_for(tmp_path), capture_output=True, text=True, timeout=150)
    assert p.returncode == 0, p.stdout + p.stderr
    assert 'NETWORK ACCESS ATTEMPTED' not in p.stdout + p.stderr
