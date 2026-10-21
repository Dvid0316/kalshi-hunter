# Troubleshooting

Everything here is read-only diagnosis. **Never run `start.sh`, `supervise.sh` or `run.py`** on this machine:
those start the legacy cloud scanner (see the warning at the top of `SETUP.md`). The desktop application is
started only with `./launch.sh`.

## First moves

```bash
cd /home/dave/kalshi-hunter-dev/workspace
./setup.sh                    # environment report: python, venv, PySide6, snapshot, evidence hash
./launch.sh --diagnose        # JSON report: versions, paths, display, problems
tail -n 50 var/log/kalshi-hunter.log
```

The log rotates at 1 MB × 4 (`var/log/kalshi-hunter.log`). Qt/QML warnings are captured into the same file.

## “It doesn’t start” (exit code 4)

`launch.sh` exits 4 when a prerequisite is missing and, when `notify-send` exists, shows a desktop
notification pointing at the same cause. Run `./setup.sh` to see which of these it is:

| Report line | Fix |
| --- | --- |
| `MISSING no .venv` | `./setup.sh --create-venv` (reuses a host PySide6, no download) |
| `MISSING PySide6 is not importable` | `./setup.sh --install-deps` (needs network) or install PySide6 on the host |
| `MISSING data/kalshi.db` | Restore the snapshot from the handoff archive. The app never rebuilds it — it is read-only evidence. |

## “Kalshi Hunter is already running” (exit code 3)

A second window is refused deliberately. Close the existing window, or if a previous run was killed
(`kill -9`), just start it again: a lock left by a dead process is detected and recovered automatically
(this is covered by a test).

To find a forgotten instance without starting anything:

```bash
pgrep -af 'desktop.app' || echo "none running"
```

## A page shows “Could not load …” with a Retry button

One data domain failed (usually the personal ledger). The other pages keep working. Common cases:

- **“The personal ledger file … cannot be opened … It was not modified”** — `var/account.db` is not a valid
  SQLite file (disk corruption, or an interrupted copy). The app refuses to touch it. Restore a backup, or move
  it aside and start a fresh ledger:
  ```bash
  mv var/account.db var/account.db.bad-$(date +%Y%m%d)   # your own decision, nothing is deleted for you
  ```
  Nothing under `var/` is evidence; it is your ledger, cache and logs only.
- **A damaged `var/settings.json`** — the app falls back to defaults and keeps the old file as
  `var/settings.json.corrupt`. Delete that copy once you have looked at it.

## Search feels slow the first time

The first query builds a derived index in `var/cache/market_index.db` (~90 MB, a few seconds). Later launches
reuse it; it is rebuilt automatically when the snapshot changes. It is disposable — deleting `var/cache/` costs
only the rebuild. If the index cannot be built (read-only `var/`), the app falls back to direct read-only
queries and is merely slower.

## “All markets verified” is missing / a market is INCOMPLETE

That is the point. The ledger prints a headline number only when the history is complete and consistent. Open
**Data quality** (Positions / Evidence) for the reason: conflicting duplicate, rejected row, void, a settlement
revenue that disagrees with the fills, a fill dated after settlement, a void that paid nothing, or a price below
1¢ (usually a dollars file imported as cents). Fix the underlying record by importing the missing fills or
correcting with new records — the old ones stay visible for audit.

## A market trades on both YES and NO

Entry and exit averages show `—` on purpose: one average over two different sides would be meaningless. The
realized result is still shown when the history is complete.

## The window looks cramped

Below 1180 px the sidebar collapses to icons; below 1060 px pages stack into one column and scroll. Minimum
usable size is 1100×760 (tested). `--compact` forces that size. Text contrast meets WCAG AA on every surface
(tested from the theme colours).

## Display / platform problems

- Wayland: run normally; Qt picks the platform up. To force a backend for one run:
  `QT_QPA_PLATFORM=wayland ./launch.sh` or `QT_QPA_PLATFORM=xcb ./launch.sh`.
- Headless/CI: `QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software ./launch.sh --smoke`.
- If a run produces no output at all, you are probably piping through `head`/`tail` and losing the exit code:
  write to a file and echo `$?` first.

## Verifying it is safe and unchanged

```bash
./launch.sh --smoke                        # every page, must print {"qml_warnings": [], "ui_errors": {}, "problems": []}
./launch.sh --interaction-test             # drives search, sort, paging, keyboard, journal
./setup.sh --tests                         # 393 tests, includes zero-network and evidence-hash checks
find data research strategies -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum
# expected: 20bb34ab867b21d6cb5f76face37915eb12225873143ea720acf0fa0c59ae6e5
```

If that hash ever differs, **stop and investigate** before doing anything else: it means the preserved
evidence changed, which this application is built not to do.

## Something is running that should not be

This application starts no background service and no scanner, and it disables duplicate instances. To confirm
nothing else was left running by an older setup:

```bash
pgrep -af 'run.py|supervise.sh' || echo "no scanner or supervisor running"
systemctl --user list-units 'kalshi*' 2>/dev/null || true
crontab -l 2>/dev/null | grep -i kalshi || echo "no cron entry"
```

Do not start any of them to “fix” anything.