# Data Model: Durable Mission Queue

**Branch**: `011-durable-mission-queue` | **Date**: 2026-06-12

---

## Entity: Trigger (extended)

**Table**: `triggers` (existing — additive migration only)

### Existing Fields (unchanged)

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `tenant` | TEXT NOT NULL | |
| `source` | TEXT NOT NULL | `jira` \| `alertmanager` \| `care` |
| `external_id` | TEXT NOT NULL | Source-side dedup key |
| `payload` | JSONB NOT NULL | Raw trigger payload |
| `matched` | BOOLEAN NOT NULL DEFAULT false | Set true when a filter rule matches |
| `mission_id` | TEXT NULL | Set by orchestrator after mission creation |
| `received_at` | TIMESTAMPTZ NOT NULL | Insertion time |
| `processed_at` | TIMESTAMPTZ NULL | Set when pipeline completes (success OR dead) |
| UNIQUE | `(tenant, source, external_id)` | Producer-side deduplication |

### New Fields (migration `XXXX_triggers_durable_queue.py`)

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `claimed_at` | TIMESTAMPTZ NULL | NULL | Set when a worker claims this trigger. Refreshed by heartbeat. NULL means unclaimed or reset after failed attempt. |
| `claimed_by` | TEXT NULL | NULL | Worker identifier: `"worker-{pid}-{index}"`. Used for debugging and audit. |
| `attempts` | INTEGER NOT NULL | 0 | Incremented on each claim. Used for max-retry enforcement. |
| `last_error` | TEXT NULL | NULL | Last failure message. Prefixed `"DEAD:"` when trigger is exhausted. |

### New Index (migration)

```sql
CREATE INDEX idx_triggers_pending ON triggers (received_at)
  WHERE matched = true AND processed_at IS NULL;
```

This partial index covers the `claim_next` query hot path (only unprocessed, matched triggers). Keeps queue-depth queries and claim queries O(pending) not O(all).

### Trigger Lifecycle (state machine)

```
                    INSERT (producer)
                          │
                          ▼
                    [pending]
             matched=true, processed_at=NULL
             claimed_at=NULL, attempts=0
                          │
           ┌──────────────┤ claim_next()
           │              ▼
           │        [in-flight]
           │  claimed_at=<now>, claimed_by=<worker>
           │  attempts=N+1
           │              │
           │   ┌──────────┼───────────────┐
           │   │          │               │
           │   ▼          ▼               ▼
           │ [lease    [success]       [failure]
           │  expired] processed_at    claimed_at=NULL
           │ re-claim  =<now>          last_error=<msg>
           │ possible  ──────────────► (retry if attempts < MAX)
           │                                │
           │                                ▼ (attempts == MAX)
           │                           [dead]
           └──────────────────────►  last_error="DEAD:<msg>"
                                    processed_at=<now>
                                    (never re-claimed)
```

### Validation Rules

- `attempts` MUST be ≥ 0. Enforced by DB DEFAULT and application-level increment.
- `claimed_at` and `claimed_by` MUST be set together (both NULL or both non-NULL). Enforced at application level in `claim_next()`.
- A trigger MAY NOT transition from `[dead]` to any other state. Enforced by `claim_next()` query filter (`last_error NOT LIKE 'DEAD:%'`).
- `processed_at` MUST be set for both successful and dead triggers to remove them from the pending queue index.

---

## Conceptual Entity: Worker

Not persisted in the database — ephemeral per-process.

| Attribute | Description |
|-----------|-------------|
| `worker_id` | `"worker-{pid}-{index}"` — unique within a process; identifies the worker in logs and `claimed_by` |
| `index` | Integer 0..N-1, assigned at startup from `WORKER_CONCURRENCY` |
| `active` | Boolean — True while the coroutine is running |
| `current_trigger_id` | UUID of the trigger currently being processed, or None |
| `sleep_seconds` | Current backoff interval (2..30s), resets on successful claim |

---

## Conceptual Entity: Lease

Not a separate table — encoded in `triggers.claimed_at`.

| Attribute | Description |
|-----------|-------------|
| `trigger_id` | FK → triggers.id |
| `worker_id` | The `claimed_by` value |
| `acquired_at` | `claimed_at` at time of claim |
| `expires_at` | `claimed_at + make_interval(secs => lease_seconds)` |
| `lease_seconds` | Configurable, default 900 (15 minutes) |

A lease is **active** if `claimed_at IS NOT NULL AND processed_at IS NULL AND claimed_at > now() - interval 'lease_seconds seconds'`.
A lease is **expired** if `claimed_at IS NOT NULL AND processed_at IS NULL AND claimed_at <= now() - interval 'lease_seconds seconds'`.
Expired leases are claimed by the next available worker via `claim_next()`.

---

## Configuration Model

Environment variables consumed by the new components:

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `WORKER_CONCURRENCY` | int | 1 | Number of parallel workers. Capped at 7 (floor(30/4)) with startup warning. |
| `WORKER_LEASE_SECONDS` | int | 900 | Trigger lease duration in seconds. Workers holding a trigger longer than this risk false re-claim without heartbeat. |
| `WORKER_MAX_ATTEMPTS` | int | 3 | Max retry count before a trigger is marked dead. |
| `WORKER_POLL_MIN_SLEEP` | int | 2 | Minimum poll sleep (seconds) when queue is empty. |
| `WORKER_POLL_MAX_SLEEP` | int | 30 | Maximum poll sleep (seconds) — exponential backoff cap. |
| `METRICS_REFRESH_INTERVAL` | int | 5 | Background task interval (seconds) for updating queue-depth Gauge metrics. |
