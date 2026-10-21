# Account data contract — the personal ledger

This is the agreement between **your real trading records** and the desktop application. It defines how your
manually-executed Kalshi trades get in, what the application is allowed to conclude from them, and exactly what
a future read-only account connection may and may not do.

Nothing in this document is implemented beyond the local file import and manual entry described in
sections 1–5. Section 6 is a **proposal that requires your explicit approval** before a single line is written.

## 0. Non-negotiables

1. **You place every trade.** The application has no code path that creates, changes, cancels or executes an
   order, and none may be added.
2. **Your records are append-only.** A correction is a new record; nothing is edited or deleted in place.
3. **Exact decimals only.** All amounts are `Decimal`. Floats are rejected at the boundary, as are ambiguous
   values like `0,07` (decimal comma) and millisecond timestamps.
4. **Unknown stays unknown.** Missing, contradictory or incomplete information renders as `Unavailable` or `—`,
   never as `0`, and never as a guess.
5. **The ledger lives apart from the evidence.** `var/account.db` (yours) and `var/sample/account.db`
   (invented demo data) can never be confused with `data/` or `research/`, and the writers refuse any path
   inside the evidence directories.

## 1. Where records come from today

| Source | How | Notes |
| --- | --- | --- |
| A file you export | Positions/History → **Import from file…**, or `AccountService.import_file(path, kind=None, price_unit='dollars', tz='America/Chicago')` | CSV or JSON, ≤ 20 MB. Column **order is irrelevant**; extra columns are ignored; headers are matched case-insensitively. |
| One trade you typed in | Positions/History → **Record a trade…** (`record_fill`) | Validated with the same rules as an import; each manual entry gets its own unique id, so two genuine identical fills are both recorded. |
| Sample fixtures | `--sample-account` | Invented data for demonstration, built fresh at launch in `var/sample/`, always shown behind a `SAMPLE DATA` banner. Never mixed with yours. |

File shape for JSON: a list of objects, or an object with a `records` or `rows` list.

## 2. Column contract

`key?` = optional. Prices are **dollars** unless you pass `price_unit='cents'`. Timestamps are epoch **seconds**
between 2000 and 2100, or ISO-8601 (`2026-10-01 10:00`, or with offset); a naive timestamp is read as
`America/Chicago`.

### fills

| Column | Required | Rules |
| --- | --- | --- |
| `fill_id` | no | Your exchange id. Re-importing the same id with the same content is a duplicate; with different content it is a **conflict** (original kept, new copy quarantined). Missing ids get a deterministic synthetic id, so re-importing the same file stays idempotent. |
| `ticker` | **yes** | Upper-cased on entry; `[A-Z0-9][A-Z0-9._-]{0,79}` |
| `side` | **yes** | `yes` or `no` |
| `action` | **yes** | `buy` or `sell` |
| `count` | **yes** | Decimal, > 0 (fractional counts are kept, not rounded) |
| `price` | **yes** | Strictly between 0 and 1 (dollars), i.e. per contract for the side traded |
| `fee` | no | Decimal ≥ 0, actual fee charged on this fill (dollars) |
| `ts` | **yes** | Execution time |
| `order_id`, `is_taker`, `note` | no | free text / true–false / ≤ 500 chars |

### settlements

| Column | Required | Rules |
| --- | --- | --- |
| `settlement_id` | no | As `fill_id` above. |
| `ticker` | **yes** | as above |
| `market_result` | **yes** | `yes`, `no`, `void` or `scalar` |
| `settled_ts` | **yes** | when the market settled |
| `revenue` | **yes** | Total payout credited to you, dollars. **This is the authoritative payout.** |
| `fee` | no | Settlement fee, dollars |
| `yes_count`, `no_count` | no | contracts held at settlement, if your export states them — used as a completeness cross-check |
| `yes_total_cost`, `no_total_cost` | no | cost as your exchange recorded it — cross-checked against your fills; a disagreement is flagged |

### cash

| Column | Required | Rules |
| --- | --- | --- |
| `txn_id` | no | as above |
| `ts` | **yes** | movement time |
| `kind` | **yes** | `deposit`, `withdrawal`, … (free text, shown as the row type) |
| `amount` | **yes** | dollars, signed (a withdrawal is negative) |
| `note` | no | free text |

