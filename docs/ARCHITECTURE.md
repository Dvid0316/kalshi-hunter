# Architecture — Kalshi Hunter desktop application

An offline, read-only research viewer plus a personal trading ledger for Kalshi prediction markets.
It **cannot** place, change or cancel an order, it holds no credentials, and it opens no network
connection (both enforced by tests). Everything it shows from the market data is **archived** and labelled
as such; everything about money it shows about *you* comes from records you import or type in yourself.

## Layers

```
   evidence (read-only, never written)
   ┌─────────────────────────────────────────────────────────────┐
   │ data/kalshi.db     167 233 markets · 1.45 M snapshot rows    │  hash-verified after every run
   │ data/backtest.db   legacy backtest tables                    │  20bb34ab… (45 files)
   │ research/*.md      preserved reports, records, JSON exports  │
   └─────────────────────────────────────────────────────────────┘
                    │ open with file:…?mode=ro&immutable=1
                    ▼
   desktop/index.py        derived, disposable cache: var/cache/market_index.db
                           signature = vN:size:mtime:max(snapshots.id); a non-default
                           KH_SNAPSHOT gets its own sha1-named cache file
                    ▼
   desktop/repository.py   every read the UI needs (markets, filters, sort, paging, detail,
                           price points, forecast cards, documents, accuracy, backtests),
                           plus the accounting cross-check of stored paper P&L
   kh/cohorts.py           the two forecast cohorts and their strict, disjoint predicate
   kh/accounting.py        settlement arithmetic used to reconcile stored paper results
                    ▼
   desktop/bridge.py       ONE QObject for QML: Property(notify=) per data domain,
                           ThreadPoolExecutor(2) workers, per-kind serial numbers so a slow
                           stale result can never overwrite a newer one, per-kind errors
                    ▼
   desktop/qml/            Theme.qml (singleton) · 25 components · 10 pages · Main.qml shell
                           summaries, archived-vs-live labels, "—"/"Unavailable" for unknowns
```

The personal ledger runs beside that stack and never mixes with it:

```
   your records (you import or type them)                        paper research (Grok's records)
   ┌───────────────────────────────┐                             ┌──────────────────────────────┐
   │ kh/ledger/models.py  validate │  Decimal only, floats       │ kh/cohorts.py forecast rows  │
   │ kh/ledger/store.py   append-  │  rejected at the boundary   │ kh/perf.py stored outcomes   │
   │   only SQLite + triggers      │                             └──────────────────────────────┘
   │ kh/ledger/engine.py  P&L      │                                          │
   │ kh/ledger/importers.py CSV/JSON│                                        │ compared, never added
   │ kh/ledger/compare.py          │◄──────────── side by side, never summed ─┘
   └───────────────┬───────────────┘
                   ▼
   desktop/account_service.py   UI façade: positions · history · journal · comparison ·
                                data quality · import_file · record_fill · void_record
                   ▼
   var/account.db   (your ledger)          var/sample/account.db  (invented demo data, bannered)
```

## Files

| Path | Role |
| --- | --- |
| `desktop/app.py` | entry point, CLI flags, single-instance lock, window, shutdown |
| `desktop/bridge.py` | the QML-facing QObject; 10-page nav register; actions and dialogs |
| `desktop/repository.py` | all reads over the frozen snapshot; formatting for the UI |
| `desktop/index.py` | the derived market index cache and its signature check |
| `desktop/freshness.py` | age classes (fresh ≤ 600 s, stale ≤ 45 min, archived) and connection state machine |
| `desktop/formatting.py` | `cents()`, `money()`, `quantity()`, `stamp()` — unknown → `Unavailable`/`—` |
| `desktop/paths.py` | `KH_VAR_DIR`, snapshot paths, and `assert_writable_path` (refuses evidence) |
| `desktop/settings.py` | project-local JSON settings (link opening off by default) |
| `desktop/logging_setup.py` | rotating log in `var/log/kalshi-hunter.log` (1 MB × 4) + Qt message capture |
| `desktop/selftest.py` | `--smoke`, `--interaction-test`, screenshots, accessibility audit |
| `kh/ledger/*` | models, append-only store, P&L engine, importers, comparison, sample fixtures |
| `kh/cohorts.py`, `kh/perf.py`, `kh/accounting.py`, `kh/fees.py` | cohort separation and paper-result arithmetic |
| `desktop/qml/` | theme, components, pages, shell |
| `tests/` | 394 tests: unit, oracle/fuzz, static QML + WCAG, runtime subprocess, evidence hash |

