import asyncio
import logging
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine

from agents.pipeline.durable_queue import claim_next, mark_processed, mark_failed
from api.routes.metrics import (
    mission_completed_total,
    mission_dead_total,
    mission_duration_seconds,
    queue_claims_total,
)

log = logging.getLogger(__name__)

_HEARTBEAT_INTERVAL = 300  # refresh claimed_at every 5 minutes
_BACKOFF_MIN = 2
_BACKOFF_MAX = 30


async def _heartbeat(
    engine: AsyncEngine,
    trigger_id: str,
    interval: int,
    stop_event: asyncio.Event,
) -> None:
    """Periodically refresh claimed_at to prevent lease expiry on long missions."""
    from sqlalchemy import text

    while not stop_event.is_set():
        await asyncio.sleep(interval)
        if stop_event.is_set():
            break
        try:
            async with AsyncSession(engine) as session:
                await session.execute(
                    text("UPDATE triggers SET claimed_at = now() WHERE id = :id"),
                    {"id": trigger_id},
                )
                await session.commit()
        except Exception as exc:
            log.warning("[heartbeat] Failed to refresh lease for trigger %s: %s", trigger_id, exc)


async def start_mission_worker(
    engine: AsyncEngine,
    worker_id: str = "worker-0",
    model: str = "gemini-2.5-flash-lite",
) -> None:
    """Background task that polls the durable trigger queue and runs the investigation pipeline."""
    from agents.pipeline.orchestrator import PipelineOrchestrator

    log.info("[%s] Mission worker: starting with model=%s", worker_id, model)
    sleep_s = _BACKOFF_MIN

    while True:
        try:
            async with AsyncSession(engine) as session:
                trigger = await claim_next(session, worker_id)
                await session.commit()

            if trigger is None:
                await asyncio.sleep(sleep_s)
                sleep_s = min(sleep_s * 2, _BACKOFF_MAX)
                continue

            sleep_s = _BACKOFF_MIN
            trigger_id = trigger["id"]
            tenant = trigger.get("tenant", "unknown")
            env = trigger.get("source", "unknown")
            log.info(
                "[%s] Mission worker: claimed trigger id=%s source=%s ext_id=%s attempt=%d",
                worker_id,
                trigger_id,
                trigger.get("source"),
                trigger.get("external_id"),
                trigger.get("attempts", 1),
            )
            queue_claims_total.labels(worker_id=worker_id).inc()
            start_time = time.monotonic()

            stop_hb = asyncio.Event()
            hb_task = asyncio.create_task(
                _heartbeat(engine, trigger_id, _HEARTBEAT_INTERVAL, stop_hb)
            )

            try:
                orchestrator = PipelineOrchestrator(db_engine=engine, model=model)
                await orchestrator.handle(trigger)

                async with AsyncSession(engine) as session:
                    await mark_processed(session, trigger_id, str(trigger.get("mission_id", "")))
                    await session.commit()

                elapsed = time.monotonic() - start_time
                mission_duration_seconds.observe(elapsed)
                mission_completed_total.labels(tenant=tenant, env=env, outcome="success").inc()
                log.info(
                    "[%s] Mission worker: completed trigger id=%s ext_id=%s in %.1fs",
                    worker_id,
                    trigger_id,
                    trigger.get("external_id"),
                    elapsed,
                )

            except Exception as exc:
                log.error(
                    "[%s] Mission worker: pipeline failed for trigger id=%s: %s",
                    worker_id,
                    trigger_id,
                    exc,
                    exc_info=True,
                )
                elapsed = time.monotonic() - start_time
                mission_duration_seconds.observe(elapsed)
                async with AsyncSession(engine) as session:
                    dead = await mark_failed(session, trigger_id, str(exc))
                    await session.commit()
                if dead:
                    mission_dead_total.inc()
                    mission_completed_total.labels(tenant=tenant, env=env, outcome="dead").inc()
                    log.error(
                        "[%s] Mission worker: trigger id=%s exhausted max attempts — marked dead",
                        worker_id,
                        trigger_id,
                    )
                else:
                    mission_completed_total.labels(tenant=tenant, env=env, outcome="failed").inc()

            finally:
                stop_hb.set()
                hb_task.cancel()
                try:
                    await hb_task
                except asyncio.CancelledError:
                    pass

        except Exception as exc:
            log.critical("[%s] Mission worker: FATAL error in main loop: %s", worker_id, exc, exc_info=True)
            await asyncio.sleep(5)
