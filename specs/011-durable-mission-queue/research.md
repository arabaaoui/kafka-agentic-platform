# Research: Durable Mission Queue with Parallel Processing

**Branch**: `011-durable-mission-queue` | **Date**: 2026-06-12

---

## Decision 1: SELECT FOR UPDATE SKIP LOCKED — SQLAlchemy async pattern

**Decision**: Use raw `text()` SQL with a CTE + `RETURNING *` inside an `AsyncSession`, committed immediately after claim.

**Rationale**: SQLAlchemy 2.0 ORM does not expose `SKIP LOCKED` through its `select()` API directly (it requires `.with_for_update(skip_locked=True)` which works but cannot be combined with a CTE RETURNING pattern in a single atomic statement). Using `text()` gives full control over the PostgreSQL-specific CTE:

```sql
WITH next AS (
  SELECT id FROM triggers
  WHERE matched = true
    AND processed_at IS NULL
    AND (claimed_at IS NULL OR claimed_at < now() - make_interval(secs => :lease_seconds))
  ORDER BY received_at
  FOR UPDATE SKIP LOCKED
  LIMIT 1
)
UPDATE triggers
SET claimed_at = now(),
    claimed_by = :worker_id,
    attempts   = attempts + 1
WHERE id = (SELECT id FROM next)
RETURNING id, tenant, source, external_id, payload, trigger_id, received_at, attempts
```

The `SKIP LOCKED` semantics mean: if another worker already holds a row-level lock on a trigger (from a concurrent claim), this query skips it and claims the next available one. This eliminates contention between workers without application-level coordination.

**asyncpg note**: asyncpg natively supports this pattern. `session.execute(text(...))` with `await` dispatches through asyncpg's connection. The result of `RETURNING *` is accessible via `result.fetchone()` or `result.mappings().fetchone()`.

**Alternatives considered**:
- `SELECT ... FOR UPDATE SKIP LOCKED` without CTE (two round-trips: SELECT then UPDATE) → race condition between two async coroutines.
- Redis-based distributed lock (`SET NX PX`) → adds Redis dependency; existing pool manages it natively in Postgres.
- `asyncio.Lock()` in-process → doesn't survive multi-replica deployment; not durable.

---

## Decision 2: prometheus_client integration with FastAPI async

**Decision**: Use `prometheus_client.generate_latest()` in a synchronous FastAPI route returning `Response(content=..., media_type="text/plain; version=0.0.4")`.

**Rationale**: `prometheus_client` is already in `pyproject.toml` (≥0.20.0). In single-process mode (one FastAPI replica), the default global registry works correctly without multiprocess mode. The `/metrics` route can call `generate_latest()` synchronously — it is CPU-only (no I/O) and returns quickly. The queue depth gauge is updated by a background task on a 5-second interval rather than on each scrape (avoids DB query on every scrape).

**Implementation pattern**:
```python
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

@router.get("/metrics")
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

**Background refresh for Gauge metrics** (`kafkaops_queue_depth`, `kafkaops_queue_inflight`): a separate `asyncio.create_task` runs every 5 seconds and executes two cheap COUNT queries against the partial index.

**Multiprocess note**: If the platform ever runs with `gunicorn --workers N` (WSGI workers), prometheus_client's multiprocess mode would be required (`PROMETHEUS_MULTIPROC_DIR` env var). This is not the case for the current FastAPI/uvicorn single-process deployment.

**Alternatives considered**:
- `starlette-prometheus` library → extra dependency; not worth it for a single endpoint.
- `make_asgi_app()` from prometheus_client → mounts as a sub-ASGI app; less flexible for auth middleware and health check integration.

---

## Decision 3: Lease heartbeat for long-running missions

**Decision**: A dedicated `asyncio.create_task` heartbeat coroutine per active worker refreshes `claimed_at` every `lease_seconds / 3` (default: 5 minutes for a 15-minute lease).

**Rationale**: A mission pipeline can run for 5–15 minutes (LLM calls + kubectl + PromQL). If the lease is 15 minutes and a mission takes 14 minutes, there is only a 1-minute safety margin before another worker re-claims the trigger. The heartbeat refreshes `claimed_at = now()` to keep the lease alive.

**Implementation**:
```python
async def _heartbeat(session_factory, trigger_id: str, interval: int, stop_event: asyncio.Event):
    while not stop_event.is_set():
        await asyncio.sleep(interval)
        if stop_event.is_set():
            break
        async with session_factory() as s:
            await s.execute(
                text("UPDATE triggers SET claimed_at = now() WHERE id = :id"),
                {"id": trigger_id}
            )
            await s.commit()
