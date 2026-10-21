# CONTINUATION — Kalshi Hunter desktop app

_Last updated: 2026-10-21, after the final verification run. **Status: the build is complete for everything
that can be done locally without your approval.**_

## Where we are

- Branch `hunter/complete-app`, repo `/home/dave/kalshi-hunter-dev/workspace`.
- **393 tests pass** (`./setup.sh --tests`, ~95 s): unit, hand-computed ledger scenarios, a Fraction oracle,
  static QML + WCAG contrast, runtime subprocess launches, accessibility audit, zero-network proof.
- Evidence hash unchanged: `20bb34ab867b21d6cb5f76face37915eb12225873143ea720acf0fa0c59ae6e5`.
- Verified on real KDE Wayland (`QT_QPA_PLATFORM=wayland`, 10 pages, zero QML warnings) and headless offscreen.
- Checkpoints: `9aaf3be` (as received) + tag `checkpoint/pre-hunter-dev-2026-10-21` + bundle; interrupted-tree
  tar in `~/kalshi-hunter-dev/checkpoints/workspace-sonnet-interrupted-2026-10-21.tar.zst`.

## Launch

```bash
cd /home/dave/kalshi-hunter-dev/workspace
./setup.sh          # check the environment (changes nothing)
./launch.sh         # start the application
```

## Done (all of it)

1. **Recovery** — interrupted tree preserved, NameError and comma-parsing defects fixed, every confirmed
   reviewer defect addressed with 28 regression tests. `docs/RECOVERY_REPORT_2026-10-21.md`.
2. **GUI** — 10 pages, dark navy/teal, compact mode below 1180 px, keyboard shortcuts, charts, search/sort/
   filter/paging, honest empty and error states, accessibility audited per page.
3. **Research features** — quotes (YES/NO with sizes), settlement rules, price history where genuine
   timestamps exist, alerts with their caveats, forecast probability bands, linked evidence, archived-vs-live
   labels, cohort separation.
4. **Personal dashboard** — positions (open/closed), history, journal with revisions, comparison against
   recorded research, data quality, Decimal ledger, append-only records, "Unavailable" instead of guesses.
   Account connection deliberately NOT built: `docs/ACCOUNT_DATA_CONTRACT.md` §6.
5. **Live research** — architecture proposal only: `docs/LIVE_RESEARCH_INTEGRATION.md`.
6. **Tests** — see above; evidence hashed before/after.
7. **Linux experience** — `launch.sh` (preflight + notifications), `setup.sh` (project-local, no sudo),
   icon set, desktop entry + installer (**prepared, not installed**), rotating logs, `docs/TROUBLESHOOTING.md`,
   `docs/ARCHITECTURE.md`, `docs/KNOWN_LIMITATIONS.md`.
8. **Screenshots** — `docs/screenshots/` (10 pages, default offline mode, 1440×960).

## Waiting on your approval (nothing done without it)

1. Install the desktop entry + icon: `packaging/install-desktop-entry.sh --yes` (user-level, reversible).
2. Read-only Kalshi account connection (design in `docs/ACCOUNT_DATA_CONTRACT.md` §6).
3. Cloud-side change to publish research batches (design in `docs/LIVE_RESEARCH_INTEGRATION.md`).
4. Any system-wide package.
5. Deleting anything in `var/` or the archive.

## Rules that must not be broken

- Dave places every trade personally. No order placement, cancellation or execution code, ever.
- No Kalshi credentials without explicit approval; no contact with Grok's cloud without approval.
- Never modify `data/`, `research/`, `strategies/`. Check the hash after every test run.
- Never start a scanner or a persistent background service. No system-wide installs without approval.
- Never present hypothetical or paper results as account profit. Unknown ⇒ "Unavailable", never 0.
- No profitable forecasting advantage has been demonstrated; backtests are inconclusive.

## If work resumes

Nothing in the local scope is unfinished. The next actions all require approval (list above). If a defect
appears, start with `./setup.sh`, `./launch.sh --diagnose`, `var/log/kalshi-hunter.log`, then
`./launch.sh --interaction-test` and `./setup.sh --tests`.