# Phase 1 findings — inspection of the inherited application

Date: 2026-10-21. Inspector: Hermes (Claude Sonnet 5.5). Scope: read-only inspection plus a git checkpoint. No application code changed in this phase.

## 0. Preservation

| Item | Result |
|---|---|
| Checkpoint | tag `checkpoint/pre-hunter-dev-2026-10-21` (commit 9aaf3be) + `git bundle` at `../checkpoints/workspace-pre-hunter-dev.bundle`. Work continues on branch `hunter/complete-app`. |
| Evidence baseline | sha256 of all 45 files under `data/` and `research/`, recorded in `../checkpoints/evidence-baseline-2026-10-21.sha256`. Re-verified identical after running tests, smoke, interaction test and a native Wayland launch. |
| Workspace vs handoff | `data/kalshi.db`, `data/backtest.db` byte-identical to the extracted handoff; `research/` tree identical (`diff -rq`). |
| Running services | None: no scanner/supervisor process, no systemd user unit, no cron entry mentioning Kalshi. |
| Secrets | `.env.example` contains only comments. No credential-like strings in committed files. |

## 1. Prior-agent claims, independently re-verified

| Claim (Codex report) | Verified? | How |
|---|---|---|
| 72 tests pass | Yes | `pytest -q tests` → 72 passed in 23 s (Python 3.14.7). |
| Zero QML warnings, nine pages | Yes | `--smoke` → `{"ready": true, "pages": 9, "qml_warnings": []}`. |
| Interaction test | Yes | `--interaction-test` → passed (nav click, search typing, page cycling). |
| Native launch + screenshots | Yes | `--capture-dir` on live Wayland session produced 9 PNGs. |
| Data isolated from archive | Partly | The *workspace* `data/` is identical to the archive; the app opens it with `mode=ro&immutable=1`. It is a separate copy, not a hardlink. |
| Research/strategy separation | Yes | `kh/cohorts.py` predicates; research (3 rows) and strategy (5 rows) are disjoint; 0 unclassified. |

## 2. What exists

Backend (`kh/`, ~1,300 lines): public-data client with GET-only guard, scanner, fee math, quant, auditor, research queue, paper-fill recorder, hash-chain integrity, backtest, validation. **Nothing in the desktop imports the scanner, API client or research queue.**

Desktop (`desktop/`): PySide6 `Bridge` (QObject) → single-worker `ThreadPoolExecutor` → `Repository` (per-call read-only SQLite connection). QML is one 354-line file, `desktop/qml/Main.qml`, with dense one-line components.

Database (`data/kalshi.db`, 425 MB, `PRAGMA integrity_check` passes per prior audit): 31 scans (≈2.3 h of data), 15,543 events, 167,233 markets, 1,450,618 snapshots, 8 forecasts (3 research, 5 strategy), 4 research rows (1 is an appended correction), **0 resolutions, 0 alerts, 0 research-queue rows, 68 structural candidates (`info_nonexhaustive`), 149-entry hash chain**. Snapshots carry YES bid/ask, NO bid/ask, top-of-book sizes, last, volume, 24h volume, open interest (liquidity is always NULL).

Data facts that constrain the product:
* Price history is **at most 31 points per market, ≈2.3 hours** (20,992 markets have all 31). That is the only genuine timestamped history; longer-range charts would be fabricated.
* Latest snapshot is ~1 h+ old relative to wall-clock at inspection and will only get older. Nothing in the current UI shows snapshot **age**.
* Historical backtest DB (`data/backtest.db`): 594 rows, 1,825 exclusions. Status INCONCLUSIVE per errata.
* Fee-multiplier metadata exists per series (`kv.series`), but it is **never to be used for actual account fees**; actual fees come from fills.

## 3. The nine views as received

