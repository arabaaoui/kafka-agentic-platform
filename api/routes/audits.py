"""Audits routes — serve audit.md and expose Jira post status."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from api.schemas import AuditResponse
from core.models import Audit, Mission

router = APIRouter(prefix="/v1/missions", tags=["audits"])

DB = Annotated[AsyncSession, Depends(get_db)]

_AUDIT_BASE = Path(os.getenv("AUDIT_DIR", "audits"))


@router.get("/{mission_id}/audit")
async def get_audit(mission_id: str, db: DB) -> Response:
    """Return the audit.md for a mission.

    - **200** — audit ready, returns `text/markdown`
    - **202** — mission still running, audit not yet generated
    - **404** — mission not found
    """
    mission = (
        await db.execute(select(Mission).where(Mission.mission_id == mission_id))
    ).scalar_one_or_none()
    if mission is None:
        raise HTTPException(status_code=404, detail=f"Mission not found: {mission_id!r}")

    audit_path = _AUDIT_BASE / mission_id / "audit.md"
    if not audit_path.exists():
        if mission.status == "OPEN":
            return Response(
                content="Audit not yet generated — mission is still running.",
                status_code=202,
                media_type="text/plain",
            )
        raise HTTPException(
            status_code=404,
            detail=f"audit.md not found for mission {mission_id!r}",
        )

    audit_row = (
        await db.execute(select(Audit).where(Audit.mission_id == mission_id).limit(1))
    ).scalar_one_or_none()

    content = audit_path.read_text(encoding="utf-8")
    headers: dict[str, str] = {}
    if audit_row:
        headers["X-Posted-To-Jira"] = str(audit_row.posted_jira).lower()
        if audit_row.jira_comment_id:
            headers["X-Jira-Comment-Id"] = audit_row.jira_comment_id

    return Response(content=content, media_type="text/markdown", headers=headers)


@router.get("/{mission_id}/audit/meta", response_model=AuditResponse)
async def get_audit_meta(mission_id: str, db: DB) -> AuditResponse:
    """Return audit metadata (posted_jira, timestamps) without the Markdown body."""
    audit_row = (
        await db.execute(select(Audit).where(Audit.mission_id == mission_id).limit(1))
    ).scalar_one_or_none()
    if audit_row is None:
        raise HTTPException(status_code=404, detail=f"No audit found for mission {mission_id!r}")
    return AuditResponse(
        mission_id=audit_row.mission_id,
        content_md=audit_row.content_md[:512] + "…" if len(audit_row.content_md) > 512 else audit_row.content_md,
        posted_jira=audit_row.posted_jira,
        jira_comment_id=audit_row.jira_comment_id,
        created_at=audit_row.created_at,
    )
