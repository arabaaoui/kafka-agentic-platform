"""Triggers routes — list received triggers and ignored ones with rejection reasons."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from api.schemas import IgnoredTriggerListResponse, IgnoredTriggerResponse, RetryResult, TriggerListResponse, TriggerResponse
from core.models import FilterMatchLog, SystemAudit, Trigger

router = APIRouter(prefix="/v1/triggers", tags=["triggers"])

DB = Annotated[AsyncSession, Depends(get_db)]


@router.post("/{trigger_id}/retry", response_model=RetryResult)
async def retry_trigger(trigger_id: str, db: DB) -> RetryResult:
    """Remet un trigger DEAD dans la file durable (action humaine explicite)."""
    trigger = (
        await db.execute(select(Trigger).where(Trigger.id == trigger_id))
    ).scalar_one_or_none()

    if not trigger:
        raise HTTPException(status_code=404, detail=f"Trigger not found: {trigger_id}")
    if trigger.processed_at is not None:
        raise HTTPException(status_code=409, detail="Trigger already processed")
    if not (trigger.last_error or "").startswith("DEAD:"):
        raise HTTPException(status_code=409, detail="Trigger is not in DEAD state")

    trigger.last_error = None
    trigger.claimed_at = None
    trigger.claimed_by = None
    trigger.attempts = 0
    db.add(
        SystemAudit(
            action="RETRY_TRIGGER",
            resource_type="TRIGGER",
            resource_id=str(trigger_id),
            audit_metadata={"tenant": trigger.tenant, "source": trigger.source},
        )
    )
    await db.commit()

    return RetryResult(id=str(trigger.id), tenant=trigger.tenant, source=trigger.source)


@router.get("", response_model=TriggerListResponse)
async def list_triggers(
    db: DB,
    source: str | None = Query(None, description="jira | alertmanager | care"),
    matched: bool | None = Query(None),
    tenant: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> TriggerListResponse:
    from sqlalchemy import func
    q = select(Trigger)
    if source:
        q = q.where(Trigger.source == source)
    if matched is not None:
        q = q.where(Trigger.matched == matched)
    if tenant:
        q = q.where(Trigger.tenant == tenant)

    total: int = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (
        await db.execute(q.order_by(Trigger.received_at.desc()).limit(limit).offset(offset))
    ).scalars().all()

    return TriggerListResponse(
        items=[TriggerResponse.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/ignored", response_model=IgnoredTriggerListResponse)
async def list_ignored_triggers(
    db: DB,
    source: str | None = Query(None),
    tenant: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> IgnoredTriggerListResponse:
    """Return unmatched triggers with the rejection reason from filter_match_log."""
    from sqlalchemy import func

    base_q = (
        select(Trigger, FilterMatchLog.reason)
        .outerjoin(FilterMatchLog, FilterMatchLog.trigger_id == Trigger.id)
        .where(Trigger.matched.is_(False))
    )
    if source:
        base_q = base_q.where(Trigger.source == source)
    if tenant:
        base_q = base_q.where(Trigger.tenant == tenant)

    total: int = (
        await db.execute(select(func.count()).select_from(base_q.subquery()))
    ).scalar_one()

    rows = (
        await db.execute(base_q.order_by(Trigger.received_at.desc()).limit(limit).offset(offset))
    ).all()

    items: list[IgnoredTriggerResponse] = []
    for trigger, reason in rows:
        item = IgnoredTriggerResponse.model_validate(trigger)
        item.reject_reason = reason
        items.append(item)

    return IgnoredTriggerListResponse(items=items, total=total, limit=limit, offset=offset)
