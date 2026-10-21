# Recovery report — interrupted session, 2026-10-21

The previous agent (Claude Sonnet 5.5 through OpenRouter) stopped mid-edit when its provider credits ran out.
This report records what was found, what was preserved, what was verified, and what was corrected. Nothing was
discarded or reverted.

## 1. What the interrupted tree contained

`git log`: last committed work `8a4f9b4` (365 tests passing). Uncommitted at the interruption:

| File | State found |
| --- | --- |
| `desktop/repository.py` | half-applied: `_card_pnl` defined as a `staticmethod` but called as `self._card_pnl(...)` from inside another static method → `NameError` on every forecast-card code path |
| `kh/ledger/models.py` | comma handling in `dec()` rejected all commas, including legitimate US thousands grouping |
| `kh/ledger/engine.py` | settlement/duplicate/mark hardening applied; **verified free of the placeholder loop** (`for extra in sl[:-1]…: pass`) and of stray `pass` statements |
| `desktop/account_service.py` | summary rewrite, unique manual ids, voided-fill history, mixed-side averages |
| `desktop/formatting.py` | money/count/stamp guards |
| `kh/ledger/importers.py` | JSON floats parsed as `Decimal` |
| `tests/test_ledger_engine.py` | mismatch expectation updated to the new (stricter) design |
| `desktop/qml/components/{QuoteCard,MarketDetail}.qml` | archived-quote wording |
| `packaging/icons/` (untracked) | icon SVG + PNGs already generated |

Evidence directories were untouched: `data/`, `research/`, `strategies/` hashed identically
(`20bb34ab867b21d6cb5f76face37915eb12225873143ea720acf0fa0c59ae6e5`) before and after recovery.

## 2. Preservation

- Full working tree (including untracked files, excluding only `.venv`, `var/cache`, `__pycache__`):
  `~/kalshi-hunter-dev/checkpoints/workspace-sonnet-interrupted-2026-10-21.tar.zst` (189 MB, 1 186 entries,
  verified readable; contains `data/kalshi.db`, `research/`, `packaging/`, `tests/helpers/`, all QML).
- Earlier checkpoints kept: commit `9aaf3be`, tag `checkpoint/pre-hunter-dev-2026-10-21`, pre-work bundle.
- No `git reset`, no `checkout --`, no file deleted. Every correction was a forward edit.

## 3. Verification of the interrupted state

`.venv/bin/python -m pytest tests` at the found state: **17 failed, 331 passed**. All 16 non-ledger failures were
the single `NameError` above (every `positions()`/`forecast_cards()`/`detail()` path builds a forecast card).
The 17th was the glass-box ledger test now expecting the new, stricter settlement rule.

## 4. Independent reviews: which findings are verified

**Review 1 — P&L engine (INTERRUPTED by the same credit failure; treated as partial evidence).**
Its scratch results survive: `~/.hermes/cache/scratch/review/ledger/results_s*.json` (8 scenario files, ~340 checks).
Every failed scenario was re-derived by hand before acting on it. Confirmed defects that were real:

- Recorded settlement revenue disagreeing with the fills printed a confident number (e.g. `+$995.90` when cents
  were typed as dollars). → now `INCOMPLETE`, both figures shown in the flag.
- A `void` settlement paying nothing while contracts were held → confident −$4.10. → now `INCOMPLETE`.
- A settlement paying more than the position can pay (`scalar`/`void` with no position) → confident profit. → `INCOMPLETE`.
- Only the latest settlement's fee was counted when several existed → fees understated (0.15 vs 0.18). → all counted.
- Fills dated after settlement were a warning only. → now `INCOMPLETE`.
- `0,07` was read as `7`; a millisecond epoch was accepted and later crashed the Positions page. → rejected.
- `Decimal(0.6)` marks produced `1.99999999999999977`. → marks validated (type, range, crossed, float artifacts).
- Economically identical re-imports (`0.40` vs `0.4`) were "conflicts" instead of duplicates. → canonical digits.
- Two genuine identical manual fills were collapsed into one. → unique id per manual entry.
- YES and NO legs were blended into one "average entry" (45¢) after a flip. → averages withheld with a flag.
- "All markets verified" was printed while conflicts, rejects or broken records existed. → note names them.

Not accepted as defects (reviewer's expectation was stricter than the documented design, verified by hand):
JSON numeric prices, `Decimal('1E+30')` formatting (now guarded anyway), missing `record_pnl` disagreement flag
(added as a warning), chart downsampling above 400 points (unreachable at current scan counts; documented).

**Review 2 — data handling and honest labelling (COMPLETED; verdict: 6 defects, none critical; 20 checks passed).**
All six addressed: the "Executable quotes" heading over archived data; a forecast card showing stored P&L that
failed reconciliation; spread-sort tie-break by float noise; unbounded offset/search input; unclamped page
numbers; and the per-process salted cache filename. Its leftover risks are recorded in
`docs/KNOWN_LIMITATIONS.md`.

## 5. State after recovery

- **393 tests pass** (94 s), including 28 new regression tests written for the confirmed defects above.
- Evidence hash unchanged. No scanner running; no network access; no credentials anywhere.
- Committed as `4acf573`.

## 6. Still open (not defects, tracked work)

Launcher/setup script, `SETUP.md` warning header, desktop entry (prepared, NOT installed), icon review, the five
documentation files, default-mode screenshots, KDE Wayland verification, final report. See `CONTINUATION.md`.