"""Missions routes — list, detail, Post-to-Jira toggle, and finalize."""

from __future__ import annotations

import logging
import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from api.schemas import (
    FinalizeResult,
    KanbanMission,
    KanbanTrigger,
    KanbanView,
    MissionDetail,
    MissionLifecycle,
    MissionListResponse,
    MissionSummary,
)
from api.sse import sse_manager
from core.kb_writer import KBCardWriter
from core.models import AgentOutput, Audit, Mission, SystemAudit, Trigger

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/missions", tags=["missions"])

DB = Annotated[AsyncSession, Depends(get_db)]


@router.get("/kanban", response_model=KanbanView)
async def missions_kanban(db: DB) -> KanbanView:
    """Retourne les 4 colonnes Kanban en une seule requête (50 items max par colonne)."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    async def _en_attente() -> list[KanbanTrigger]:
        rows = (
            await db.execute(
                select(Trigger)
                .where(
                    Trigger.matched.is_(True),
                    Trigger.processed_at.is_(None),
                    Trigger.claimed_at.is_(None),
                )
                .order_by(Trigger.received_at.asc())
                .limit(50)
            )
        ).scalars().all()
        return [KanbanTrigger.model_validate(r) for r in rows]

    async def _reservee() -> list[KanbanTrigger]:
        rows = (
            await db.execute(
                select(Trigger)
                .where(
                    Trigger.matched.is_(True),
                    Trigger.processed_at.is_(None),
                    Trigger.claimed_at.is_not(None),
                )
                .order_by(Trigger.claimed_at.asc())
                .limit(50)
            )
        ).scalars().all()
        return [KanbanTrigger.model_validate(r) for r in rows]

    async def _terminee() -> list[KanbanMission]:
        rows = (
            await db.execute(
                select(Mission)
                .where(
                    Mission.status.in_(["CLOSED", "PARTIAL"]),
                    Mission.closed_at > cutoff,
                )
                .order_by(Mission.closed_at.desc())
                .limit(50)
            )
        ).scalars().all()
        return [
            KanbanMission(
                mission_id=r.mission_id,
                tenant=r.tenant,
                env=r.env,
                subject=r.subject,
                status=r.status,
                created_at=r.created_at,
                closed_at=r.closed_at,
            )
            for r in rows
        ]

    async def _en_echec() -> list[KanbanTrigger]:
        rows = (
            await db.execute(
                select(Trigger)
                .where(
                    Trigger.last_error.like("DEAD:%"),
                    Trigger.processed_at.is_(None),
                )
                .order_by(Trigger.received_at.asc())
                .limit(50)
            )
        ).scalars().all()
        return [KanbanTrigger.model_validate(r) for r in rows]

    # Sequential execution — AsyncSession does not support concurrent queries on the same connection.
    en_attente = await _en_attente()
    reservee = await _reservee()
    terminee = await _terminee()
    en_echec = await _en_echec()
    return KanbanView(en_attente=en_attente, reservee=reservee, terminee=terminee, en_echec=en_echec)


@router.get("", response_model=MissionListResponse)
async def list_missions(
    db: DB,
    status: str | None = Query(None, description="Filter by status (OPEN, CLOSED, PARTIAL)"),
    env: str | None = Query(None, description="Filter by env (preprod, prod…)"),
    tenant: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> MissionListResponse:
    q = select(Mission)
    if status:
        q = q.where(Mission.status == status.upper())
    if env:
        q = q.where(Mission.env == env.upper())
    if tenant:
        q = q.where(Mission.tenant == tenant.lower())

    total_q = select(func.count()).select_from(q.subquery())
    total: int = (await db.execute(total_q)).scalar_one()

    rows = (await db.execute(q.order_by(Mission.created_at.desc()).limit(limit).offset(offset))).scalars().all()
    return MissionListResponse(
        items=[MissionSummary.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{mission_id}", response_model=MissionDetail)
async def get_mission(mission_id: str, db: DB) -> MissionDetail:
    mission = await _get_or_404(db, mission_id)

    outputs = (
        await db.execute(
            select(AgentOutput).where(AgentOutput.mission_id == mission_id).order_by(AgentOutput.created_at)
        )
    ).scalars().all()

    audit = (
        await db.execute(select(Audit).where(Audit.mission_id == mission_id).limit(1))
    ).scalar_one_or_none()

    if audit:
        log.debug("Audit object attributes: %s", dir(audit))
        # Check if card still exists, otherwise "un-finalize" in response
        f_at = getattr(audit, "finalized_at", None)
        slug = getattr(audit, "kb_card_slug", None)
        if f_at:
            if not slug:
                # Old mission without slug tracking - allow re-finalizing to populate it
                audit.finalized_at = None
                audit.brief_path = None
            else:
                # New mission with slug tracking - check physical existence
                writer = KBCardWriter(kb_dir=os.getenv("KB_DIR", "/app/kb"))
                if not writer.card_exists(slug):
                    audit.finalized_at = None
                    audit.brief_path = None

    # Explicit construction to avoid Pydantic/SQLAlchemy attribute suffix issues
    mission_dict = {
        "id": mission.id,
        "mission_id": mission.mission_id,
        "tenant": mission.tenant,
        "env": mission.env,
        "cluster": mission.cluster,
        "type": mission.type,
        "subject": mission.subject,
        "status": mission.status,
        "autonomy_level": mission.autonomy_level,
        "trigger_id": mission.trigger_id,
        "created_at": mission.created_at,
        "closed_at": mission.closed_at,
        "metadata_": mission.mission_metadata,
    }
    detail = MissionDetail(**mission_dict)
    
    detail.agent_outputs = [
        {"id": o.id, "agent": o.agent, "created_at": o.created_at} for o in outputs  # type: ignore[assignment]
    ]
    
    if audit:
        # Explicit dict conversion to help Pydantic
        detail.audit = {
            "id": audit.id,
            "agent": audit.agent,
            "posted_jira": audit.posted_jira,
            "jira_comment_id": audit.jira_comment_id,
            "created_at": audit.created_at,
            "updated_at": audit.updated_at,
            "brief_path": getattr(audit, "brief_path", None),
            "kb_card_slug": getattr(audit, "kb_card_slug", None),
            "finalized_at": getattr(audit, "finalized_at", None),
        }  # type: ignore[assignment]
    else:
        detail.audit = None
    
    return detail


@router.post("/{mission_id}/finalize")
async def finalize_mission(mission_id: str, db: DB) -> Any:
    """Trigger post-mortem capitalisation: BRIEF.md + KB card + INDEX.md.

    Only works on CLOSED missions. Idempotent: returns 409 if already finalized.
    Opt-in — never called automatically.
    """
    from agents.post_mortem_analyst.agent import PostMortemAgent
    from core.mission import MissionContext, MissionStatus, MissionType
    from core.tenant import TenantRegistry

    mission = await _get_or_404(db, mission_id)

    if mission.status == "OPEN":
        raise HTTPException(
            status_code=409,
            detail={"error": "mission_not_completed", "status": mission.status},
        )

    audit_row = (
        await db.execute(select(Audit).where(Audit.mission_id == mission_id).limit(1))
    ).scalar_one_or_none()

    if audit_row:
        f_at = getattr(audit_row, "finalized_at", None)
        slug = getattr(audit_row, "kb_card_slug", None)
        if f_at is not None:
            # If card slug is known, check if it still exists
            card_exists = False
            if slug:
                writer = KBCardWriter(kb_dir=os.getenv("KB_DIR", "/app/kb"))
                card_exists = writer.card_exists(slug)
            
            if card_exists:
                raise HTTPException(
                    status_code=409,
                    detail={"error": "already_finalized", "finalized_at": str(f_at)},
                )

    try:
        tenant_cfg = TenantRegistry.get(mission.tenant)
    except Exception:
        tenant_cfg = None  # type: ignore[assignment]

    ctx = MissionContext(
        mission_id=mission.mission_id,
        tenant=mission.tenant,
        env=mission.env,
        cluster=mission.cluster,
        type=MissionType(mission.type),
        subject=mission.subject,
        status=MissionStatus(mission.status),
        autonomy_level=mission.autonomy_level,
        metadata=mission.metadata_,
    )

    agent = PostMortemAgent(tenant_config=tenant_cfg)

    try:
        result = await agent.finalize(ctx, db_conn=db)
        log.info("Finalize success for mission %s: card=%s", mission_id, result.kb_card_slug)
        
        # Return raw dict to avoid any Pydantic serialization crash
        return {
            "mission_id": result.mission_id,
            "brief_path": result.brief_path,
            "kb_card_slug": result.kb_card_slug,
            "kb_card_action": result.kb_card_action,
            "kb_index_card_count": result.kb_index_card_count,
            "finalized_at": result.finalized_at.isoformat() if hasattr(result.finalized_at, "isoformat") else str(result.finalized_at),
        }
    except Exception as exc:
        log.error("Finalize FAILED for mission %s: %s", mission_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Capitalisation failed: {exc}")


@router.post("/{mission_id}/post-to-jira", status_code=501)
async def post_to_jira(mission_id: str, db: DB) -> dict:
    """Post the audit summary as a Jira comment (opt-in, explicit action).

    Returns 501 in v0.  Fully implemented in spec 001 US3 (Phase 5 T056).
    """
    await _get_or_404(db, mission_id)
    raise HTTPException(
        status_code=501,
        detail={
            "error": "not_implemented",
            "message": "Post-to-Jira is implemented in v0 Phase 5 (US3).",
        },
    )


@router.get("/{mission_id}/events")
async def mission_events(mission_id: str, db: DB) -> StreamingResponse:
    """SSE stream for live mission lifecycle events."""
    await _get_or_404(db, mission_id)
    return StreamingResponse(
        sse_manager.subscribe(mission_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/{mission_id}", status_code=204)
async def delete_mission(mission_id: str, db: DB) -> None:
    """Delete a mission and all related data (cascading)."""
    mission = await _get_or_404(db, mission_id)

    try:
        # Cascade delete manually (or rely on FK if configured, but explicit is safer here)
        await db.execute(delete(AgentOutput).where(AgentOutput.mission_id == mission_id))
        await db.execute(delete(Audit).where(Audit.mission_id == mission_id))
        await db.execute(delete(Mission).where(Mission.mission_id == mission_id))

        # Log the action
        audit = SystemAudit(
            action="DELETE_MISSION",
            resource_type="MISSION",
            resource_id=mission_id,
            audit_metadata={"mission_id": mission_id, "tenant": mission.tenant},
            created_by="system",
        )
        db.add(audit)
        await db.commit()

    except Exception as exc:
        await db.rollback()
        log.error("Failed to delete mission %s: %s", mission_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{mission_id}/lifecycle", response_model=MissionLifecycle)
async def mission_lifecycle(mission_id: str, db: DB) -> MissionLifecycle:
    """Retourne le cycle de vie complet d'une mission (trigger + mission)."""
    mission = await _get_or_404(db, mission_id)
    trigger = (
        await db.execute(
            select(Trigger).where(Trigger.mission_id == mission_id).limit(1)
        )
    ).scalar_one_or_none()

    return MissionLifecycle(
        trigger_id=str(trigger.id) if trigger else None,
        received_at=trigger.received_at if trigger else None,
        claimed_at=trigger.claimed_at if trigger else None,
        claimed_by=trigger.claimed_by if trigger else None,
        attempts=trigger.attempts if trigger else 0,
        last_error=trigger.last_error if trigger else None,
        mission_created_at=mission.created_at,
        mission_closed_at=mission.closed_at,
        mission_status=mission.status,
    )


async def _get_or_404(db: AsyncSession, mission_id: str) -> Mission:
    row = (
        await db.execute(select(Mission).where(Mission.mission_id == mission_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Mission not found: {mission_id!r}")
    return row
