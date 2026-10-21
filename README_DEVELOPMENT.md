Kalshi Hunter — offline Linux desktop (Phases 1–2)

Launch from this directory:

```bash
./launch.sh
```

This is a native PySide6 / Qt Quick desktop application. It uses the isolated `data/kalshi.db` snapshot read-only. It does not launch a scanner, research worker, account session or trading connection. `start.sh` and `supervise.sh` refuse operation in this development build. `run.py` accepts only offline `health` and `validate`; the latter creates a new report under `artifacts/reports/`.

Use Markets to search all 167,233 catalog records; an empty search shows the eight forecast tickers. Quotes have their own as-of time, and markets without quote history show unavailable data. Select a market for its settlement rules and bid/ask history. Research/Strategy rows select their evidence; scroll the evidence pane to read all original source records, including appended corrections. Sources are displayed as text: this build does not fetch them or launch a browser.

New naming, per owner request:

- Track A: Research forecasts (legacy researched B/C).
- Track B: Strategy forecasts (legacy C2; exact `prereg_flb_v1` marker).
- Historical backtests: legacy A, retained separately and INCONCLUSIVE.
- Unclassified records are excluded and counted in Evidence. No cross-cohort aggregate P&L or accuracy is presented.

The snapshot contains three researched demo-origin paper entries, five strategy paper entries, zero settlements, and zero alerts. These are actual preserved records, not actual account positions. Unresolved P&L, actual account P&L, Brier/log loss without outcomes and missing quotes are unavailable, not zero. Account functionality is intentionally absent.

Paper accounting: a purchased binary contract held to binary settlement earns `quantity * (winning-side payout - entry price) - recorded entry fee`. A winning side pays $1 per contract; losing pays $0. Use Decimal for arithmetic and retain recorded fees. No invented exit fee, current fee recomputation, unrealized return, account cost basis or deposit/withdrawal accounting. Nonbinary/void outcomes require a separate explicit policy. Stored settlement P&L is reconciled against inputs; a mismatch suppresses the cohort total and is identified in reports. Existing evidence rows are never repaired in place.

Environment:

- Local `.venv` created with `--system-site-packages`, using existing Python 3.14.7 and PySide6 6.11.2. Nothing installed system-wide or downloaded.
- This is a pragmatic local environment, not a hermetic portable lock. See `environment-observed.json` and `requirements-desktop.txt` for observed versions. Do not blindly install the original cloud freeze.
- To recreate using already-installed host packages: `python3 -m venv --system-site-packages .venv`. A clean machine will need a separately validated project-local dependency installation.
- Native desktop and offscreen software rendering checked. Minimum window: 1100×760 logical pixels; smaller work areas are unsupported. Content can scroll at compact sizes. Screen-reader certification and all GPU/platform combinations remain untested.

Tests:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software ./launch.sh --smoke
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software ./launch.sh --interaction-test
```

`artifacts/` contains milestone test results, screenshots, label-leakage analysis, versioned reports and preservation verification. Independent review is in `../audit/INDEPENDENT_IMPLEMENTATION_REVIEW.md`.

Architecture: QML presentation → QObject bridge → one background executor → per-query read-only SQLite connection. UI only receives plain data; no requests client or credential handling is imported by the desktop. Connections close deterministically; no schema migration/sealing on reads. Search is parameterized, paged 50 results and debounced; late results are discarded by request sequence. Price history comes solely from preserved bid/ask snapshots, with no fabricated prices or interpolation claims. The in-process service is sufficient offline; a separate Unix-socket service is deferred until live ownership is designed in Phase 3.

Known limitations: no live feed or local AI researcher, account reads, notifications, order entry, transfers, automatic resolution, or scanner. Legacy research modules are retained for offline tests, not approved for live use. URL fetch security, atomic queue leases, quote-source freshness, fee policy, no-duplicate ownership, current API compatibility and data-retention policy still gate Phase 3. A bounded local fetch duration in the alert helper does not establish upstream quote age. Old alerts missing secondary rules or fee provenance fail closed. Preserved frozen strategy, research documents and checkpoints keep their original historical wording and hashes; new code uses explicit updated labels and versioned reports.

Phase 3 proposal (NOT STARTED): build replay-tested public-data adapters and a durable research queue, protect source fetching, collect prospective availability/fee/book metadata, introduce freshness-qualified alerts, and define one scanner owner before activation. Leave Grok cloud services unchanged unless separately authorized. Decide controlled handover versus authorized read/export feed; never infer that cloud collection has stopped. Real account access belongs to a later separately authorized phase. Automated trading remains excluded.
