# CONTINUATION — Kalshi Hunter desktop app

_Last updated: 2026-10-21 (after commit `4acf573`). Keep this file current: it is the hand-off note if work stops mid-way._

## Where we are

- Branch `hunter/complete-app`, repo `/home/dave/kalshi-hunter-dev/workspace`.
- Checkpoint of the original received work: commit `9aaf3be`, tag `checkpoint/pre-hunter-dev-2026-10-21`,
  bundle `~/kalshi-hunter-dev/checkpoints/workspace-pre-hunter-dev.bundle`.
- Checkpoint of the interrupted agent's tree: `~/kalshi-hunter-dev/checkpoints/workspace-sonnet-interrupted-2026-10-21.tar.zst`.
- **393 tests pass** (unit + static QML + runtime subprocess tests). Evidence hash unchanged:
  `20bb34ab867b21d6cb5f76face37915eb12225873143ea720acf0fa0c59ae6e5`.
- Evidence is read-only; all writes go under `var/` (`KH_VAR_DIR`). No scanner, no network, no order capability.

## Done

1. Whole app rebuilt on the received backend: 10 pages, dark navy/teal design language, component library,
   keyboard shortcuts, charts, search/sort/filter/pagination, journal, positions, history, comparison,
   accuracy, evidence views. Headless self-test harness (`--smoke`, `--interaction-test`, `--accessibility`).
2. Decimal personal ledger (`kh/ledger/`): append-only store, idempotent imports, voids, conflicts, journal
   revisions, engine with an independent Fraction oracle, sample fixtures, comparison against recorded research.
3. Two independent adversarial reviews (one completed, one interrupted by a provider credit failure whose
   raw result files survive in `~/.hermes/cache/scratch/review/ledger/`). All confirmed defects fixed with
   28 regression tests (`tests/test_review_regressions.py`). See `docs/RECOVERY_REPORT_2026-10-21.md`.

## Remaining (in order)

1. Finish the launcher (`launch.sh`), add a project-local `setup.sh`, and add the "never run a scanner" warning
   header to `SETUP.md`.
2. Finish the icon set and commit `packaging/` (SVG + PNGs done, review pending).
3. Prepare `packaging/kalshi-hunter.desktop` + `packaging/install-desktop-entry.sh` — **do not install**.
4. Write the missing docs the UI points at: `docs/ACCOUNT_DATA_CONTRACT.md`,
   `docs/LIVE_RESEARCH_INTEGRATION.md`, plus `docs/ARCHITECTURE.md`, `docs/TROUBLESHOOTING.md`,
   `docs/KNOWN_LIMITATIONS.md`.
5. Capture final screenshots in **default offline mode** (not sample mode) into `docs/screenshots/`.
6. Re-run the full suite + evidence hash; commit; write the completion report with the approvals list.

## Rules that must not be broken

- Dave places every trade personally. No order placement, no cancellation, no execution code.
- No Kalshi credentials without explicit approval; no connection to Grok's cloud without approval.
- Never modify `data/`, `research/`, `strategies/` (evidence). Check the hash after every test run.
- Never start a scanner or a persistent background service. No system-wide installs without approval.
- Never present hypothetical/paper results as account profit. "Unavailable", never 0, for unknown values.
- Historical backtests are inconclusive; no profitable forecasting advantage has been demonstrated.

## How to verify quickly

```bash
cd /home/dave/kalshi-hunter-dev/workspace
./launch.sh --diagnose                      # environment JSON, makes no changes
./launch.sh --smoke --screenshots /tmp/kh   # every page, zero QML warnings
./launch.sh --interaction-test --sample-account
.venv/bin/python -m pytest -q -p no:cacheprovider tests   # 393 passed
find data research strategies -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum
```