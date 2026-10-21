"""Account views for the desktop: ledger reports turned into display data. OFFLINE ONLY.

* Reads/writes only the dedicated ``account.db`` (or the disposable sample DB) via ``kh.ledger``.
* Contains no network code, no credentials and no order capability. ``authorization`` is a constant
  that says so; enabling a real Kalshi connection is a separate, explicitly approved project.
* Anything unknown is the string 'Unavailable'. A real zero is '$0.00'.
"""
from __future__ import annotations

import time
import uuid
from decimal import Decimal
from pathlib import Path

from kh.ledger import compare as L_compare, engine as E, importers, models as M, sample as L_sample
from kh.ledger.store import AccountStore

from . import paths
from .formatting import cents, money, quantity, stamp, short_stamp, age_text, to_decimal, UNAVAILABLE, DASH

PAGE = 50
AUTHORIZATION = dict(
    api_access=False, credentials_stored=False, mode='Not connected',
    detail=('Kalshi account access has not been authorized. This build reads only trades and settlements that you '
            'import or record yourself. It cannot place, change or cancel orders.'))
SAMPLE_BANNER = 'SAMPLE DATA · not your account · hypothetical figures'


def _sort_page(rows, sort, desc, offset, size=PAGE):
    if sort:
        present = [r for r in rows if r['k'].get(sort) is not None]
        absent = [r for r in rows if r['k'].get(sort) is None]
        present.sort(key=lambda r: r['k'][sort], reverse=bool(desc))
        rows = present + absent
    total = len(rows)
    return rows[offset:offset + size], total


def _clean(rows):
    return [{k: v for k, v in r.items() if k != 'k'} for r in rows]


