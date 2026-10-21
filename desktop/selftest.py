"""Headless self-tests driven from inside the app (``--smoke``, ``--interaction-test``, ``--screenshots``).

They exercise the real QML and the real bridge with synthetic input events. They need no display
server when run with QT_QPA_PLATFORM=offscreen. Output is one JSON line; exit code 0 means pass.
"""
from __future__ import annotations

import json
import logging
import sys
import time
import traceback
from pathlib import Path

log = logging.getLogger('kh.selftest')

SETTLE_S = 0.35
TIMEOUT_S = 40


def install(app, window, bridge, errors, qt_messages, args, pages):
    from PySide6.QtCore import QTimer
    t = _Tester(app, window, bridge, errors, qt_messages, args, pages)
    app._kh_tester = t                     # PySide holds bound methods weakly: keep the tester alive explicitly
    QTimer.singleShot(200, lambda: t.run())
    return t


class _Tester:
    def __init__(self, app, window, bridge, errors, qt_messages, args, pages):
        self.app, self.window, self.bridge, self.errors, self.qt, self.args, self.pages = app, window, bridge, errors, qt_messages, args, pages

    # ------------------------------------------------------------------ helpers
    def pump(self, seconds=0.0):
        end = time.time() + seconds
        while True:
            self.app.processEvents()
            if time.time() >= end:
                return
            time.sleep(0.01)

    def wait_until(self, pred, what, timeout=TIMEOUT_S):
        log.info('waiting for %s', what)
        end = time.time() + timeout
        while time.time() < end:
            self.app.processEvents()
            if pred():
                return
            time.sleep(0.02)
        raise AssertionError(f'timed out waiting for {what}')

    def idle(self):
        return not self.bridge.ui['loading']

    def settle(self):
        self.wait_until(self.idle, 'data loading to finish')
        self.pump(SETTLE_S)

    def find(self, name):
        def walk(item):
            if item.objectName() == name:
                return item
            for child in item.childItems():
                r = walk(child)
                if r is not None:
                    return r
            return None
        item = walk(self.window.contentItem())
        if item is None:
            raise AssertionError(f'item {name!r} not found on page {self.bridge.ui["page"]}')
        return item

    def click(self, name):
        from PySide6.QtCore import Qt, QPointF
        from PySide6.QtTest import QTest
        item = self.find(name)
        pos = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
        QTest.mouseClick(self.window, Qt.LeftButton, Qt.NoModifier, pos)
        self.pump(0.25)

    def key(self, key, mods=None):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        QTest.keyClick(self.window, key, mods or Qt.NoModifier)
        self.pump(0.2)

    def page(self):
        return self.bridge.ui['page']

    # ------------------------------------------------------------------ drivers
    def run(self):
        code = 0
        try:
            self.wait_until(lambda: self.bridge.ui['ready'] and self.idle(), 'initial snapshot load')
            if self.args.interaction_test:
                result = self.interaction()
            else:
                result = self.tour()
            problems = self.problems()
            result.update(qml_warnings=list(self.errors) + [m for m in self.qt if 'QML' in m or '.qml' in m], ui_errors=self.bridge.ui['errors'])
            if problems or result['qml_warnings'] or result['ui_errors']:
                code = 1
            result['problems'] = problems
            print(json.dumps(result, default=str), flush=True)
        except Exception as exc:                                  # any failure is a failed self-test
            traceback.print_exc()
            print(json.dumps(dict(error=str(exc), qml_warnings=list(self.errors))), file=sys.stdout, flush=True)
            code = 1
        self.app.exit(code)

    def problems(self):
        return [m for m in self.qt if 'QML' in m or 'TypeError' in m or 'ReferenceError' in m]

    def tour(self):
        shots = self.args.screenshots
        if shots:
            Path(shots).mkdir(parents=True, exist_ok=True)
        visited = []
        for page in self.pages:
            log.info('tour: %s (loading=%s)', page, self.bridge.ui['loading'])
            self.bridge.navigate(page)
            self.settle()
            assert self.page() == page, (page, self.page())
            if shots:
                img = self.window.grabWindow()
                assert not img.isNull() and img.width() > 100, 'empty screenshot'
                img.save(str(Path(shots) / f'{page.lower()}.png'))
            visited.append(page)
        return dict(ready=True, pages=len(visited), visited=visited, size=[self.window.width(), self.window.height()])

    def interaction(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        b, steps = self.bridge, []

        def step(name):
            steps.append(name)

        self.click('nav_Markets'); self.settle()
        assert self.page() == 'Markets'; step('nav click')
        self.click('market_search')
        for ch in 'CONTROL':
            QTest.keyClick(self.window, ch)
        self.wait_until(lambda: b.markets.get('search') == 'CONTROL' and self.idle(), 'search results')
        rows = b.markets['rows']
        assert rows and all('control' in (r['ticker'] + r['title'] + r['subtitle']).lower() for r in rows), 'search results must match the term'
        step('debounced search')
        self.click('sort_volume'); self.settle()
        assert b.markets['sort'] == 'volume'; first = b.markets['desc']
        self.click('sort_volume'); self.settle()
        assert b.markets['desc'] != first; step('sort toggle')
        self.click('row_0'); self.settle()
        assert b.ui['selectedTicker'] == b.markets['rows'][0]['ticker'] and b.detail.get('ticker') == b.ui['selectedTicker']; step('row select')
        self.key(Qt.Key_Escape)
        self.wait_until(lambda: b.markets.get('search') == '' and self.idle(), 'escape clears search'); step('escape clears search')
        self.key(Qt.Key_3, Qt.ControlModifier); self.settle()
        assert self.page() == 'Research'; step('ctrl+3')
        self.key(Qt.Key_K, Qt.ControlModifier); self.settle()
        assert self.page() == 'Markets'; step('ctrl+k')
        issues, audited = [], 0
        for n, page in enumerate(self.pages, start=1):
            self.click('nav_' + page); self.settle()
            assert self.page() == page, (page, self.page())
            found, seen = self.a11y_audit()
            issues += found
            audited += seen
        assert audited > 400, f'accessibility audit looked at only {audited} nodes: it is not inspecting the UI'
        assert not issues, 'accessibility audit: ' + '; '.join(issues[:8])
        step(f'all pages via nav + accessibility audit ({audited} nodes)')

        # --- market filters, paging, keyboard paging
        self.click('nav_Markets'); self.settle()
        b.resetMarketFilters(); self.settle()
        b.filterMarkets('scope', 'all'); self.settle()
        b.filterMarkets('status', 'settled'); self.settle()
        rows = b.markets['rows']
        assert rows and all(r['status'] in ('determined', 'finalized') for r in rows), 'status filter must only return settled markets'
        total_settled = b.markets['total']
        b.filterMarkets('status', 'any'); self.settle()
        assert b.markets['total'] >= total_settled; step('status filter')
        before = b.markets['rows'][0]['ticker']
        self.key(Qt.Key_Right, Qt.AltModifier); self.settle()
        assert b.markets['page'] == 2 and b.markets['rows'][0]['ticker'] != before, 'Alt+Right must advance a page'
        self.key(Qt.Key_Left, Qt.AltModifier); self.settle()
        assert b.markets['page'] == 1 and b.markets['rows'][0]['ticker'] == before; step('keyboard paging')
        b.resetMarketFilters(); self.settle()

        # --- positions + journal (sample data only: the app is started with --sample-account)
        if b.ui['sample']:
            self.click('nav_Positions'); self.settle()
            assert b.positions['summary']['open_count'] >= 1 and b.positions['rows'], 'sample open positions must show'
            b.setPositionsTab('closed'); self.settle()
            assert b.positions['tab'] == 'closed' and b.positions['rows'] and all('realized' in r for r in b.positions['rows'])
            step('positions tabs')
            self.click('nav_Journal'); self.settle()
            n0 = len(b.journal['entries'])
            b.saveJournal(0, 'Self-test entry', 'created by the interaction test', '', 'note', 'selftest', '', '', '')
            self.wait_until(lambda: len(b.journal['entries']) == n0 + 1 and self.idle(), 'journal entry saved')
            made = next(e for e in b.journal['entries'] if e['title'] == 'Self-test entry')
            b.deleteJournal(made['id'])
            self.wait_until(lambda: len(b.journal['entries']) == n0 and self.idle(), 'journal entry hidden'); step('journal save/delete')
        self.key(Qt.Key_F1)
        dialog = self.find_popup('shortcuts_dialog')
        assert dialog is not None and dialog.property('visible'), 'F1 must open the shortcuts help'
        self.key(Qt.Key_Escape); step('F1 help')
        return dict(interaction_test='passed', steps=steps, qml_warnings=[])

    def find_popup(self, name):
        from PySide6.QtCore import QObject
        return self.window.findChild(QObject, name)

    # ------------------------------------------------------------------ accessibility (what a screen reader would see)
    def a11y_audit(self):
        from PySide6.QtGui import QAccessible
        QAccessible.setActive(True)
        root = QAccessible.queryAccessibleInterface(self.window)
        issues, seen = [], [0]
        need_name = {QAccessible.Role.Button, QAccessible.Role.PushButton, QAccessible.Role.CheckBox, QAccessible.Role.ComboBox,
                     QAccessible.Role.EditableText, QAccessible.Role.RadioButton, QAccessible.Role.ListItem}

        def walk(node, depth=0):
            if node is None or depth > 40:
                return
            if node.state().invisible:                      # hidden items are not reachable by assistive tech
                return
            seen[0] += 1
            role = node.role()
            name = (node.text(QAccessible.Text.Name) or '').strip()
            if role in need_name and not name:
                obj = node.object()
                where = ''
                if obj is not None:
                    where = f' [{obj.metaObject().className()} id={obj.objectName() or "-"} parent={obj.parent().metaObject().className() if obj.parent() else "-"}]'
                issues.append(f'{role.name} without accessible name (page {self.page()}){where}')
            for i in range(node.childCount()):
                walk(node.child(i), depth + 1)
        walk(root)
        return issues, seen[0]