Deposits and withdrawals are **never** counted as profit; they are reported separately as net deposits.

## 3. What the application concludes

- **Settlement is authoritative for the payout.** Realized P&L = proceeds from sales and netting + settlement
  revenue − cost basis (including entry fees) − all fees. Entry fees are part of cost basis; exit and
  settlement fees reduce proceeds.
- **Completeness is checked before any number is printed.** The market is marked *incomplete* — and shows
  `Unavailable` — when: settlement revenue disagrees with what the fills imply; a settlement's own
  yes/no counts disagree with the fills; a payout exceeds what the held contracts could pay; a fill is dated
  after settlement; several settlements exist; a void paid nothing while contracts were held; a sale exceeds
  the position; or a settlement exists with no fills. The reason is always shown next to the figure.
- **Unrealized P&L is `Unavailable` offline.** It requires a fresh, executable exit quote (≤ 300 s old by the
  marking rule). The archive is hours old, so nothing is marked from it — deliberately.
- **Averages are withheld when they would mislead.** A market traded on both YES and NO shows `—` for entry and
  exit averages instead of blending two different prices into one meaningless number.
- **Fees are never dropped**, including every fee when several settlement records exist for one market.
- **Quarantine is visible.** Conflicts, rejected rows and voids are counted in Data quality, and the positions
  headline says `All markets verified` **only** when nothing at all is flagged or quarantined.

## 4. Journal

| Field | Notes |
| --- | --- |
| `title`, `body`, `tags` | free text; every save keeps the previous wording (revisions are retained) |
| `ticker` | optional link to a market; the entry then shows the recorded research for that ticker |
| `entry_type` | `note`, `pre_trade`, `post_trade` |
| `planned_side`, `planned_price`, `my_prob` | what you intended, before you knew the outcome |

Deleting hides an entry; the revision history remains. The comparison view shows *your* decisions next to the
recorded research (side, timing, your own probabilities) — descriptively, never as a scoreboard, and paper
results are never added to your actual results.

## 5. Data quality report

Positions/Evidence pages list: quarantined conflicts (with the record id), rejected rows with their line number
and reason, voided records, per-import batches (new/duplicate/conflict/rejected), and a warning when any fill is
priced below 1¢ — the signature of a dollars file imported as cents (void those rows and re-import with the
right unit; the app will not guess).

## 6. Read-only account connection — PROPOSED, NOT BUILT

A design only. No credential has been requested, stored or used, and no endpoint has been contacted.
**It requires your explicit approval before implementation starts.** When approved, the first step is a dry run
against a file you export by hand — never against live endpoints first.

What it would be:

- **Scope: reads only.** Positions, fills, settlements and balance history. There is no order-placement,
  order-amendment or order-cancellation endpoint in the design, and the client would refuse to send any
  non-GET request. A read-only API key is the only key accepted.
- **Credentials**: kept in the OS keyring, never in the repository, never in a log, never echoed to the UI.
  A `Not connected` state is the default and remains until you enable it.
- **Sync model**: cursor-paged reads, newest-first resume from the last stored id, appending into
  `var/account.db` through the same validated importers (`source='kalshi_api'`), so re-syncing is idempotent and
  a conflicting duplicate is quarantined exactly as with a file import. The reserved source label
  `kalshi_api` is not written by anything today.
- **Separation**: account activity lands only in your ledger. It can never write into `data/` or `research/`,
  and paper forecasts are never adjusted by it. The comparison view is the only place the two meet, side by
  side.
- **Failure handling**: every response is validated with the rules in section 2 before it is stored;
  a partial page is not silently accepted; a mismatch (e.g. a fill whose count exceeds the position) surfaces
  as a data-quality error rather than a corrected number.
- **Auditability**: each sync is recorded as an import batch (time, source, label, counts) so you can always
  see what arrived when.

Approval gates before any of this is built or enabled: (1) you approve the design; (2) you approve requesting
a read-only key; (3) you approve the first live sync; (4) a written, tested assertion that no non-GET request
can leave the process.

## 7. Versioning

`var/account.db` records `schema_version = 1` in its `meta` table. Future changes are additive migrations;
this database is append-only, so an upgrade never rewrites your history.