"""Admin routes — hot-reload tenant configs without server restart (spec 003 FR-005)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from api.schemas import AgentCard, SkillCard, SystemAuditListResponse
from core.models import SystemAudit
from core.tenant import TenantRegistry

router = APIRouter(prefix="/v1/admin", tags=["admin"])

AGENTS_DIR = Path(__file__).parent.parent.parent / "agents"

_CATEGORY_MAP: dict[str, str] = {
    "k8s_gcp_sre": "infrastructure",
    "prom_alerts_triage": "infrastructure",
    "kafka_strimzi_expert": "données",
    "intake": "autre",
    "evidence_consolidator": "autre",
    "post_mortem_analyst": "autre",
}

def _categorize(agent_dir: str) -> str:
    return _CATEGORY_MAP.get(agent_dir, "autre")

DB = Annotated[AsyncSession, Depends(get_db)]


@router.get("/audit", response_model=SystemAuditListResponse, summary="Get system audit logs")
async def get_audit_logs(
    db: DB,
    action: str | None = Query(None, description="Filter by action type"),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> SystemAuditListResponse:
    """Return a list of system audit logs, ordered by newest first."""
    q = select(SystemAudit)

    if action:
        q = q.where(SystemAudit.action == action.upper())
    if resource_type:
        q = q.where(SystemAudit.resource_type == resource_type.upper())

    q = q.order_by(desc(SystemAudit.created_at))

    total_q = select(func.count()).select_from(q.subquery())
    total: int = (await db.execute(total_q)).scalar_one()

    rows = (await db.execute(q.limit(limit).offset(offset))).scalars().all()

    return SystemAuditListResponse(
        items=list(rows),
        total=total,
        limit=limit,
        offset=offset
    )



@router.post("/platform-identity")
async def set_platform_identity(payload: dict, db: AsyncSession = Depends(get_db)):
    """Upload the Master GSA Key (JSON) to make the platform autonomous."""
    from sqlalchemy import text
    from pathlib import Path
    import json
    
    value = json.dumps(payload)
    
    # 1. Persist to DB
    await db.execute(
        text("INSERT INTO platform_settings (key, value) VALUES ('gsa_key', :v) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"),
        {"v": value}
    )
    await db.commit()
    
    # 2. Materialize to disk for the GCPTokenProvider
    key_path = Path("/app/kube_conf/platform_master_key.json")
    key_path.write_text(value, encoding="utf-8")
    
    return {"status": "ok", "message": "Platform identity updated. Backend is now autonomous."}


@router.get("/agents/catalog", response_model=list[AgentCard])
async def agents_catalog() -> list[AgentCard]:
    """Catalogue des agents actifs lu depuis agents/*/SKILL.md (constitution §VI)."""
    result: list[AgentCard] = []
    for skill_file in sorted(AGENTS_DIR.glob("*/SKILL.md")):
        try:
            text = skill_file.read_text(encoding="utf-8")
            if not text.startswith("---"):
                continue
            _, front, body = text.split("---", 2)
            meta = yaml.safe_load(front) or {}
            result.append(
                AgentCard(
                    name=str(meta.get("name", skill_file.parent.name)),
                    agent_dir=skill_file.parent.name,
                    description=str(meta.get("description", "")).strip()[:200],
                    version=str(meta.get("version", "1.0")),
                    description_long=body.strip()[:500],
                    active=True,
                )
            )
        except Exception:
            continue
    return result


@router.get("/skills/catalog", response_model=list[SkillCard])
async def skills_catalog() -> list[SkillCard]:
    """Catalogue des compétences extraites des SKILL.md."""
    result: list[SkillCard] = []
    for skill_file in sorted(AGENTS_DIR.glob("*/SKILL.md")):
        try:
            text = skill_file.read_text(encoding="utf-8")
            if not text.startswith("---"):
                continue
            _, front, body = text.split("---", 2)
            meta = yaml.safe_load(front) or {}
            agent_name = str(meta.get("name", skill_file.parent.name))
            agent_dir = skill_file.parent.name

            # Extraire les bullet points du corps du SKILL.md
            skills: list[str] = []
            for line in body.splitlines():
                line = line.strip()
                if line.startswith("- ") and len(line) > 3:
                    skill_text = line[2:].strip()
                    if skill_text and not skill_text.startswith("["):
                        skills.append(skill_text[:120])
                        if len(skills) >= 10:
                            break

            result.append(
                SkillCard(
                    agent_name=agent_name,
                    agent_dir=agent_dir,
                    category=_categorize(agent_dir),
                    skills=skills,
                )
            )
        except Exception:
            continue
    return result


@router.post("/reload-tenants", summary="Reload all tenant YAML configs")
async def reload_tenants() -> dict:
    """Re-read all tenants/*.yaml files and swap the active config atomically.

    On validation error the current configs remain active — no partial reload.
    Returns the list of loaded tenant slugs.
    """
    try:
        configs = TenantRegistry.reload()
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "tenants": sorted(configs)}
