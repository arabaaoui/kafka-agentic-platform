"""Durable queue primitives backed by the triggers PostgreSQL table.

Workers use SELECT FOR UPDATE SKIP LOCKED so that concurrent workers each
claim a distinct trigger row without application-level locking.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


async def claim_next(
    session: AsyncSession,
    worker_id: str,
    lease_seconds: int = 900,
    max_attempts: int = 3,
) -> dict[str, Any] | None:
    """Atomically claim the oldest pending trigger not already held by another worker.

    Uses a single CTE + UPDATE RETURNING statement (one round-trip).
    The caller MUST commit the session immediately after this call to release
    the row-level lock.

    Returns the claimed trigger row as a dict, or None if the queue is empty.
    """
    stmt = text(
        """
        WITH next AS (
            SELECT id FROM triggers
            WHERE matched = true
              AND processed_at IS NULL
              AND (claimed_at IS NULL
                   OR claimed_at < now() - make_interval(secs => :lease_seconds))
              AND (last_error IS NULL OR last_error NOT LIKE 'DEAD:%%')
              AND attempts < :max_attempts
            ORDER BY received_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        UPDATE triggers
        SET claimed_at  = now(),
            claimed_by  = :worker_id,
            attempts    = attempts + 1
        WHERE id = (SELECT id FROM next)
        RETURNING *
        """
    )
    result = await session.execute(
        stmt,
        {
            "lease_seconds": lease_seconds,
            "worker_id": worker_id,
            "max_attempts": max_attempts,
        },
    )
    row = result.mappings().fetchone()
    if row is None:
        return None
    return dict(row)


async def mark_processed(
    session: AsyncSession,
    trigger_id: str,
    mission_id: str,
) -> None:
    """Mark a trigger as successfully processed."""
    await session.execute(
        text("UPDATE triggers SET processed_at = now() WHERE id = :id"),
        {"id": trigger_id},
    )


async def mark_failed(
    session: AsyncSession,
    trigger_id: str,
    error: str,
    max_attempts: int = 3,
) -> bool:
    """Record a pipeline failure.

    Resets claimed_at so the trigger can be re-claimed on the next cycle.
    If attempts >= max_attempts, delegates to mark_dead() instead.

    Returns True if the trigger was marked dead, False if reset for retry.
    """
    result = await session.execute(
        text("SELECT attempts FROM triggers WHERE id = :id"),
        {"id": trigger_id},
    )
    row = result.fetchone()
    attempts = row[0] if row else 0

    if attempts >= max_attempts:
        await mark_dead(session, trigger_id, error)
        return True

    await session.execute(
        text(
            """
            UPDATE triggers
            SET claimed_at = NULL,
                claimed_by = NULL,
                last_error = :error
            WHERE id = :id
            """
        ),
        {"id": trigger_id, "error": error[:4096]},
    )
    return False


async def mark_dead(
    session: AsyncSession,
    trigger_id: str,
    error: str,
) -> None:
    """Permanently exhaust a trigger after max retries.

    Sets last_error with 'DEAD:' prefix and processed_at so the row is
    removed from the pending index and never re-claimed.
    """
    await session.execute(
        text(
            """
            UPDATE triggers
            SET last_error    = :error,
                processed_at  = now()
            WHERE id = :id
            """
        ),
        {"id": trigger_id, "error": "DEAD:" + error[:4000]},
    )
    log.error("Trigger %s marked dead: %s", trigger_id, error[:200])


async def queue_stats(session: AsyncSession) -> dict[str, Any]:
    """Return aggregate queue statistics using the partial index.

    Returns a dict with keys:
      depth                    — pending + in-flight (processed_at IS NULL)
      inflight                 — currently claimed (claimed_at IS NOT NULL, processed_at IS NULL)
      oldest_pending_age_seconds — age of oldest unprocessed trigger, or None
    """
    result = await session.execute(
        text(
            """
            SELECT
                COUNT(*)                                                            AS depth,
                COUNT(*) FILTER (WHERE claimed_at IS NOT NULL)                     AS inflight,
                EXTRACT(EPOCH FROM (now() - MIN(received_at)))                     AS oldest_age
            FROM triggers
            WHERE matched = true AND processed_at IS NULL
            """
        )
    )
    row = result.fetchone()
    if row is None:
        return {"depth": 0, "inflight": 0, "oldest_pending_age_seconds": None}
    depth, inflight, oldest_age = row
    return {
        "depth": int(depth or 0),
        "inflight": int(inflight or 0),
        "oldest_pending_age_seconds": float(oldest_age) if oldest_age is not None else None,
    }
