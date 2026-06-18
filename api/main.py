"""Main application factory and lifespan management."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.tenant import TenantRegistry

log = logging.getLogger(__name__)


def init_otel_tracing() -> None:
    """Initialize telemetry. No-op since we use native REST-based LangfuseADKPlugin."""
    log.info("Langfuse native REST-based ADK Plugin tracing active.")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # ── startup ──────────────────────────────────────────────────────────────
    init_otel_tracing()
    tenants_dir = os.getenv("TENANTS_DIR", "tenants")
    TenantRegistry.init(tenants_dir)

    # 1. Materialize Master Key from DB
    from core.db import get_engine
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession
    from pathlib import Path

    engine = get_engine()
    conf_dir = Path("/app/kube_conf")
    conf_dir.mkdir(parents=True, exist_ok=True)

    async with AsyncSession(engine) as session:
        # Load Master Key
        res = await session.execute(text("SELECT value FROM platform_settings WHERE key = 'gsa_key'"))
        row = res.fetchone()
        if row:
            key_path = conf_dir / "platform_master_key.json"
            key_path.write_text(row[0], encoding="utf-8")
            log.info("Platform Master Key materialized from DB.")

        # Load dynamic overrides
        from core.models import InfrastructureEnv
        from core.tenant import EnvConfig
        from sqlalchemy import select

        db_envs = (await session.execute(select(InfrastructureEnv))).scalars().all()
        for e in db_envs:
            try:
                # Prepare a clean dict for Pydantic
                cfg_data = {
                    "display_name": e.display_name,
                    "badge_color": e.badge_color,
                    "clusters": e.clusters,
                    "kubeconfig": e.kubeconfig,
                    "kube_context": getattr(e, "kube_context", ""),
                    "kubeconfig_content": e.kubeconfig_content,
                    "kafka_namespace": e.kafka_namespace,
                    "prom_url": e.prom_url,
                    "alertmanager_url": e.alertmanager_url,
                    "proxy_url": e.proxy_url,
                    "proxy_user": e.proxy_user,
                    "proxy_pass": e.proxy_pass,
                    "vm_url": e.vm_url,
                    "target_gsa_email": getattr(e, "target_gsa_email", ""),
                }

                # Materialize files for DB overrides if content is present
                if e.kubeconfig_content:
                    kc_path = conf_dir / f"{e.tenant}_{e.slug}_kubeconfig.yaml"
                    kc_path.write_text(e.kubeconfig_content, encoding="utf-8")
                    cfg_data["kubeconfig"] = str(kc_path)

                # Use the new target_gsa_email field
                if cfg_data.get("target_gsa_email"):
                    log.debug("DB Override: registered target GSA email for %s:%s", e.tenant, e.slug)

                TenantRegistry.add_env_override(e.tenant, e.slug, EnvConfig(**cfg_data))
            except Exception as exc:
                log.warning("Could not load DB override for %s:%s: %s", e.tenant, e.slug, exc)

    log.info("TenantRegistry loaded: %s", list(TenantRegistry.all()))

    from agents.pipeline.worker import start_mission_worker
    from agents.pipeline.durable_queue import queue_stats
    from api.routes.metrics import queue_depth as m_queue_depth, queue_inflight as m_queue_inflight, push_history_point
    from triggers.jira_mcp_poller import JiraMcpPoller
    from triggers.alertmanager_poller import start_alertmanager_poller

    async def _refresh_metrics(refresh_engine: Any, interval: int) -> None:
        while True:
            try:
                async with AsyncSession(refresh_engine) as session:
                    stats = await queue_stats(session)
                depth = stats["depth"] or 0
                inflight = stats["inflight"] or 0
                m_queue_depth.set(depth)
                m_queue_inflight.set(inflight)
                push_history_point(depth, inflight)
            except Exception as exc:
                log.warning("Metrics refresh failed: %s", exc)
            await asyncio.sleep(interval)

    def _on_task_done(task: asyncio.Task) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log.critical("Background task failed: %s", exc, exc_info=True)

    # Start N mission workers (WORKER_CONCURRENCY env var, default 1)
    concurrency = int(os.getenv("WORKER_CONCURRENCY", "1"))
    if concurrency > 7:
        log.warning(
            "WORKER_CONCURRENCY=%d exceeds DB pool capacity (max safe: 7) — connection exhaustion risk",
            concurrency,
        )
    model = os.getenv("GOOGLE_ADK_MODEL", "gemini-2.5-flash-lite")
    app.state.worker_tasks = []
    for i in range(concurrency):
        worker_id = f"worker-{os.getpid()}-{i}"
        t = asyncio.create_task(
            start_mission_worker(engine, worker_id=worker_id, model=model)
        )
        t.add_done_callback(_on_task_done)
        app.state.worker_tasks.append(t)
    log.info("Started %d mission worker(s)", concurrency)

    # Start metrics refresh background task
    metrics_interval = int(os.getenv("METRICS_REFRESH_INTERVAL", "5"))
    app.state.metrics_task = asyncio.create_task(_refresh_metrics(engine, metrics_interval))
    app.state.metrics_task.add_done_callback(_on_task_done)

    # Start Jira poller
    poller = JiraMcpPoller(db_engine=engine)
    app.state.poller_task = asyncio.create_task(poller.start())
    app.state.poller_task.add_done_callback(_on_task_done)

    # Start Alertmanager poller
    app.state.am_poller_task = asyncio.create_task(start_alertmanager_poller())
    app.state.am_poller_task.add_done_callback(_on_task_done)

    try:
        yield
    except Exception as exc:
        log.critical("Lifespan crashed: %s", exc, exc_info=True)
        raise

    # ── shutdown ─────────────────────────────────────────────────────────────
    for t in app.state.worker_tasks:
        t.cancel()
    app.state.poller_task.cancel()
    app.state.am_poller_task.cancel()
    app.state.metrics_task.cancel()
    await engine.dispose()


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    app = FastAPI(
        title="Phenix Kafka Ops AI Platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── routes ────────────────────────────────────────────────────────────────
    from api.routes import admin, audits, filter_rules, kb, metrics, missions, triggers, infrastructure
    from triggers import alertmanager_webhook

    app.include_router(admin.router)
    app.include_router(missions.router)
    app.include_router(audits.router)
    app.include_router(filter_rules.router)
    app.include_router(triggers.router)
    app.include_router(infrastructure.router)
    app.include_router(alertmanager_webhook.router)
    app.include_router(kb.router)
    app.include_router(metrics.router)

    @app.get("/healthz", tags=["ops"])
    async def healthz() -> dict:
        from agents.pipeline.durable_queue import queue_stats
        from core.db import get_session
        from sqlalchemy import text

        worker_tasks = getattr(app.state, "worker_tasks", [])
        worker_count = sum(1 for t in worker_tasks if not t.done())
        try:
            async with get_session() as session:
                stats = await queue_stats(session)
                dead_count: int = (
                    await session.execute(
                        text("SELECT count(*) FROM triggers WHERE last_error LIKE 'DEAD:%' AND processed_at IS NULL")
                    )
                ).scalar_one()
        except Exception:
            stats = {"depth": None, "inflight": None, "oldest_pending_age_seconds": None}
            dead_count = 0
        return {
            "status": "ok",
            "tenants": sorted(TenantRegistry.all()),
            "worker_count": worker_count,
            "queue_depth": stats["depth"],
            "oldest_pending_age_seconds": stats["oldest_pending_age_seconds"],
            "dead_count": dead_count,
        }

    return app


app = create_app()