## Threading and lifecycle

- The UI thread never runs a query. `Bridge._request(kind, fn, …)` submits work to a 2-worker pool, stamps a
  per-kind serial number, and re-emits on completion; results with a stale serial are dropped. One failing
  domain sets `ui.errors[kind]` (shown as a Retry banner) and never blanks the others.
- Work that must not interleave (imports, journal writes) runs through the same pool and reports via
  `actionDone`, so a slow disk cannot freeze the window.
- Start-up: `QLockFile(var/kalshi-hunter.lock)` — a second instance exits **3** without touching anything
  (a lock left by a killed process is recovered, tested with SIGKILL). A corrupt `var/account.db` produces a
  clear per-page error and is never modified; a corrupt `var/settings.json` is kept as `settings.json.corrupt`.
- Shutdown: SIGTERM/SIGINT → clean exit **0**, lock released, workers drained (`aboutToQuit`).

## Safety invariants (each backed by a test)

| Invariant | How it is enforced |
| --- | --- |
| No network, ever | import-graph test over `desktop/` + `kh/ledger/`; runtime test patches `socket.connect`/`getaddrinfo` to raise and runs the smoke test; static test forbids remote URLs in QML |
| No order capability | static scan for order/credential strings (negated disclaimers such as "cannot cancel orders" are exempt) |
| Evidence untouched | `paths.assert_writable_path` refuses `data/`, `research/`, `strategies/`; the runtime suite hashes all 45 evidence files before and after |
| Money is exact | `Decimal` throughout; floats and ambiguous commas rejected at the record boundary; "Unavailable", never 0, for unknowns |
| No guessed P&L | incomplete or inconsistent history ⇒ `None` ⇒ "Unavailable", with the exclusion disclosed in the headline note |
| Paper ≠ actual | separate stores, separate cohorts, `SAMPLE`/`PAPER` banners, comparison is descriptive and never sums them |
| Records are append-only | SQLite triggers block UPDATE/DELETE on every record table; corrections and voids are new rows |
| Imports are idempotent | canonical content hash per record id; a conflicting duplicate keeps the original and is quarantined |
| Damaged user data is preserved | a corrupt ledger is reported and left byte-identical; a corrupt settings file is renamed, not overwritten |

## Testing strategy

1. **Unit + hand-computed scenarios** for the engine, store and service.
2. **Independent oracle**: a `fractions.Fraction` aggregate-cash-flow model that shares no method with the
   engine; plus mutation checks (injected bugs must fail the tests, then the file is restored byte-identical).
3. **Static QML**: WCAG-AA contrast computed from `Theme.qml` colours on every surface, page/loader coverage,
   no component named like a `QtQuick.Controls` type, honest-labelling rules (no "live" label for archived
   data), no order or credential strings.
4. **Runtime subprocess tests**: real launches — every page, zero QML warnings, interaction and accessibility
   audit (≥ 400 accessible nodes), SIGTERM shutdown, second-instance refusal, killed-process lock recovery,
   corrupt-data recovery, zero network, temp `KH_VAR_DIR` so no test can touch the real ledger.
5. **Evidence integrity**: whole-tree sha256 before and after the suite.

Run everything with `./setup.sh --tests` (or `./launch.sh --smoke` for the UI-only checks).