# Live research integration — architecture proposal (NOT IMPLEMENTED)

How the desktop application can receive Grok's continuously generated research **without disrupting the
existing cloud backend**. Nothing in this document has been built or contacted: no remote service was
modified, no endpoint was called, and no credential was requested. It requires your explicit approval before
any implementation begins.

## 1. Goal and constraints

Wanted: research that reaches this desktop while it is fresh, with honest freshness labelling, visible
connection status and stale-data warnings — and with **zero risk** to the running cloud environment.

Constraints, in priority order:

1. **The cloud stays the single writer.** The desktop never scans, never schedules cloud work, never writes to
   the cloud, and never “refreshes” anything remotely. No duplicate research jobs can exist because the
   desktop is incapable of starting one.
2. **Read-only, client-initiated.** Every byte arrives because this machine asked for it. Nothing is pushed
   into this machine uninvited.
3. **Paper research never becomes account activity.** The feed can only ever feed the research/paper views.
   Your ledger is a different database with a different writer.
4. **Labelling is honest.** Feed rows are labelled by measured age, never by optimism: `LIVE` only while the
   connection is up *and* the newest batch is inside the fresh window; otherwise `STALE`, and archived
   snapshot data always says `ARCHIVED` no matter how recent it looks.

## 2. What already exists (verified in this codebase)

- `desktop/freshness.py` — the age classes and the connection state machine are implemented and tested:
  scan interval 300 s, fresh ≤ 600 s, stale ≤ 2700 s (45 min), older or `source='archive'` ⇒ `ARCHIVED`.
  `ConnectionState` transitions already cover `DISCONNECTED → CONNECTING → CONNECTED → STALE → RECONNECTING`
  with a `TIMEOUT` event, and the UI shows the state and its text.
- The repository, bridge and pages are prepared to show a `connection` label and per-source freshness; today
  the status bar reads “READ-ONLY SNAPSHOT · NO SCANNER STARTED · LOCAL DATA ONLY”.
- The Alerts page already states that what it shows is **historical, not a live feed**, and that delivery
  would be a separately approved integration.

What is missing is only the transport and the store on this side: a `var/feed.db` and a fetcher.

## 3. Options considered

| Option | Shape | Pros | Cons | Verdict |
| --- | --- | --- | --- | --- |
| **A. Append-only export batches** (recommended) | The cloud periodically writes an immutable bundle (JSON lines or SQLite) per batch, with a manifest: sequence number, row counts, per-batch sha256, chained previous-hash. The desktop GETs the manifest, then any batches it lacks. | Immutable, resumable, verifiable, trivially cache-friendly (ETag), no per-row API needed, cannot be “written back” by construction | Needs a small publisher change in the cloud (a cron/step that emits a bundle) | **Recommended** |
| B. Read-only REST endpoint | The desktop polls `GET /research?since=<id>` with a read-only token | No publishing step; per-request freshness | Per-row API load on the scanner host; needs auth; harder to verify continuity | Fallback if A is impractical |
| C. Shared object storage only | Both sides mount the same bucket/volume | Simplest transport | Couples the desktop to cloud filesystem layout; weaker integrity story | Only inside your own infrastructure |
| D. Message queue / websocket stream | Push from the cloud | Lowest latency | A push channel into a research workstation is the largest attack surface and the largest operational change; hard to replay | Not recommended |

Latency is not a design driver here: this application is a research viewer, and research that is minutes old
is still useful. Immutability, replayability and “cannot write back” matter more.

## 4. Recommended design (option A), concretely

**Cloud side** (a change to the cloud environment — *requires approval; nothing done*):
- After each scan/research cycle, append new rows to an export stream: `scans`, `snapshots` (delta),
  `candidates`, `alerts`, `forecasts` (with cohort label), `research_records`, `hash_chain`.
