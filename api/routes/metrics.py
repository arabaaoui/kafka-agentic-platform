"""Prometheus metrics endpoint and metric objects for the mission queue."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from api.schemas import MetricsDataPoint, MetricsSnapshot

router = APIRouter(tags=["ops"])

DB = Annotated[AsyncSession, Depends(get_db)]

# Ring buffer in-memory : 60 points × intervalle METRICS_REFRESH_INTERVAL = ~10 min de données
_history: deque[dict] = deque(maxlen=60)


def push_history_point(depth: int, inflight: int) -> None:
    """Appelé par le background task _refresh_metrics dans api/main.py."""
    _history.append({
        "ts": datetime.now(timezone.utc).isoformat(),
        "depth": depth,
        "inflight": inflight,
    })

# ── Metric objects (module-level singletons) ──────────────────────────────────

queue_depth = Gauge(
    "kafkaops_queue_depth",
    "Number of triggers pending or in-flight (processed_at IS NULL)",
)

queue_inflight = Gauge(
    "kafkaops_queue_inflight",
    "Number of triggers currently claimed by a worker",
)

queue_claims_total = Counter(
    "kafkaops_queue_claims_total",
    "Total trigger claims by worker",
    ["worker_id"],
)

mission_completed_total = Counter(
    "kafkaops_mission_completed_total",
    "Total completed missions",
    ["tenant", "env", "outcome"],
)

mission_duration_seconds = Histogram(
    "kafkaops_mission_duration_seconds",
    "End-to-end mission processing time",
    buckets=[5, 15, 30, 60, 120, 300, 600],
)

mission_dead_total = Counter(
    "kafkaops_mission_dead_total",
    "Triggers permanently exhausted after max attempts",
)


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/v1/metrics/snapshot", response_model=MetricsSnapshot, tags=["ops"])
async def metrics_snapshot(db: DB) -> MetricsSnapshot:
    """Métriques plateforme sous forme JSON pour la page Surveillance."""
    from agents.pipeline.durable_queue import queue_stats

    stats = await queue_stats(db)

    pct_row = (
        await db.execute(
            text("""
                SELECT
                    percentile_cont(0.5)  WITHIN GROUP (ORDER BY extract(epoch FROM (closed_at - created_at))),
                    percentile_cont(0.95) WITHIN GROUP (ORDER BY extract(epoch FROM (closed_at - created_at))),
                    percentile_cont(0.99) WITHIN GROUP (ORDER BY extract(epoch FROM (closed_at - created_at)))
                FROM missions
                WHERE closed_at > now() - interval '1 hour'
                  AND closed_at IS NOT NULL
            """)
        )
    ).fetchone()

    completed_24h: int = (
        await db.execute(
            text("SELECT count(*) FROM missions WHERE closed_at > now() - interval '24 hours'")
        )
    ).scalar_one()

    dead_total: int = (
        await db.execute(
            text("SELECT count(*) FROM triggers WHERE last_error LIKE 'DEAD:%' AND processed_at IS NULL")
        )
    ).scalar_one()

    history = [MetricsDataPoint(**p) for p in list(_history)]

    return MetricsSnapshot(
        queue_depth=stats["depth"] or 0,
        queue_inflight=stats["inflight"] or 0,
        oldest_pending_age_seconds=stats.get("oldest_pending_age_seconds"),
        mission_completed_24h=completed_24h,
        mission_dead_total=dead_total,
        duration_p50_seconds=pct_row[0] if pct_row and pct_row[0] is not None else None,
        duration_p95_seconds=pct_row[1] if pct_row and pct_row[1] is not None else None,
        duration_p99_seconds=pct_row[2] if pct_row and pct_row[2] is not None else None,
        history=history,
    )