| View | State | Notes |
|---|---|---|
| Overview | Functional, partly hard-coded | Metric cards data-driven; "Track A · 3 demo-origin entries" is literal text. Research table clipped by the bottom of the viewport. Chart has no time axis labels or hover. |
| Markets | Functional, thin | Debounced literal search (parameterised, `%`/`_` escaped), 50/page, detail pane. **YES quotes only** (no NO side, no sizes, no spread). No sort, no filters, no sort indicators, no result count, no keyboard navigation. Default list = the 8 forecast tickers. |
| Research | Functional, thin | Row click selects evidence; evidence pane is nested-scroll inside a fixed-height panel and clips. Static explanatory paragraph hard-coded. No probability-vs-market view, no auditor notes, no secondary rules. |
| Strategy | Functional, thin | Same table; static paragraph about flb_v1 hard-coded. |
| Alerts | Honest empty state | Zero alerts in DB. Does not surface the 68 screened candidates (which are *not* alerts but are real preserved screening output). |
| Positions | Placeholder | "Account stays disconnected". No data contract, no schema, no offline mode. |
| History | Functional, thin | Paper entries only. No search, no export, no transaction model. |
| Accuracy | Mixed | Two cards with **hard-coded** "3 paper forecasts · 0 resolved" strings; uncertainty-band chart is data-driven. No Brier/log-loss/reliability rendering path even when outcomes exist. Backtest summary absent. |
| Evidence | Functional | Integrity badge + scan list. Integrity issue text is shown if any. |

## 4. Gaps against the mission (mapped to phases)

Phase 2: componentisation (monolith blocks maintainability); responsive layout (fixed sidebar, 1100×760 minimum, clipping); sort/filter/pagination UI; interactive chart (axes, hover, YES/NO toggle); keyboard shortcuts and focus order; Accessible.* metadata; loading/empty/error states per view with retry; data-driven strings; snapshot-age/staleness display.
Phase 3: NO-side executable quotes, sizes, spread, rules (primary + secondary), market status/result, settlement time, linked research with auditor notes, probability band vs executable break-even, candidate list, historical-backtest summary clearly labelled INCONCLUSIVE.
Phase 4: no account model, no data contract, no journal, no import path. (Must be built offline; no credentials.)
Phase 5: no freshness/connection-state model at all.
Phase 6: tests exist for cohorts/accounting/alerts/reliability but there is no test for GUI state beyond one smoke/interaction run, nothing for the account ledger (doesn't exist), freshness, or evidence immutability at the app level.
Phase 7: `launch.sh` exists; no .desktop entry, icon, log file, single-instance guard, diagnostics, or troubleshooting doc. `.venv` uses `--system-site-packages` (not hermetic).

## 5. Defects and risks found during inspection

1. **Hard-coded snapshot facts in QML** (counts, "demo-origin", "5 paper forecasts · 0 resolved"). They become wrong the moment data changes. → data-driven.
2. **No staleness signal.** "Preserved as of 12:16 CDT" is shown but its age is not; a user could read archived quotes as current. → age + STALE badge, quote-level age.
3. **YES-only quotes** hide the executable NO side, which is the side every recorded forecast actually takes (all 8 are NO). → both sides.
4. **`Repository.detail()` loads all points then downsamples in Python** (fine at 31 points/market; unbounded in a future feed). → SQL-bounded.
5. **Overview recomputes `integrity.verify` on every load** (≈87 ms; acceptable) – cache with checked-at timestamp.
6. **Single-worker executor serialises** all reads; a slow query blocks others. Sequence numbers discard stale results correctly, so this is a latency not correctness issue.
7. **Legacy modules (`kh/research.py`, `kh/scanner.py`, `kh/api.py`) remain importable**; `kh/api.py` can make network GETs. They are not wired into the desktop, but a test should assert that the desktop import graph excludes them. → test.
8. `README_DEVELOPMENT.md` claims minimum window 1100×760 "smaller unsupported"; at narrower widths content simply clips.
9. Time labels are rendered in `America/Chicago` correctly via zoneinfo (the earlier audit's "formatted in machine zone but labelled CT" defect is fixed in the desktop path; not re-verified in legacy `kh/validation.py` text).

## 6. Not changed / preserved

All `data/`, `research/`, `strategies/` bytes. Prior agents' reports under `../audit/`. Frozen strategy and historical wording. Original cohort naming map (new A = research, new B = strategy; historical backtests separate).

## 7. Open uncertainties

* Whether the original cloud scanner (Grok) is still running – unknown and not assumed either way.
* Native screen-reader behaviour, HiDPI scaling and X11 (as opposed to Wayland/offscreen) are untested.
* Kalshi's current API field names and fixed-point price formats have **not** been checked against live docs for the account adapter; no network was used.