```

The `stop_event` is set by the worker upon mission completion or failure, cleanly cancelling the heartbeat.

**Alternatives considered**:
- Longer lease (e.g., 2h) to avoid heartbeat → acceptable for simple cases, but means a crashed worker holds a trigger for 2h before recovery. 15 min + heartbeat gives fast recovery on crash with no false re-claims during normal operation.
- Extending `claimed_at` from within the pipeline → would require passing a callback into `orchestrator.handle()`, coupling the pipeline to queue mechanics.

---

## Decision 4: Adaptive polling backoff

**Decision**: Exponential backoff starting at 2 seconds, doubling on each idle cycle, capped at 30 seconds. Resets to 2 seconds on successful claim.

**Rationale**: Without backoff, an idle worker polls the database every iteration, generating constant DB load even when there is no work. With 3 workers and no triggers, that's 3 queries/second against PostgreSQL — unnecessary at low load. At the cap of 30s, 3 workers generate 6 queries/minute at peak idle — negligible.

```python
sleep_s = 2
while True:
    trigger = await claim_next(session, worker_id, lease_seconds)
    if trigger is None:
        await asyncio.sleep(sleep_s)
        sleep_s = min(sleep_s * 2, 30)
    else:
        sleep_s = 2  # reset on work found
        await process(trigger)
```

**Alternatives considered**:
- Fixed 5-second poll → acceptable but wastes cycles at peak idle.
- Database LISTEN/NOTIFY to wake workers → more responsive but requires a persistent asyncpg connection in LISTEN mode; complexity not justified for current load.

---

## Decision 5: Dead-letter handling

**Decision**: After `MAX_ATTEMPTS` (default: 3) failures, set `last_error` to a terminal string (prefixed `"DEAD:"`) and never re-claim. No separate DLQ table — dead triggers remain in `triggers` for audit.

**Rationale**: A separate DLQ table would require a schema migration plus additional tooling (UI, cleanup job). The `triggers` table already has `last_error` for storing failure context. A `DEAD:` prefix on `last_error` is sufficient to distinguish dead triggers from transiently-failed ones. The `kafkaops_mission_dead_total` metric provides the operational alert.

**Alternatives considered**:
- Move dead triggers to a separate `trigger_dlq` table → clean separation but adds schema complexity for a low-volume case.
- Delete dead triggers → loses audit trail; violates "Zero Secret Leakage" indirectly (can't audit what was attempted).

---

## Decision 6: asyncio.Queue removal strategy

**Decision**: Remove `asyncio.Queue` in WS-2, not WS-1. In WS-1, the `asyncio.Queue` is kept but N workers all consume from it (valid for `asyncio.Queue.get()` which is coroutine-safe). WS-2 replaces the queue entirely.

**Rationale**: WS-1 is low-risk and delivers immediate parallelism value. WS-2 is a larger refactor touching 5 files. Keeping them separate reduces rollback blast radius.

**Consequence**: WS-1 can be merged independently with `WORKER_CONCURRENCY=1` as the safe default. WS-2 has the same safe default — if WS-2 is deployed and DB has no pending triggers, behavior is identical to the prior single-worker implementation.

---

## Decision 7: prometheus_client — Gauge update strategy

**Decision**: Queue-depth and in-flight Gauges are refreshed by a dedicated background task (`asyncio.create_task`) on a 5-second interval, not on each HTTP scrape of `/metrics`.

**Rationale**: The `/metrics` endpoint is called by Prometheus every 15–60 seconds and also potentially by debugging tools. Executing a DB query on every scrape would add DB load proportional to scrape frequency. A 5-second background refresh decouples observability from DB load and gives near-real-time accuracy (at most 5s stale).

**Alternatives considered**:
- Query on every scrape → accurate but adds 1 DB connection per scrape; at 15s interval acceptable, but tightly couples scraper to DB health.
- Store metrics only in-process counters (no DB query) → fast but misses triggers inserted by pollers without going through worker (edge case: manual DB insert for testing).
