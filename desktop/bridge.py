"""QObject bridge between QML and the offline data services.

Rules
  * QML only ever receives plain data (maps/lists/strings). Money is pre-formatted text.
  * All I/O runs on worker threads; every request carries a per-kind sequence number so a slow,
    superseded query can never overwrite a newer answer.
  * Failures are caught, logged with a traceback, and surfaced as a per-kind error with a Retry path.
  * No network access, credentials or order capability exist here (tests enforce the import graph).
"""
from __future__ import annotations

import logging
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from PySide6.QtCore import QObject, Property, Signal, Slot, QUrl
from PySide6.QtGui import QGuiApplication, QDesktopServices

from kh.ledger.models import LedgerError as M_LedgerError

from . import settings as app_settings
from .account_service import AccountService, AUTHORIZATION
from .freshness import ConnectionState, STATE_TEXT
from .logging_setup import environment_report
from .repository import Repository

log = logging.getLogger('kh.bridge')

PAGES = ['Overview', 'Markets', 'Research', 'Strategy', 'Alerts', 'Positions', 'History', 'Journal', 'Accuracy', 'Evidence']
# Which data each page needs. Loaded lazily the first time the page is opened.
PAGE_DATA = {
    'Overview': ['overview', 'account', 'positions'], 'Markets': ['markets', 'categories', 'detail'], 'Research': ['cards', 'detail'],
    'Strategy': ['cards', 'detail'], 'Alerts': ['alerts'], 'Positions': ['account', 'positions'],
    'History': ['account', 'history', 'cards'], 'Journal': ['account', 'journal', 'comparison'],
    'Accuracy': ['accuracy'], 'Evidence': ['overview', 'documents', 'quality', 'diagnostics'],
}


