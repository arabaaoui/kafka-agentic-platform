"""Filter rules routes — runtime-editable without server restart (spec 002)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from api.schemas import FilterRuleCreate, FilterRulePatch, FilterRuleResponse
from core.models import FilterRule

router = APIRouter(prefix="/v1/filter-rules", tags=["filter-rules"])

DB = Annotated[AsyncSession, Depends(get_db)]

_VALID_SCOPES = {"jira", "alertmanager", "care"}


@router.get("", response_model=list[FilterRuleResponse])
async def list_filter_rules(
    db: DB,
    tenant: str | None = Query(None),
    scope: str | None = Query(None),
    enabled: bool | None = Query(None),
) -> list[FilterRuleResponse]:
    q = select(FilterRule)
    if tenant:
        q = q.where(FilterRule.tenant == tenant)
    if scope:
        q = q.where(FilterRule.scope == scope)
    if enabled is not None:
        q = q.where(FilterRule.enabled == enabled)
    rows = (await db.execute(q.order_by(FilterRule.priority.asc()))).scalars().all()
    return [FilterRuleResponse.model_validate(r) for r in rows]


@router.post("", response_model=FilterRuleResponse, status_code=201)
async def create_filter_rule(body: FilterRuleCreate, db: DB) -> FilterRuleResponse:
    if body.scope not in _VALID_SCOPES:
        raise HTTPException(status_code=422, detail=f"scope must be one of {sorted(_VALID_SCOPES)}")

    rule = FilterRule(
        id=uuid.uuid4(),
        tenant=body.tenant,
        scope=body.scope,
        name=body.name,
        enabled=body.enabled,
        priority=body.priority,
        poll_interval_seconds=body.poll_interval_seconds,
        criteria=body.criteria,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return FilterRuleResponse.model_validate(rule)


@router.patch("/{rule_id}", response_model=FilterRuleResponse)
async def update_filter_rule(rule_id: uuid.UUID, body: FilterRulePatch, db: DB) -> FilterRuleResponse:
    rule = await _get_rule_or_404(db, rule_id)
    if body.name is not None:
        rule.name = body.name
    if body.enabled is not None:
        rule.enabled = body.enabled
    if body.priority is not None:
        rule.priority = body.priority
    if body.poll_interval_seconds is not None:
        rule.poll_interval_seconds = body.poll_interval_seconds
    if body.criteria is not None:
        rule.criteria = body.criteria
    rule.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(rule)
    return FilterRuleResponse.model_validate(rule)


@router.delete("/{rule_id}", status_code=204)
async def delete_filter_rule(rule_id: uuid.UUID, db: DB) -> None:
    """Actually delete the rule. Nullifies references in logs."""
    from sqlalchemy import update
    from core.models import FilterMatchLog

    rule = await _get_rule_or_404(db, rule_id)

    # Nullify references in logs to avoid FK constraint violation
    await db.execute(
        update(FilterMatchLog).where(FilterMatchLog.rule_id == rule_id).values(rule_id=None)
    )

    await db.delete(rule)
    await db.flush()


async def _get_rule_or_404(db: AsyncSession, rule_id: uuid.UUID) -> FilterRule:
    row = (
        await db.execute(select(FilterRule).where(FilterRule.id == rule_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Filter rule not found: {rule_id}")
    return row
