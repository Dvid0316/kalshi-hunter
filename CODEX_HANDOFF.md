# CODEX HANDOFF: Kalshi Hunter (2026-10-21)
**Status: the framework is verified, no advantage has been demonstrated, and Track A is INCONCLUSIVE.** This is research and paper trading only. **There's no trading capability, and none should be added without the owner's (Deividas) separate explicit authorization.**

## No-trading guard
- `kh/api.py` makes GETs only. An allow-list assertion covers `/events`, `/markets`, `/series` and `/exchange/status`, and rejects `portfolio`.
- `tests/test_pricing_reliability.py::test_read_only_guard` checks the order and portfolio paths, and greps all modules for `.post(`, `.delete(` and `create_order`.
- There are no keys, auth or brokerage code. Keep it that way.

## Architecture (one Python service, SQLite)
- `kh/api.py`: public client with throttling and 429 backoff.
- `kh/scanner.py`: every 5 min it pulls all open events and markets, snapshots prices, and runs the structural screens (mutually exclusive sets, threshold ladders).
- `kh/quant.py`: orderbook math (ask = 1 − opposite bid, walking levels, capped at depth), EV and screens.
- `kh/fees.py`: Kalshi taker/maker fee formulas (Jul 7 2026 schedule).
- `kh/auditor.py`: live re-check of depth, ambiguity, close time and worst-case EV.
- `kh/research.py`: queue of screened candidates (3/day) → sourced submissions (live URL checks, contrarian pass, second-hand labels) → paper forecast and auditor → `alerts`.
- `kh/perf.py`: paper fills, `forecast_market` (mid and executable-implied probabilities), resolutions.
- `kh/prereg_flb.py`: frozen forward strategy flb_v1 (`strategies/flb_v1.json` and its hash).
- `kh/integrity.py`: per-row hash chain plus external checkpoint log.
- `kh/db.py`: schema, migrations, append-only triggers.
- `kh/calibration.py`: Brier, log loss, reliability, cluster bootstrap.
- `kh/backtest.py`: Track A builder and runner.
- `kh/validation.py`: three-track report.
- `kh/dashboard.py`: static HTML.
- `run.py`: loop / once / health / validate / claim / submit / pending-alerts / mark-alerted. `start.sh` and `supervise.sh` handle process control (see OPERATIONS.md).

## The three tracks (never pooled)
- **A: mechanical backtest** (`data/backtest.db`; rules sched24, open72 and close24_legacy). Status is **INCONCLUSIVE**: availability at T of the candles and of `expected_expiration_time` can't be verified (ERRATA §4, CANDLE_LIMITATIONS.md, VALIDATION_HANDOFF_v2.md).
- **B: researched-forecast calibration.** 3 forecasts, 0 resolved.
- **C: forward paper fills.** Researched forecasts are in C; the pre-registered flb_v1 is reported separately as C2.

## Conclusions: see research/CONCLUSIONS.md (quoted from independent review 2)
1. The framework is sound, with fixes.
2. The backtest is partly reproducible, and Track A is INCONCLUSIVE.
3. There's no profitable advantage.

## Known issues / to-do
1. **Track B pooling fix PENDING.** `track_b` doesn't exclude `prereg_%` rows. The patch and test are in `research/pending_fixes/` and were verified on a scratch copy. It wasn't applied live because the running loop imports the module. Apply it before any flb_v1 entry resolves (about Oct 22).
2. Track A is INCONCLUSIVE (see above). The "revision" evidence was withdrawn (ERRATA §1).
3. **The original backtest source is missing.** `research/recovery/` is a reviewer's transcription, which is a reconstruction (ERRATA §7). The current `kh/backtest.py` is the corrected version, not the original.
4. The exclusions CSV holds 26 reconstructed candidates, of which at most 11 were deleted (ERRATA §2).
5. flb_v1's `registered_at` field says 12:05; the true time is 12:00:44 CT (ERRATA §3).
6. The running loop's hourly report rewrites `research/validation_report_2026-10-21.md` and `data/validation.json` using intermediate in-memory code. Those aren't authoritative (ERRATA §6). The corrected report is `research/validation_report_2026-10-21_corrected.md`.
7. Bootstrap CIs are series-clustered, but cross-series correlation isn't modeled. Backtest fills are 1-lot at top of book with no depth.
8. Neither the hash-chain checkpoint log nor the archive manifest is anchored off-box. Copy `research/chain_checkpoints.log` somewhere independent.
9. It isn't reboot-persistent (it depends on the watchdog routine).

## Evidence that must not be edited
`research/archive/`, `research/INDEPENDENT_REVIEW_*.md`, `research/INCIDENTS.md`, `research/recovery/`, and the append-only DB tables (enforced by triggers and the hash chain).