class Bridge(QObject):
    uiChanged = Signal()
    overviewChanged = Signal()
    marketsChanged = Signal()
    detailChanged = Signal()
    categoriesChanged = Signal()
    cardsChanged = Signal()
    alertsChanged = Signal()
    accuracyChanged = Signal()
    documentsChanged = Signal()
    documentChanged = Signal()
    accountChanged = Signal()
    positionsChanged = Signal()
    historyChanged = Signal()
    journalChanged = Signal()
    comparisonChanged = Signal()
    qualityChanged = Signal()
    diagnosticsChanged = Signal()
    toast = Signal(str, str)                 # message, kind (info|ok|warn|error)
    focusSearch = Signal()                   # Ctrl+K or "/" : focus the current page's search box
    stepPageRequested = Signal(int)          # Alt+Left / Alt+Right : previous / next page of the current table
    dialogRequested = Signal(str)            # shortcuts | settings | import | record
    actionDone = Signal(str, 'QVariantMap')  # name, result
    finished = Signal(str, int, object)

    def __init__(self, repo: Repository | None = None, *, sample=False, account_service: AccountService | None = None):
        super().__init__()
        self.repo = repo or Repository()
        self.account = account_service or AccountService(self.repo, sample=sample)
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='kh-worker')
        self.settings = app_settings.load()
        self.serial: dict[str, int] = {}
        self._lock = threading.Lock()
        self._retry: dict[str, tuple] = {}
        self._loaded: set[str] = set()
        self._ui: dict[str, Any] = dict(ready=False, page='Overview', loading=[], errors={}, sample=bool(sample), selectedTicker='', cohort='research',
                        allowLinks=bool(self.settings.get('allow_open_links')), indexState='pending', pages=PAGES,
                        connection=self._connection(), authorization=AUTHORIZATION, closing=False)
        self._data: dict[str, Any] = dict(overview={}, markets=dict(rows=[], total=0, page=1, pages=1, offset=0, sort='ticker', desc=False, scope='watchlist',
                                                    status='any', category='any', quotes_only=False, search=''),
                          detail={}, categories=[], cards=dict(research=[], strategy=[]), alerts={}, accuracy={}, documents=[], document={},
                          account={}, positions={}, history={}, journal={}, comparison={}, quality={}, diagnostics={})
        self._mq: dict[str, Any] = dict(search='', offset=0, sort=None, desc=None, status='any', category='any', quotes_only=False, scope=None)
        self._pq: dict[str, Any] = dict(tab='open', search='', sort=None, desc=None, offset=0)
        self._hq: dict[str, Any] = dict(kind='transactions', search='', sort=None, desc=None, offset=0)
        self._cq: dict[str, Any] = dict(offset=0, sort='edge')
        self._jq: dict[str, Any] = dict(search='')
        self.finished.connect(self._receive)

    # ------------------------------------------------------------------ properties
    def _g(self, key):
        return self._data[key]

    @Property('QVariantMap', notify=uiChanged)
    def ui(self): return self._ui                                    # noqa: E704
    @Property('QVariantMap', notify=overviewChanged)
    def overview(self): return self._data['overview']                # noqa: E704
    @Property('QVariantMap', notify=marketsChanged)
    def markets(self): return self._data['markets']                  # noqa: E704
    @Property('QVariantMap', notify=detailChanged)
    def detail(self): return self._data['detail']                    # noqa: E704
    @Property('QVariantList', notify=categoriesChanged)
    def categories(self): return self._data['categories']            # noqa: E704
    @Property('QVariantMap', notify=cardsChanged)
    def cards(self): return self._data['cards']                      # noqa: E704
    @Property('QVariantMap', notify=alertsChanged)
    def alerts(self): return self._data['alerts']                    # noqa: E704
    @Property('QVariantMap', notify=accuracyChanged)
    def accuracy(self): return self._data['accuracy']                # noqa: E704
    @Property('QVariantList', notify=documentsChanged)
    def documents(self): return self._data['documents']              # noqa: E704
    @Property('QVariantMap', notify=documentChanged)
    def document(self): return self._data['document']                # noqa: E704
    @Property('QVariantMap', notify=accountChanged)
    def account_status(self): return self._data['account']           # noqa: E704
    @Property('QVariantMap', notify=positionsChanged)
    def positions(self): return self._data['positions']              # noqa: E704
    @Property('QVariantMap', notify=historyChanged)
    def history(self): return self._data['history']                  # noqa: E704
    @Property('QVariantMap', notify=journalChanged)
    def journal(self): return self._data['journal']                  # noqa: E704
    @Property('QVariantMap', notify=comparisonChanged)
    def comparison(self): return self._data['comparison']            # noqa: E704
    @Property('QVariantMap', notify=qualityChanged)
    def quality(self): return self._data['quality']                  # noqa: E704
    @Property('QVariantMap', notify=diagnosticsChanged)
    def diagnostics(self): return self._data['diagnostics']          # noqa: E704

    _SIGNALS = dict(ui='uiChanged', overview='overviewChanged', markets='marketsChanged', detail='detailChanged',
                    categories='categoriesChanged', cards='cardsChanged', alerts='alertsChanged', accuracy='accuracyChanged',
                    documents='documentsChanged', document='documentChanged', account='accountChanged', positions='positionsChanged',
                    history='historyChanged', journal='journalChanged', comparison='comparisonChanged',
                    quality='qualityChanged', diagnostics='diagnosticsChanged')

    # ------------------------------------------------------------------ plumbing
    @staticmethod
    def _connection():
        state = ConnectionState.NOT_CONFIGURED
        label, detail = STATE_TEXT[state]
        return dict(state=state.value, label=label, detail=detail, source='Archived offline snapshot')

    def _set_ui(self, **kw):
        self._ui = {**self._ui, **kw}
        self.uiChanged.emit()

    def _request(self, kind, fn, *args, **kwargs):
        with self._lock:
            n = self.serial.get(kind, 0) + 1
            self.serial[kind] = n
        self._retry[kind] = (fn, args, kwargs)
        errors = {k: v for k, v in self._ui['errors'].items() if k != kind}
        self._set_ui(loading=sorted(set(self._ui['loading']) | {kind}), errors=errors)
        fut = self.pool.submit(fn, *args, **kwargs)

        def done(f, kind=kind, n=n):
            try:
                value = f.result()
            except M_LedgerError as exc:                            # expected, user-actionable: one line in the log, plain message in the UI
                log.warning('request %s: %s', kind, exc)
                value = {'__error__': str(exc)}
            except Exception as exc:                                # unexpected: surfaced to the UI and logged with a traceback
                log.error('request %s failed: %s\n%s', kind, exc, traceback.format_exc())
                value = {'__error__': f'{type(exc).__name__}: {exc}'}
            if not self._ui.get('closing'):
                self.finished.emit(kind, n, value)

        fut.add_done_callback(done)

    @Slot(str, int, object)
    def _receive(self, kind, n, value):
        if kind.startswith('__action__'):
            self._finish_action(kind[len('__action__'):], value)
            return
        if n != self.serial.get(kind):
            return                                                  # superseded by a newer request of the same kind
        loading = [k for k in self._ui['loading'] if k != kind]
        if isinstance(value, dict) and '__error__' in value:
            self._set_ui(loading=loading, errors={**self._ui['errors'], kind: value['__error__']})
            return
        self._loaded.add(kind)
        if kind == 'cohort_cards':
            self._data['cards'] = value
            self.cardsChanged.emit()
        elif kind == 'index':
            self._ui = {**self._ui, 'indexState': value.get('state', 'unavailable')}
        elif kind in self._data:
            self._data[kind] = value
            getattr(self, self._SIGNALS[kind]).emit()
        if kind == 'overview' and not self._ui['selectedTicker']:
            rows = value.get('cohorts', {}).get('research', {}).get('rows', [])
            if rows:
                self._ui = {**self._ui, 'selectedTicker': rows[0]['ticker']}
                self._request('detail', self.repo.detail, rows[0]['ticker'])
        self._set_ui(loading=loading, ready=self._ui['ready'] or kind == 'overview')

    # ------------------------------------------------------------------ loaders
    def _fetch(self, kind):
        r, a = self.repo, self.account
        if kind == 'overview':
            self._request('overview', r.overview)
        elif kind == 'markets':
            q = self._mq
            self._request('markets', r.markets, q['search'], q['offset'], sort=q['sort'], desc=q['desc'], status=q['status'],
                          category=q['category'], quotes_only=q['quotes_only'], scope=q['scope'])
        elif kind == 'categories':
            self._request('categories', r.categories)
        elif kind == 'detail':
            if self._ui['selectedTicker']:
                self._request('detail', r.detail, self._ui['selectedTicker'])
        elif kind == 'cards':
            self._request('cohort_cards', lambda: dict(research=r.forecast_cards('research'), strategy=r.forecast_cards('strategy')))
        elif kind == 'alerts':
            self._request('alerts', lambda: dict(r.alerts(), candidates=r.candidates(self._cq['offset'], self._cq['sort'])))
        elif kind == 'accuracy':
            self._request('accuracy', r.accuracy)
        elif kind == 'documents':
            self._request('documents', r.documents)
        elif kind == 'account':
            self._request('account', a.status)
        elif kind == 'positions':
            q = self._pq
            self._request('positions', a.positions, q['tab'], q['search'], q['sort'], q['desc'], q['offset'])
        elif kind == 'history':
            q = self._hq
            self._request('history', a.history, q['kind'], q['search'], q['sort'], q['desc'], q['offset'])
        elif kind == 'journal':
            self._request('journal', a.journal, self._jq['search'])
        elif kind == 'comparison':
            self._request('comparison', a.comparison)
        elif kind == 'quality':
            self._request('quality', a.data_quality)
        elif kind == 'diagnostics':
            self._request('diagnostics', environment_report)

    @Slot()
    def load(self):
        """Startup: build the derived index off-thread, then load the first page."""
        self._request('index', self.repo.ensure_index)
        self._request('account', self.account.status)
        self._request('overview', self.repo.overview)
        self._fetch('markets')
        self._fetch('categories')

    @Slot(str)
    def navigate(self, page):
        if page not in PAGES:
            return
        self._set_ui(page=page)
        app_settings.save({**self.settings, 'last_page': page})
        if page in ('Research', 'Strategy'):
            self._ui = {**self._ui, 'cohort': 'research' if page == 'Research' else 'strategy'}
            self._pick_first_for(self._ui['cohort'])
        for kind in PAGE_DATA[page]:
            if kind not in self._loaded and not (kind in ('cards',) and 'cohort_cards' in self._loaded):
                self._fetch(kind)

    def _pick_first_for(self, cohort):
        """Research/Strategy pages need a selected forecast of that cohort."""
        cards = self._data['cards'].get(cohort) or []
        tickers = [c['ticker'] for c in cards]
        if cards and self._ui['selectedTicker'] not in tickers:
            self.select(cards[0]['ticker'])

    @Slot()
    def refresh(self):
        """Re-read the current page's data. Does not touch the network (there is none)."""
        self._loaded.clear()
        self.repo.ensure_index()
        for kind in PAGE_DATA.get(self._ui['page'], []):
            self._fetch(kind)
        self._fetch('overview')
        self.toast.emit('Reloaded the local snapshot. It is still the same archived data.', 'info')

    @Slot(str)
    def retry(self, kind):
        item = self._retry.get(kind)
        if item:
            self._request(kind, item[0], *item[1], **item[2])

    # ------------------------------------------------------------------ markets
    def _requery_markets(self, **changes):
        self._mq.update(changes)
        self._fetch('markets')

    @Slot(str)
    def search(self, text):
        self._requery_markets(search=text.strip(), offset=0)

    @Slot(str)
    def sortMarkets(self, key):
        cur = self._data['markets']
        desc = (not cur.get('desc')) if cur.get('sort') == key else None
        self._requery_markets(sort=key, desc=desc, offset=0)

    @Slot(str, str)
    def filterMarkets(self, name, value):
        if name == 'quotes_only':
            self._requery_markets(quotes_only=(value == 'true'), offset=0)
        elif name in ('status', 'category', 'scope'):
            self._requery_markets(**{name: value if value else None, 'offset': 0})

    @Slot()
    def resetMarketFilters(self):
        self._mq.update(search='', offset=0, sort=None, desc=None, status='any', category='any', quotes_only=False, scope=None)
        self._fetch('markets')

    @Slot(int)
    def pageMarkets(self, delta):
        m = self._data['markets']
        self._requery_markets(offset=max(0, int(m.get('offset', 0)) + 50 * delta))

    @Slot(int)
    def gotoMarketPage(self, page):
        m = self._data['markets']
        page = max(1, min(int(page), int(m.get('pages', 1))))
        self._requery_markets(offset=(page - 1) * 50)

    @Slot(str)
    def select(self, ticker):
        if not ticker:
            return
        self._ui = {**self._ui, 'selectedTicker': ticker}
        self.uiChanged.emit()
        self._fetch('detail')

    # ------------------------------------------------------------------ alerts / candidates
    @Slot(int)
    def pageCandidates(self, delta):
        self._cq['offset'] = max(0, self._cq['offset'] + 30 * delta)
        self._fetch('alerts')

    @Slot(str)
    def sortCandidates(self, key):
        self._cq.update(sort=key, offset=0)
        self._fetch('alerts')

    # ------------------------------------------------------------------ documents
    @Slot(str)
    def openDocument(self, name):
        self._request('document', self.repo.document, name)

    # ------------------------------------------------------------------ account views
    def _requery(self, q, kind, **changes):
        q.update(changes)
        self._fetch(kind)

    @Slot(str)
    def setPositionsTab(self, tab):
        self._requery(self._pq, 'positions', tab=tab, offset=0, sort=None, desc=None)

    @Slot(str)
    def searchPositions(self, text):
        self._requery(self._pq, 'positions', search=text.strip(), offset=0)

    @Slot(str)
    def sortPositions(self, key):
        cur = self._data['positions']
        self._requery(self._pq, 'positions', sort=key, desc=((not cur.get('desc')) if cur.get('sort') == key else None), offset=0)

    @Slot(int)
    def pagePositions(self, delta):
        self._requery(self._pq, 'positions', offset=max(0, self._pq['offset'] + 50 * delta))

    @Slot(str)
    def setHistoryKind(self, kind):
        self._requery(self._hq, 'history', kind=kind, offset=0, sort=None, desc=None)

    @Slot(str)
    def searchHistory(self, text):
        self._requery(self._hq, 'history', search=text.strip(), offset=0)

    @Slot(str)
    def sortHistory(self, key):
        cur = self._data['history']
        self._requery(self._hq, 'history', sort=key, desc=((not cur.get('desc')) if cur.get('sort') == key else None), offset=0)

    @Slot(int)
    def pageHistory(self, delta):
        self._requery(self._hq, 'history', offset=max(0, self._hq['offset'] + 50 * delta))

    @Slot(str)
    def searchJournal(self, text):
        self._requery(self._jq, 'journal', search=text.strip())

    def _after_account_change(self):
        self._loaded -= {'positions', 'history', 'journal', 'comparison', 'quality', 'account'}
        for kind in ('account', 'positions', 'history', 'journal', 'comparison', 'quality'):
            if kind in PAGE_DATA.get(self._ui['page'], []) or kind in ('account', 'quality'):
                self._fetch(kind)

    def _action(self, name, fn, *args):
        def run():
            return fn(*args)
        fut = self.pool.submit(run)

        def done(f):
            try:
                result = f.result()
                result = dict(result or {}, ok=True)
            except Exception as exc:
                log.warning('action %s failed: %s', name, exc)
                result = dict(ok=False, error=str(exc))
            if not self._ui.get('closing'):
                self.finished.emit('__action__' + name, 0, result)

        fut.add_done_callback(done)

    def _finish_action(self, name, result):
        if result.get('ok'):
            summary = result.get('summary') or 'Saved'
            kind = 'warn' if (result.get('rejected') or result.get('conflict')) else 'ok'
            self.toast.emit(summary, kind)
            self._after_account_change()
        else:
            self.toast.emit(result.get('error', 'The action failed'), 'error')
        self.actionDone.emit(name, result)

    @Slot(str, str, str)
    def importFile(self, url_or_path, kind, price_unit):
        path = QUrl(url_or_path).toLocalFile() if url_or_path.startswith('file:') else url_or_path
        self._action('import', self.account.import_file, path, kind or None, price_unit or 'dollars')

    @Slot(str, str, str, str, str, str, str)
    def recordFill(self, ticker, side, action, count, price_cents, fee, when):
        self._action('record', self.account.record_fill, ticker, side, action, count, price_cents, fee, when or None)

    @Slot(str, str, str)
    def voidRecord(self, table, record_id, reason):
        self._action('void', self.account.void_record, table, record_id, reason)

    @Slot(int, str, str, str, str, str, str, str, str)
    def saveJournal(self, entry_id, title, body, ticker, entry_type, tags, planned_side, planned_price_cents, my_prob_pct):
        self._action('journal', self.account.journal_save, entry_id or None, title, body, ticker, entry_type, tags, planned_side,
                     planned_price_cents, my_prob_pct)

    @Slot(int)
    def deleteJournal(self, entry_id):
        self._action('journal_delete', self.account.journal_delete, entry_id)

    # ------------------------------------------------------------------ keyboard / dialog plumbing
    @Slot()
    def requestSearchFocus(self):
        if self._ui['page'] != 'Markets':
            self.navigate('Markets')
        self.focusSearch.emit()

    @Slot(int)
    def stepPage(self, delta):
        self.stepPageRequested.emit(delta)

    @Slot(str)
    def openDialog(self, name):
        self.dialogRequested.emit(name)

    # ------------------------------------------------------------------ desktop helpers
    @Slot(str)
    def copyText(self, text):
        QGuiApplication.clipboard().setText(text)
        self.toast.emit('Copied to clipboard', 'ok')

    @Slot(str)
    def openLink(self, url):
        if not self.repo.safe_url(url):
            self.toast.emit('Only plain http(s) links can be opened.', 'warn')
            return
        if not self._ui['allowLinks']:
            QGuiApplication.clipboard().setText(url)
            self.toast.emit('Opening links is off (Settings). The link was copied instead.', 'info')
            return
        QDesktopServices.openUrl(QUrl(url))

    @Slot(bool)
    def setAllowLinks(self, allow):
        self.settings['allow_open_links'] = bool(allow)
        app_settings.save(self.settings)
        self._set_ui(allowLinks=bool(allow))

    def close(self):
        self._ui['closing'] = True
        self.pool.shutdown(wait=True, cancel_futures=True)