class AccountService:
    def __init__(self, repo, *, sample=False, db_path=None, clock=time.time):
        self.repo = repo
        self.sample = bool(sample)
        self.path = Path(db_path) if db_path else (paths.sample_dir() / 'account.db' if sample else paths.account_db_path())
        self.clock = clock

    # ------------------------------------------------------------------ plumbing
    def prepare(self):
        """Create the sample DB (regenerated each launch). The real DB is created lazily on first write."""
        if self.sample:
            paths.assert_writable_path(self.path)
            L_sample.build_sample_store(self.path).close()

    def _open(self, create=False):
        if not self.path.exists() and not create:
            return None
        paths.assert_writable_path(self.path)
        return AccountStore(self.path)

    def _writer(self) -> AccountStore:
        store = self._open(create=True)
        assert store is not None
        return store

    def _report(self, store):
        if store is None:
            return E.compute([], [], [])
        # Archived quotes are never used to mark open positions (see freshness.mark_usable).
        return E.compute(store.fills(), store.settlements(), store.cash(), marks=None, now=self.clock())

    # ------------------------------------------------------------------ status
    def status(self):
        store = self._open()
        try:
            counts = store.counts() if store else dict(fills=0, settlements=0, cash=0, conflicts=0, rejects=0, voids=0, journal=0, batches=0)
        finally:
            if store:
                store.close()
        has = bool(counts['fills'] or counts['settlements'] or counts['cash'])
        return dict(sample=self.sample, banner=SAMPLE_BANNER if self.sample else '', has_data=has, counts=counts,
                    authorization=AUTHORIZATION, path=str(self.path),
                    mode_label='SAMPLE DATA' if self.sample else ('LOCAL RECORDS' if has else 'NO ACCOUNT DATA'))

    # ------------------------------------------------------------------ positions
    def positions(self, tab='open', search='', sort=None, desc=None, offset=0):
        store = self._open()
        try:
            rep = self._report(store)
            counts = store.counts() if store else {}
            sub_cent = self._sub_cent(store) if store else 0
        finally:
            if store:
                store.close()
        titles = self.repo.market_titles(list(rep.markets))
        cards = self.repo.all_forecast_cards()
        researched = {c['ticker'] for c in cards}
        refs = self.repo.latest_quotes([m.ticker for m in rep.open_positions])
        now = self.clock()
        q = (search or '').lower().split()

        def match(m):
            hay = f'{m.ticker} {titles.get(m.ticker, "")}'.lower()
            return all(t in hay for t in q)

        summary = self._summary(rep, counts, sub_cent)
        if tab == 'open':
            src = [m for m in rep.open_positions if match(m)]
            rows = [self._open_row(m, titles, researched, refs, now) for m in src]
            default = ('cost_basis', True)
        elif tab == 'closed':
            src = [m for m in rep.closed_positions if m.status in ('closed', 'settled') and match(m)]
            rows = [self._closed_row(m, titles, researched) for m in src]
            default = ('closed_ts', True)
        else:
            raise ValueError('tab must be open or closed')
        sort = sort or default[0]
        desc = default[1] if desc is None else desc
        page, total = _sort_page(rows, sort, desc, max(0, int(offset)))
        return dict(tab=tab, rows=_clean(page), total=total, offset=offset, pages=max(1, -(-total // PAGE)),
                    page=int(offset) // PAGE + 1, sort=sort, desc=bool(desc), summary=summary,
                    flags=[f.message for f in rep.flags], empty=not rep.markets)

    @staticmethod
    def _sub_cent(store) -> int:
        """Fills priced below 1 cent: almost always a dollars-vs-cents import mistake (100x too small)."""
        return store.c.execute("SELECT COUNT(*) FROM fills WHERE CAST(price AS REAL) < 0.01").fetchone()[0]

    def _summary(self, rep, counts=None, sub_cent=0):
        none = not rep.markets
        realized = rep.realized_total
        excluded = rep.n_incomplete
        flagged = sum(1 for m in rep.markets.values() if m.flags and not m.incomplete)
        quarantined = (counts or {}).get('conflicts', 0) + (counts or {}).get('rejects', 0)
        parts = []
        if excluded:
            parts.append(f'{excluded} market(s) excluded: incomplete or inconsistent history')
        if flagged:
            parts.append(f'{flagged} market(s) flagged for review')
        if quarantined:
            parts.append(f'{quarantined} quarantined or rejected record(s)')
        if sub_cent:
            parts.append(f'{sub_cent} fill(s) priced below 1¢: check the import unit')
        if any(f.severity in ('warn', 'error') for f in rep.flags):
            parts.append('possible duplicate records')
        note = 'No trades imported' if none else ('; '.join(parts) + ' (see Data quality)' if parts else 'All markets verified')
        return dict(
            realized=money(realized, plus=True) if realized is not None else UNAVAILABLE,
            realized_note=note,
            fees=money(rep.fees_total) if rep.fees_total is not None else UNAVAILABLE,
            open_cost=money(rep.open_cost_basis) if rep.open_cost_basis is not None else UNAVAILABLE,
            open_count=len(rep.open_positions),
            unrealized=UNAVAILABLE,
            unrealized_note=('No open positions' if not rep.open_positions else
                             'Needs a fresh executable quote; only archived quotes exist offline'),
            net_deposits=money(rep.cash_net, plus=True) if rep.cash_count else UNAVAILABLE,
            net_deposits_note=(f'{rep.cash_count} cash record(s); never counted as profit' if rep.cash_count else 'No deposits/withdrawals recorded'),
            equity=UNAVAILABLE, equity_note='Needs your account balance: account not connected',
            closed_count=len([m for m in rep.markets.values() if m.status in ('closed', 'settled')]),
            incomplete=excluded)

    def _flags(self, m):
        return [f.message for f in m.flags]

    def _open_row(self, m, titles, researched, refs, now):
        ref = refs.get(m.ticker)
        if ref and m.side:
            bid = ref['yes_bid'] if m.side == 'yes' else (None if ref['yes_ask'] is None else Decimal(1) - ref['yes_ask'])
            ref_text = (f'Archived exit quote {cents(bid)} · {age_text(now - ref["ts"])} old: not used for P&L'
                        if bid is not None else 'No archived exit quote')
        else:
            ref_text = 'No archived quote'
        return dict(ticker=m.ticker, title=titles.get(m.ticker, ''), side=(m.side or '').upper(), qty=quantity(m.qty),
                    avg_entry=cents(m.avg_entry), cost_basis=money(m.cost_basis), realized=money(m.realized, plus=True) if m.realized is not None else UNAVAILABLE,
                    fees=money(m.fees), unrealized=UNAVAILABLE, unrealized_reason=m.unrealized_reason or 'Needs a fresh executable quote',
                    reference=ref_text, opened=short_stamp(m.first_ts), researched=m.ticker in researched,
                    incomplete=m.incomplete, flags=self._flags(m), status='INCOMPLETE' if m.incomplete else 'OPEN',
                    k=dict(ticker=m.ticker, qty=m.qty, cost_basis=m.cost_basis, avg_entry=m.avg_entry, fees=m.fees,
                           opened=m.first_ts, realized=m.realized))

    def _closed_row(self, m, titles, researched):
        end = m.settled_ts or m.last_ts
        result = (m.result or '').upper() if m.status == 'settled' else ''
        outcome = ('INCOMPLETE' if m.incomplete else ('WON' if m.realized and m.realized > 0 else ('LOST' if m.realized and m.realized < 0 else 'FLAT')))
        mixed = len(m.sides) > 1     # traded on both YES and NO: one average would blend two different prices
        bad = m.incomplete or mixed  # an incomplete or two-sided history makes entry/exit averages untrustworthy: show nothing, not a guess
        return dict(ticker=m.ticker, title=titles.get(m.ticker, ''), status='INCOMPLETE' if m.incomplete else m.status.upper(), result=result,
                    outcome=outcome, qty=quantity(m.opened_qty) if not m.incomplete else DASH,
                    avg_entry=cents(m.avg_entry_price) if not bad else DASH, avg_exit=cents(m.avg_exit_price) if not bad else DASH,
                    fees=money(m.fees), realized=money(m.realized, plus=True) if m.realized is not None else UNAVAILABLE,
                    opened=short_stamp(m.first_ts), closed=short_stamp(end), researched=m.ticker in researched,
                    incomplete=m.incomplete, flags=self._flags(m) + (['Traded on both YES and NO: entry/exit averages are not shown because they would blend the two sides.'] if mixed and not m.incomplete else []),
                    record_pnl=money(m.record_pnl, plus=True) if m.record_pnl is not None else '',
                    k=dict(ticker=m.ticker, qty=m.opened_qty, avg_entry=m.avg_entry_price, avg_exit=m.avg_exit_price, fees=m.fees,
                           realized=m.realized, closed_ts=end, opened=m.first_ts))

    # ------------------------------------------------------------------ history
    def history(self, kind='transactions', search='', sort=None, desc=None, offset=0):
        store = self._open()
        try:
            fills = store.fills() if store else []
            all_fills = store.fills(include_voided=True) if store else []
            void_ids = store.voided('fills') if store else set()
            settles = store.settlements() if store else []
            cash = store.cash() if store else []
            rep = E.compute(fills, settles, cash)
        finally:
            if store:
                store.close()
        q = (search or '').lower().split()
        rows = []
        if kind == 'transactions':
            for f in all_fills:
                voided = f.fill_id in void_ids
                gross = f.count * f.price
                effect = (-gross if f.action == 'buy' else gross) - f.fee
                rows.append(dict(type='Fill (voided)' if voided else 'Fill', ts=f.ts, when=stamp(f.ts), ticker=f.ticker,
                                 description=('VOIDED · not counted · ' if voided else '') + f'{f.action.capitalize()} {quantity(f.count)} {f.side.upper()} @ {cents(f.price)}',
                                 cash=DASH if voided else money(effect, plus=True), fee=DASH if voided else money(f.fee), source=f.source, ref=f.fill_id,
                                 k=dict(ts=f.ts, ticker=f.ticker, cash=Decimal(0) if voided else effect, fee=Decimal(0) if voided else f.fee, type='Fill')))
            for s in settles:
                effect = s.revenue - s.fee
                rows.append(dict(type='Settlement', ts=s.settled_ts, when=stamp(s.settled_ts), ticker=s.ticker,
                                 description=f'Settled {s.market_result.upper()} · payout {money(s.revenue)}',
                                 cash=money(effect, plus=True), fee=money(s.fee), source=s.source, ref=s.settlement_id,
                                 k=dict(ts=s.settled_ts, ticker=s.ticker, cash=effect, fee=s.fee, type='Settlement')))
            for c in cash:
                rows.append(dict(type=c.kind.capitalize(), ts=c.ts, when=stamp(c.ts), ticker='', description=c.note or c.kind.capitalize(),
                                 cash=money(c.amount, plus=True), fee=DASH, source=c.source, ref=c.txn_id,
                                 k=dict(ts=c.ts, ticker='', cash=c.amount, fee=None, type=c.kind.capitalize())))
            rows = [r for r in rows if all(t in f'{r["type"]} {r["ticker"]} {r["description"]} {r["ref"]} {r["source"]}'.lower() for t in q)]
            default = ('ts', True)
        elif kind == 'settlements':
            for s in settles:
                m = rep.markets.get(s.ticker)
                rows.append(dict(ticker=s.ticker, when=stamp(s.settled_ts), result=s.market_result.upper(), payout=money(s.revenue),
                                 fee=money(s.fee), realized=(money(m.realized, plus=True) if m and m.realized is not None else UNAVAILABLE),
                                 incomplete=bool(m and m.incomplete), flags=[f.message for f in (m.flags if m else [])],
                                 source=s.source, ref=s.settlement_id,
                                 k=dict(ts=s.settled_ts, ticker=s.ticker, payout=s.revenue, realized=(m.realized if m else None))))
            rows = [r for r in rows if all(t in f'{r["ticker"]} {r["result"]} {r["ref"]}'.lower() for t in q)]
            default = ('ts', True)
        else:
            raise ValueError('kind must be transactions or settlements')
        sort = sort or default[0]
        desc = default[1] if desc is None else desc
        page, total = _sort_page(rows, sort, desc, max(0, int(offset)))
        return dict(kind=kind, rows=_clean(page), total=total, offset=offset, pages=max(1, -(-total // PAGE)),
                    page=int(offset) // PAGE + 1, sort=sort, desc=bool(desc), empty=not (all_fills or settles or cash))

    # ------------------------------------------------------------------ data quality
    def data_quality(self):
        store = self._open()
        try:
            if store is None:
                return dict(items=[], conflicts=[], rejects=[], batches=[], counts={}, ok=True, empty=True)
            rep = self._report(store)
            items = [dict(level=f.severity, message=f.message) for f in rep.flags]
            for m in rep.markets.values():
                items += [dict(level=f.severity, message=f.message) for f in m.flags]
            conflicts = [dict(table=c['table_name'], record=c['record_id'], when=stamp(c['ts'])) for c in store.conflicts()]
            rejects = [dict(line=r['line'], reason=r['reason'], when=stamp(r['ts'])) for r in store.rejects()]
            batches = [dict(when=stamp(b['ts']), kind=b['kind'], source=b['source'], label=b['label'] or '', total=b['n_total'], new=b['n_new'],
                            dup=b['n_dup'], conflict=b['n_conflict'], rejected=b['n_rejected']) for b in store.batches()[:20]]
            counts = store.counts()
            n_sub = self._sub_cent(store)
        finally:
            if store:
                store.close()
        if n_sub:
            items.append(dict(level='warn', message=f'{n_sub} fill(s) are priced below 1¢. If the file was in dollars but imported as cents, those prices are 100x too small: void them and re-import with the right unit.'))
        for c in conflicts:
            items.append(dict(level='error', message=f'Conflicting duplicate of {c["table"]} record {c["record"]}: kept the original, ignored the new copy.'))
        return dict(items=items, conflicts=conflicts, rejects=rejects, batches=batches, counts=counts,
                    ok=not any(i['level'] == 'error' for i in items), empty=False)

    # ------------------------------------------------------------------ writes (local files only)
    def import_file(self, path, kind=None, price_unit='dollars', tz='America/Chicago'):
        paths_ok = Path(path).expanduser()
        if not paths_ok.is_file():
            raise M.LedgerError(f'No such file: {path}')
        store = self._writer()
        try:
            res = importers.import_file(store, paths_ok, kind=kind or None, price_unit=price_unit, tz=tz)
            return dict(summary=res.summary(), new=res.n_new, dup=res.n_dup, conflict=res.n_conflict, rejected=res.n_rejected,
                        rejects=[dict(line=l, reason=r) for l, r in res.rejected[:10]])
        finally:
            store.close()

    def record_fill(self, ticker, side, action, count, price_cents, fee, when=None):
        """Record a trade the owner already executed elsewhere. This NEVER places an order."""
        # A unique id per manual entry: two genuine identical trades in the same minute must both be recorded.
        raw = dict(fill_id='man:' + uuid.uuid4().hex, ticker=ticker, side=side, action=action, count=count, price=price_cents, fee=fee or '0',
                   ts=when or time.time(), note='manual entry')
        fill = M.make_fill(raw, price_unit='cents', source='manual')
        store = self._writer()
        try:
            res = store.add_fills([fill], source='manual', label='manual entry')
            return dict(summary=res.summary())
        finally:
            store.close()

    def void_record(self, table, record_id, reason):
        store = self._open()
        if store is None:
            raise M.LedgerError('There is no account data to change')
        try:
            store.void(table, record_id, reason)
        finally:
            store.close()

    # ------------------------------------------------------------------ journal
    def journal(self, search='', ticker=None):
        store = self._open()
        if store is None:
            return dict(entries=[], total=0, empty=True)
        try:
            entries = store.journal(query=search or None, ticker=ticker or None)
        finally:
            store.close()
        cards = {c['ticker']: c for c in self.repo.all_forecast_cards()}
        out = []
        for e in entries:
            link = cards.get(e['ticker']) if e['ticker'] else None
            out.append(dict(e, type_label={'note': 'Note', 'pre_trade': 'Before trade', 'post_trade': 'After trade'}.get(e['entry_type'], e['entry_type']),
                            when=stamp(e['created']), updated_text=stamp(e['updated']), edited=e['revisions'] > 1,
                            planned=(f"{e['planned_side'].upper()} @ {cents(to_decimal(e['planned_price']))}" if e['planned_side'] and e['planned_price'] else ''),
                            my_prob_text=(f"{Decimal(e['my_prob']) * 100:.0f}%" if e['my_prob'] else ''),
                            research_note=(f"Grok recorded {link['side'].upper()} · P(YES) {link['probability']} · {link['cohort_label']}" if link else '')))
        return dict(entries=out, total=len(out), empty=False)

    def journal_save(self, entry_id, title, body, ticker, entry_type, tags, planned_side, planned_price_cents, my_prob_pct):
        pp = None
        if planned_price_cents not in (None, ''):
            pp = M.dec(planned_price_cents, 'planned price') / 100
        prob = None
        if my_prob_pct not in (None, ''):
            prob = M.dec(my_prob_pct, 'my probability') / 100
        store = self._writer()
        try:
            if entry_id:
                store.journal_revise(int(entry_id), title=title, body=body, tags=tags, planned_side=planned_side or None,
                                     planned_price=pp, my_prob=prob)
                return dict(id=int(entry_id))
            fid = None
            if ticker:
                cards = [c for c in self.repo.all_forecast_cards() if c['ticker'] == ticker]
                fid = cards[0]['id'] if cards else None
            return dict(id=store.journal_add(title=title, body=body, ticker=ticker or None, entry_type=entry_type or 'note', tags=tags,
                                             forecast_id=fid, planned_side=planned_side or None, planned_price=pp, my_prob=prob))
        finally:
            store.close()

    def journal_delete(self, entry_id):
        store = self._open()
        if store is None:
            return
        try:
            cur = next((j for j in store.journal() if j['id'] == int(entry_id)), None)
            if cur:
                store.journal_revise(cur['id'], title=cur['title'], body=cur['body'], tags=cur['tags'], planned_side=cur['planned_side'],
                                     planned_price=cur['planned_price'], my_prob=cur['my_prob'], deleted=True)
        finally:
            store.close()

    # ------------------------------------------------------------------ comparison with Grok's recorded research
    def comparison(self):
        store = self._open()
        try:
            rep = self._report(store)
            journal = store.journal() if store else []
        finally:
            if store:
                store.close()
        cards = self.repo.all_forecast_cards()
        titles = self.repo.market_titles({c['ticker'] for c in cards} | set(rep.markets))
        rows = []
        for r in L_compare.compare(rep, cards, journal):
            for f in r['research']:
                rows.append(dict(
                    ticker=r['ticker'], title=titles.get(r['ticker'], ''), cohort_label=f['cohort_label'],
                    research_side=f['side'].upper(), research_p=f"{f['prob_yes'] * 100:.1f}%", research_when=stamp(f['ts']),
                    paper_price=cents(f['paper_price']), paper_status=('Open · paper' if f['outcome'] is None else 'Resolved · paper'),
                    traded=r['traded'], my_side=(r.get('actual_side') or '').upper() or (DASH if not r['traded'] else 'closed'),
                    relation={'same_side': 'Same side as research', 'opposite_side': 'Opposite side to research',
                              'research_only': 'You did not trade this' if not r['traded'] else 'n/a'}[f['relation']],
                    relation_code=f['relation'], my_entry=cents(r.get('actual_avg_entry')) if r['traded'] else DASH,
                    lag=(age_text(abs(f['my_entry_after_seconds'])) + (' after' if f['my_entry_after_seconds'] >= 0 else ' before') + ' research'
                         if f['my_entry_after_seconds'] is not None else DASH),
                    my_actual=(money(r.get('actual_realized'), plus=True) if r['traded'] and r.get('actual_realized') is not None
                               else (UNAVAILABLE if r['traded'] else DASH)),
                    my_status=r.get('actual_status', '').upper() if r['traded'] else DASH,
                    my_estimates=', '.join(f"{Decimal(j['my_prob']) * 100:.0f}%" for j in r['journal_estimates'])))
        return dict(rows=rows, total=len(rows), empty=not rep.markets,
                    note='Actual results come from your ledger. Paper entries come from Grok\'s recorded research. They are never added together, '
                         'and an unresolved market has no winner.')
