# Contract: agents/pipeline/durable_queue.py

Module interface contract for the durable queue primitives used by workers.

---

## claim_next

```python
async def claim_next(
    session: AsyncSession,
    worker_id: str,
    lease_seconds: int = 900,
    max_attempts: int = 3,
) -> dict | None:
```

**Description**: Atomically claims the oldest pending trigger that is not dead and not currently held by another worker (or whose lease has expired). Returns the trigger row as a dict, or `None` if no claimable trigger is available.

**Behavior**:
- Executes a single `WITH next AS (...) UPDATE ... RETURNING *` statement (one round-trip).
- Skips triggers where `attempts >= max_attempts` (dead-letter candidates — they will be marked dead by `mark_failed`, not re-claimed).
- Increments `attempts` on the claimed row.
- Sets `claimed_at = now()` and `claimed_by = worker_id`.
- The `session` MUST be committed by the caller immediately after this call to release the row-level lock.

**Returns**:
- `dict` with keys matching the `triggers` table columns if a trigger was claimed.
- `None` if no claimable trigger exists (queue is empty or all pending triggers are held by other workers).

**Raises**:
- `sqlalchemy.exc.SQLAlchemyError` on DB errors — caller must handle and retry.

---

## mark_processed

```python
async def mark_processed(
    session: AsyncSession,
    trigger_id: str,
    mission_id: str,
) -> None:
```

**Description**: Marks a trigger as successfully processed. Sets `processed_at = now()`.

**Behavior**:
- Updates `triggers SET processed_at = now() WHERE id = :trigger_id`.
- Does NOT update `mission_id` (already set by orchestrator during intake).
- Caller must commit the session.

---

## mark_failed

```python
async def mark_failed(
    session: AsyncSession,
    trigger_id: str,
    error: str,
    max_attempts: int = 3,
) -> bool:
```

**Description**: Records a pipeline failure. Resets `claimed_at = NULL` to allow re-claim on the next cycle. If `attempts >= max_attempts`, calls `mark_dead()` instead.

**Returns**: `True` if the trigger was marked dead, `False` if it was reset for retry.

**Behavior**:
- First reads current `attempts` from the row.
- If `attempts >= max_attempts` → delegates to `mark_dead(session, trigger_id, error)`, returns `True`.
- Otherwise → sets `claimed_at = NULL`, `claimed_by = NULL`, `last_error = error[:4096]`, returns `False`.
- Caller must commit the session.

---

## mark_dead

```python
async def mark_dead(
    session: AsyncSession,
    trigger_id: str,
    error: str,
) -> None:
```

**Description**: Permanently exhausts a trigger. Sets `last_error = "DEAD:<error>"` and `processed_at = now()` so it is removed from the pending index and never re-claimed.

**Behavior**:
- Updates `last_error = 'DEAD:' || :error` and `processed_at = now()`.
- Increments `kafkaops_mission_dead_total` counter.
- Caller must commit the session.

---

## queue_stats

```python
async def queue_stats(session: AsyncSession) -> dict:
```

**Description**: Returns aggregate queue statistics for metrics and `/healthz`. Executes two COUNT queries against the partial index.

**Returns**:
```python
{
    "depth": int,           # matched=true AND processed_at IS NULL
    "inflight": int,        # claimed_at IS NOT NULL AND processed_at IS NULL
    "oldest_pending_age_seconds": float | None,
}
```