- Publish **immutable batches** (e.g. `research-export/<seq>.jsonl.zst`) plus a manifest
  `research-export/manifest.json`: `{seq, prev_hash, batch_hash, rows, generated_at, schema_version}`.
- Batches are only added, never rewritten. The scanner's own database remains the source of truth.

**Desktop side** (new code, only after approval):
- A `FeedService` that polls the manifest on a fixed schedule (default 15 min) with a random jitter of ±2 min,
  using `If-None-Match`/`ETag` so an unchanged manifest costs one empty response.
- Downloads only missing sequences (resume from the last verified `seq`), verifies `prev_hash` chains to what
  it already has and `batch_hash` over the bytes **before** parsing, then appends rows into `var/feed.db`
  (its own database; `data/kalshi.db` stays frozen evidence, opened read-only).
- Records sync state: `last_seq`, `last_ok_at`, `last_attempt_at`, `consecutive_failures`, `last_error`.
- Freshness: the **research timestamp** of the newest row, not “when we last fetched”, drives the label. A
  successful fetch of old research must still read `STALE`; a failed fetch must never make anything read newer.
- Connection status in the UI: `DISCONNECTED` (feature off — the default), `CONNECTING`, `CONNECTED`
  (fresh batches), `STALE` (nothing new inside the stale window; the banner says so explicitly),
  `RECONNECTING` after failures.
- Failure handling: exponential backoff 1 → 2 → 4 → … minutes capped at 30, with jitter; a hash-chain gap
  (can happen if a batch was ever rewritten) → keep the good rows, quarantine the inconsistent range, stop
  advancing, and raise a visible “feed integrity” banner with the sequence numbers. The app never guesses
  missing research; it shows a gap.
- Kill switch: the feature is **off by default** and off means “no socket is opened at all”. A single setting
  (`research_feed.enabled`) gates it; the static and runtime tests that prove zero network use stay in force
  for every other code path, and a new test asserts that with the feed disabled the process opens no
  connection even when the setting is toggled in the same session.

## 5. Why no duplicate research jobs can exist

The desktop is a *consumer*: it has no scheduler that triggers cloud work, no “scan now” action, and no way to
send the cloud anything except a GET for a batch it is missing. Adding a “request a fresh scan” button in the
future would be a deliberate, separately-approved feature with its own rate limit and dedupe; it is **not**
part of this design.

## 6. Separation of paper research from account activity

- Feed rows live in `var/feed.db` and are labelled `paper` everywhere they are shown.
- Your ledger lives in `var/account.db`, written only by you (imports and manual entries).
- No code path copies a feed row into the ledger, derives a position from research, or adds a paper result to
  an account figure. The comparison view is the only join, it is read-only, and it is descriptive.
- The `research_feed` requires no trading credentials. If it ever used a token, it would be a read-only research
  token kept in the OS keyring — never the account key, and never a key with order permissions.

## 7. Testing plan (to run before it is ever pointed at anything real)

1. Fixture bundles, including: a normal sequence, a gap, a batch with a broken hash, a manifest that moves
   backwards, a huge batch, and a malformed row set.
2. Resume/idempotence: re-running the fetcher over an already-imported range must add nothing.
3. Freshness: labels must follow the research timestamp in every fixture, including adversarial ones (fresh
   manifest, stale content).
4. Backoff schedule and jitter bounds, and a test that a failing feed never blocks the rest of the UI.
5. Default-off network test (extends the existing runtime test).
6. A dry run against a bundle you export by hand, reviewed before any live endpoint is configured.

## 8. Approval gates

1. You approve this design (or choose an option from §3).
2. You approve the **cloud-side** change to publish batches — the only change to the existing environment in
   the whole plan, and it must not alter scanner behaviour or its database.
3. You approve the desktop-side fetch implementation and its default-off switch.
4. You approve the first real run, with the dry-run results in hand.

Until all four: this document remains a proposal, the code stays as it is, and the application continues to
show archived snapshots only — labelled exactly as such.