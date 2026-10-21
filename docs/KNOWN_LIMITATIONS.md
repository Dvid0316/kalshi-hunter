# Known limitations and remaining uncertainties

Honest inventory. Everything here is either by design, currently unreachable with the preserved data, or
waiting on your approval — nothing in this list is a claim that the application is complete.

## By design

1. **Offline.** Market data is the archived snapshot (newest scan: Oct 21, 2026 · 12:16 CDT). No live prices,
   no streaming, and therefore **unrealized P&L is always `Unavailable`** — it needs a fresh executable exit
   quote that does not exist offline. The app never marks positions from archived quotes.
2. **No account connection.** Positions, history and journal work only from records you import or type in.
   Connecting read-only to Kalshi is designed in `docs/ACCOUNT_DATA_CONTRACT.md` §6 and needs your approval.
3. **No trading capability.** No order placement, amendment or cancellation — by construction and by test.
   You execute every trade yourself.
4. **No forecasting advantage has been demonstrated.** Historical backtests are inconclusive; both forecast
   cohorts have too few resolved outcomes for calibration or accuracy figures, so Brier score, log loss and
   calibration curves show `Unavailable` rather than numbers. Paper P&L is hypothetical throughout.
5. **Sample mode is invented data.** `--sample-account` builds demo fixtures in `var/sample/`, always behind a
   banner; it can never touch your ledger.
6. **The three `demo` forecasts** (ids 1–3) are the initial demo run recorded by the previous system: real
   research text, second-hand figures documented in `research/VALIDATION_HANDOFF.md`. They are labelled
   `· demo run` everywhere rather than being reclassified out of Track A.
7. **The application is not a market-data feed.** Its freshness labels (`ARCHIVED`, `STALE`, ages) are about
   the snapshot, not about Kalshi right now.

## Reconciled the strict way (deliberate trade-off)

The ledger prefers “I don’t know” over a confident wrong number. Consequences you may hit with real exports:

- A settlement whose revenue disagrees with the fills by more than half a cent ⇒ that market shows
  `Unavailable` until the fills are corrected. A legitimate export that nets fees into revenue would need the
  fee recorded separately instead.
- A `void` settlement that paid nothing while contracts were held ⇒ `Unavailable` (a void normally refunds cost).
  A payout greater than the held contracts could pay ⇒ `Unavailable`.
- Two settlement records for one market ⇒ `Unavailable` (all their fees are still counted).
- A fill dated after settlement ⇒ `Unavailable`.
- Entry and exit averages are withheld (`—`) for a market traded on both YES and NO.

## Latent issues, not reachable with the current data

Found by the independent reviews and confirmed by inspection; each needs data the archive does not contain.

1. **Chart downsampling**: above ~400 two-sided snapshots the rendered series drops some points before the last
   one and reports the downsampled count. The busiest ticker in the archive has 31 snapshots.
2. **NO-side chart**: the NO series has no explicit null guard; it would print `0.0¢` if a one-sided NO row
   ever existed. The archive has none (`no_*` is NULL exactly when `yes_*` is NULL, and points are filtered to
   two-sided YES).
3. **`yes_bid == 0`** would render `0.0¢`, count as two-sided and appear as a bid with size. The archive has no
   0 or 1.0 prices, so this is untested against real rows and is a semantics risk if Kalshi ever uses 0 for
   “no bid”.
4. **Search case-folding is ASCII-only** (`LIKE`), so non-ASCII titles will not match across case.
5. **Title and category sorts use binary collation** (uppercase sorts before lowercase): deterministic but
   surprising.
6. **`Closed` in “time to close”** is derived from the wall clock, not from the snapshot’s own status field, so
   a market the snapshot calls `active` can display `Closed`.
7. **The backtest verdict** is set by finding the substring `INCONCLUSIVE` in `research/CONCLUSIONS.md` — text
   matching driving a label, brittle if that file is ever reworded.
8. **Unknown-cohort forecasts** are surfaced as a count only, not as a browsable list.
9. **Formatting of absurd stored amounts**: a value above ~10¹² already in the database would be printed as-is
   (record entry rejects such values now, so only legacy rows could contain one). It cannot crash a page.
10. **Single writer assumed**: the app prevents a second instance, but nothing prevents another program from
    writing `var/account.db` concurrently (SQLite WAL).

## Not built / not verified

- No Windows or macOS packaging, no installer, no auto-update. Linux only.
- The desktop menu entry and icons are **prepared, not installed** (`packaging/`, dry-run by default).
- The live research feed is a proposal (`docs/LIVE_RESEARCH_INTEGRATION.md`); nothing was contacted. What the
  cloud environment can actually publish is **unverified** from this machine.
- Verified on this machine only (CachyOS, KDE Wayland, and headless offscreen). No other distribution or GPU
  configuration was tested.
- The P&L engine’s adversarial review is **partial**: the reviewing agent ran out of provider credits before
  writing its final report. Its raw scenario results are preserved under
  `~/.hermes/cache/scratch/review/ledger/`; every failed scenario was re-derived by hand and fixed (see
  `docs/RECOVERY_REPORT_2026-10-21.md`). The data-handling review completed.

## Approvals outstanding

| # | Item | Gate |
| --- | --- | --- |
| 1 | Install the desktop entry + icon (`packaging/install-desktop-entry.sh --yes`) | user-level only, reversible |
| 2 | Read-only Kalshi account connection | design approved? key requested? first sync? |
| 3 | Cloud-side change to publish research batches | design approval, before any cloud work |
| 4 | Any package installed system-wide | explicit approval per package |
| 5 | Deleting or compacting anything in `var/` or the archive | your call; nothing is deleted automatically |