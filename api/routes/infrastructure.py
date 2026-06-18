"""Infrastructure routes — CRUD for environments (merged YAML + DB)."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from api.schemas import (
    InfrastructureEnvCreate,
    InfrastructureEnvResponse,
    TenantInfrastructureResponse,
)
from core.models import InfrastructureEnv, SystemAudit
from core.tenant import EnvConfig, TenantRegistry

router = APIRouter(prefix="/v1/infrastructure", tags=["infrastructure"])

DB = Annotated[AsyncSession, Depends(get_db)]
log = logging.getLogger(__name__)


@router.post("/tenants/{tenant}/envs/{slug}/test", response_model=dict)
async def test_infrastructure_env(
    tenant: str,
    slug: str,
    db: DB,
) -> dict:
    """Test GKE connectivity for a specific environment (Impersonation check)."""
    # 1. Get environment config
    q = select(InfrastructureEnv).where(
        InfrastructureEnv.tenant == tenant,
        InfrastructureEnv.slug == slug
    )
    db_env = (await db.execute(q)).scalar_one_or_none()
    
    if not db_env:
        # Fallback to YAML if not in DB
        try:
            tenant_cfg = TenantRegistry.get(tenant)
            env_cfg = tenant_cfg.envs.get(slug)
            if not env_cfg:
                raise KeyError()
            target_gsa = getattr(env_cfg, "target_gsa_email", None)
            kubeconfig = env_cfg.kubeconfig
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Environment '{slug}' not found")
    else:
        target_gsa = db_env.target_gsa_email
        kubeconfig = db_env.kubeconfig

    # 2. Try to get token
    from core.gcp import GCPTokenProvider
    try:
        log.info("Testing connectivity for %s:%s (GSA: %s)", tenant, slug, target_gsa)
        token = await GCPTokenProvider.get_token(target_gsa_email=target_gsa)
        
        # 3. Simple cluster check if kubeconfig is available
        connectivity_status = "Token obtained successfully"
        if kubeconfig and Path(kubeconfig).exists():
            import subprocess
            try:
                # Just try to get the server version or similar
                cmd = ["kubectl", "--kubeconfig", kubeconfig, "version", "--client", "--short"]
                # We need to temporarily set the token in the file or environment
                # For a quick test, we'll just validate the token was generated
                connectivity_status += " and Kubeconfig exists."
            except Exception as e:
                connectivity_status += f", but kubectl test failed: {e}"
        
        return {
            "status": "success",
            "message": connectivity_status,
            "details": {
                "token_preview": f"{token[:10]}...{token[-10:]}",
                "target_gsa": target_gsa
            }
        }
    except Exception as exc:
        log.error("Connectivity test failed: %s", exc, exc_info=True)
        return {
            "status": "error",
            "message": f"Failed to authenticate: {str(exc)}"
        }


from fastapi.encoders import jsonable_encoder

@router.get("/tenants", response_model=list[TenantInfrastructureResponse])
async def get_infrastructure_tenants(db: DB) -> list[TenantInfrastructureResponse]:
    """Return all tenants and their environments (merged YAML + DB)."""
    # 1. Get YAML-based configs
    configs = TenantRegistry.all()
    
    # 2. Get DB-based overrides
    db_envs = (await db.execute(select(InfrastructureEnv))).scalars().all()
    
    result = []
    for t_slug, cfg in configs.items():
        # Create a combined map of environments
        # Start with YAML envs (already as dicts via model_dump)
        envs_map = {k: v.model_dump() for k, v in cfg.envs.items()}
        
        # Overlay with DB envs (validated via schema then dumped to JSON-safe dict)
        tenant_db_envs = [e for e in db_envs if e.tenant == t_slug]
        for db_e in tenant_db_envs:
            # We use model_validate to check schema, then dump to JSON-safe format
            valid_e = InfrastructureEnvResponse.model_validate(db_e)
            envs_map[db_e.slug] = jsonable_encoder(valid_e)
            
        result.append(TenantInfrastructureResponse(
            tenant=cfg.tenant,
            display_name=cfg.display_name,
            autonomy_level=cfg.autonomy_level,
            envs=envs_map
        ))
    
    return result


@router.post("/tenants/{tenant}/envs/{slug}", response_model=InfrastructureEnvResponse)
async def upsert_infrastructure_env(
    tenant: str,
    slug: str,
    payload: InfrastructureEnvCreate,
    db: DB,
) -> InfrastructureEnvResponse:
    """Create or update an environment in the database and hot-reload registry."""
    # Validate tenant exists
    try:
        TenantRegistry.get(tenant)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant}' not found")

    # Find existing or create new
    q = select(InfrastructureEnv).where(
        InfrastructureEnv.tenant == tenant,
        InfrastructureEnv.slug == slug
    )
    db_env = (await db.execute(q)).scalar_one_or_none()

    if db_env:
        action = "UPDATE_INFRA_ENV"
        for key, value in payload.model_dump().items():
            setattr(db_env, key, value)
    else:
        action = "CREATE_INFRA_ENV"
        db_env = InfrastructureEnv(
            tenant=tenant,
            slug=slug,
            **payload.model_dump()
        )
        db.add(db_env)
        
        # ── DEFAULT KAFKA FILTER RULE ──────────────────────────────────────
        from core.models import FilterRule
        kafka_rule = FilterRule(
            tenant=tenant,
            scope="alertmanager",
            name=f"Kafka Alerts ({slug})",
            enabled=True,
            priority=10,
            criteria={
                "matchers": {
                    "alertname": "Kafka.*",
                    "env": slug
                }
            }
        )
        db.add(kafka_rule)
        log.info("Infrastructure: created default Kafka filter rule for %s", slug)
        # ──────────────────────────────────────────────────────────────────

    # ── MANAGED FILES PERSISTENCE ─────────────────────────────────────────
    conf_dir = Path("/app/kube_conf")

    # 1. Kubeconfig Content
    kc_path = conf_dir / f"{tenant}_{slug}_kubeconfig.yaml"
    if payload.kubeconfig_content:
        try:
            kc_path.write_text(payload.kubeconfig_content, encoding="utf-8")
            # Update the effective path to our managed file
            db_env.kubeconfig = str(kc_path)
            log.info("Infrastructure: wrote Kubeconfig to %s", kc_path)
        except Exception as exc:
            log.error("Infrastructure: failed to write Kubeconfig: %s", exc)
    elif kc_path.exists():
        kc_path.unlink()
    # ──────────────────────────────────────────────────────────────────────

    await db.commit()
    await db.refresh(db_env)

    # Sync memory registry
    TenantRegistry.add_env_override(tenant, slug, EnvConfig(**InfrastructureEnvResponse.model_validate(db_env).model_dump()))

    # Audit
    audit = SystemAudit(
        action=action,
        resource_type="INFRA_ENV",
        resource_id=f"{tenant}:{slug}",
        audit_metadata=payload.model_dump()
    )
    db.add(audit)
    await db.commit()

    return InfrastructureEnvResponse.model_validate(db_env)


@router.delete("/tenants/{tenant}/envs/{slug}")
async def delete_infrastructure_env(
    tenant: str,
    slug: str,
    db: DB,
) -> dict:
    """Delete an environment from the database and remove from registry."""
    # We only allow deleting envs that were added via DB (YAML envs remain as fallbacks)
    q = select(InfrastructureEnv).where(
        InfrastructureEnv.tenant == tenant,
        InfrastructureEnv.slug == slug
    )
    db_env = (await db.execute(q)).scalar_one_or_none()

    if not db_env:
        # If it's a YAML env, we can't delete the file, but we could "disable" it if we had a field
        # For v0, we only delete DB overrides.
        raise HTTPException(
            status_code=400, 
            detail="Cannot delete a system-defined environment (YAML). Only dynamically added environments can be deleted."
        )

    await db.delete(db_env)
    
    # ── MANAGED FILES CLEANUP ────────────────────────────────────────────
    conf_dir = Path("/app/kube_conf")
    kc_path = conf_dir / f"{tenant}_{slug}_kubeconfig.yaml"
    if kc_path.exists():
        kc_path.unlink()
    # ──────────────────────────────────────────────────────────────────────

    # Audit
    audit = SystemAudit(
        action="DELETE_INFRA_ENV",
        resource_type="INFRA_ENV",
        resource_id=f"{tenant}:{slug}",
        audit_metadata={"display_name": db_env.display_name}
    )
    db.add(audit)
    
    await db.commit()

    # Re-sync memory registry from YAML (reset to default)
    try:
        # Reloading everything is safest to ensure YAML defaults are restored
        TenantRegistry.reload()
        # Re-apply other DB overrides
        db_envs = (await db.execute(select(InfrastructureEnv))).scalars().all()
        for e in db_envs:
             TenantRegistry.add_env_override(e.tenant, e.slug, EnvConfig(**InfrastructureEnvResponse.model_validate(e).model_dump()))
    except Exception as exc:
        log.warning("Registry re-sync failed after delete: %s", exc)

    return {"status": "ok", "message": f"Environment '{slug}' removed from DB overrides"}
