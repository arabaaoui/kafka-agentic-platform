"""Pipeline orchestrator — IntakeAgent → ParallelAgent(3 experts) → EvidenceConsolidator.

Triggered by a mission_queue item from the Jira poller or alertmanager webhook.
Follows the architecture in spec 001 US1:
  - IntakeAgent
  - Parallel agents (Kafka, SRE, Triage)
  - EvidenceConsolidator
"""

from __future__ import annotations

import logging
import os
import asyncio
from pathlib import Path
from typing import Any

from agents.base import BaseAgent
from agents.intake.agent import IntakeAgent
from agents.kafka_strimzi_expert.agent import KafkaStrimziExpertAgent
from agents.k8s_gcp_sre.agent import K8sGcpSreAgent
from agents.prom_alerts_triage.agent import PromAlertTriageAgent
from agents.evidence_consolidator.agent import EvidenceConsolidatorAgent
from agents.post_mortem_analyst.agent import PostMortemAgent
from core.mission import MissionContext, MissionStatus
from core.models import Mission
from core.tenant import TenantRegistry, TenantConfig, EnvConfig

log = logging.getLogger(__name__)

_AUDIT_BASE = Path(os.getenv("AUDIT_DIR", "/app/audits"))


class PipelineOrchestrator:
    """Orchestrates the investigation pipeline for a single mission."""

    def __init__(
        self,
        *,
        db_engine: Any,
        model: str = "gemini-2.5-flash-lite",
    ) -> None:
        self._engine = db_engine
        self._model = model

    async def handle(self, queue_item: dict[str, Any]) -> str | None:
        """Run the full pipeline for a trigger item."""
        source = queue_item.get("source", "unknown")
        ext_id = queue_item.get("external_id", "unknown")
        payload = queue_item.get("payload", {})

        log.info("Pipeline: starting for %s:%s", source, ext_id)

        # 1. Intake & Classification (needs a temporary session)
        from sqlalchemy.ext.asyncio import AsyncSession
        async with AsyncSession(self._engine) as session:
            intake = IntakeAgent(model=self._model)
            classification = await intake.classify(
                source=source,
                trigger_payload=payload,
                tenant="enterprise", # Default tenant for lookup
            )

            if not classification:
                log.error("Pipeline: classification failed (IntakeAgent returned None)")
                return None

            if classification.get("status") in ("ignored", "env_ambiguous"):
                log.info("Pipeline: trigger %s — %s", classification["status"], classification.get("reason"))
                return None

            # 2. Mission Creation
            cluster = classification.get("cluster")
            if not cluster:
                # Try to infer cluster from env config if only one is present
                try:
                    tenant_cfg = TenantRegistry.get(classification["tenant"])
                    env_slug = classification["env"].lower()
                    env_cfg = tenant_cfg.envs.get(env_slug)
                    if env_cfg and env_cfg.clusters:
                        cluster = env_cfg.clusters[0]
                except Exception:
                    pass
            
            if not cluster:
                cluster = "unknown"

            trigger_id = queue_item.get("id")

            mission_ctx = await MissionContext.create(
                db_conn=session,
                tenant=classification["tenant"],
                env=classification["env"],
                cluster=cluster,
                type=classification["type"],
                subject=classification["subject"],
                trigger_id=trigger_id,
                metadata=classification.get("metadata", {}),
            )

            # ── TRIGGER LINKAGE ──────────────────────────────────────────────────
            # Update the trigger with the new mission_id to enable UI linking.
            from sqlalchemy import text
            await session.execute(
                text("UPDATE triggers SET mission_id = :mid, processed_at = now() WHERE id = :tid"),
                {"mid": mission_ctx.mission_id, "tid": trigger_id}
            )
            # ──────────────────────────────────────────────────────────────────

            await session.commit()
            
        log.info("Pipeline: mission created → %s", mission_ctx.mission_id)

        # 3. Parallel Expert Investigations
        # ── MISSION-SPECIFIC CONFIG (Isolation & GKE Auth Fix) ────────────────
        from core.models import InfrastructureEnv
        from sqlalchemy import select
        
        tenant_name = classification["tenant"]
        env_slug = classification["env"].lower()
        
        async with AsyncSession(self._engine) as session:
            # 1. Try to load config from DB first (Source of Truth for dynamic envs)
            stmt = select(InfrastructureEnv).where(
                InfrastructureEnv.tenant.ilike(tenant_name),
                InfrastructureEnv.slug.ilike(env_slug)
            )
            db_env = (await session.execute(stmt)).scalar_one_or_none()
            
            if db_env:
                log.info("Pipeline: using DB configuration for env %s/%s", tenant_name, env_slug)
                mission_env_cfg = EnvConfig(
                    display_name=db_env.display_name,
                    badge_color=db_env.badge_color,
                    clusters=db_env.clusters,
                    kubeconfig=db_env.kubeconfig,
                    kube_context=db_env.kube_context,
                    kubeconfig_content=db_env.kubeconfig_content,
                    kafka_namespace=db_env.kafka_namespace,
                    prom_url=db_env.prom_url,
                    alertmanager_url=db_env.alertmanager_url,
                    proxy_url=db_env.proxy_url,
                    proxy_user=db_env.proxy_user,
                    proxy_pass=db_env.proxy_pass,
                    vm_url=db_env.vm_url,
                    target_gsa_email=db_env.target_gsa_email,
                )
            else:
                # 2. Fallback to static YAML registry
                log.info("Pipeline: env %s/%s not in DB, falling back to registry", tenant_name, env_slug)
                tenant_config = TenantRegistry.get(tenant_name)
                env_cfg_source = tenant_config.envs.get(env_slug)
                if not env_cfg_source:
                    log.error("Pipeline: environment '%s' not found in registry", env_slug)
                    return None
                mission_env_cfg = EnvConfig(**env_cfg_source.model_dump())

        # ── GKE AUTH PATCHING ─────────────────────────────────────────────────
        # If it's a GKE environment, get a fresh token (ADC or Impersonation)
        if mission_env_cfg.kubeconfig_content:
            from core.gcp import GCPTokenProvider
            import yaml
            try:
                # 1. Get fresh token (Try impersonation first)
                target_gsa = getattr(mission_env_cfg, "target_gsa_email", None)
                try:
                    token = await GCPTokenProvider.get_token(target_gsa_email=target_gsa)
                    log.info("Pipeline: GKE token acquired via impersonation for %s", target_gsa)
                except Exception as gcp_exc:
                    log.warning("Pipeline: impersonation failed for %s (%s). Falling back to ADC token.", target_gsa, gcp_exc)
                    # Fallback to base ADC token (current user/identity)
                    token = await GCPTokenProvider.get_token(target_gsa_email=None)
                    log.info("Pipeline: GKE token acquired via local ADC fallback")

                # 2. Patch Kubeconfig content in memory
                data = yaml.safe_load(mission_env_cfg.kubeconfig_content)
                if "users" in data:
                    for u in data["users"]:
                        if "user" in u:
                            u["user"].pop("exec", None)
                            u["user"]["token"] = token
                
                # 3. Materialize a MISSION-SPECIFIC Kubeconfig file
                mission_kc_path = _AUDIT_BASE / mission_ctx.mission_id / "kubeconfig.yaml"
                mission_kc_path.parent.mkdir(parents=True, exist_ok=True)
                mission_kc_path.write_text(yaml.dump(data), encoding="utf-8")
                
                # 4. Point this mission's config to the local file
                mission_env_cfg.kubeconfig = str(mission_kc_path)
                log.info("Pipeline: dynamic GKE token injected for mission %s", mission_ctx.mission_id)
            except Exception as exc:
                log.error("Pipeline: failed to generate dynamic GKE token: %s", exc)
        # ──────────────────────────────────────────────────────────────────────

        # Create a transient tenant config for this mission experts
        tenant_config = TenantRegistry.get(tenant_name) # Need for autonomy level etc
        mission_tenant_config = TenantConfig(
            tenant=tenant_config.tenant,
            display_name=tenant_config.display_name,
            autonomy_level=tenant_config.autonomy_level,
            envs={env_slug: mission_env_cfg}
        )

        # Extract alert details for expert agents
        alert_name = ""
        alert_namespace = ""
        if source == "alertmanager":
            alert_name = payload.get("labels", {}).get("alertname", "")
            alert_namespace = payload.get("labels", {}).get("namespace", "")
        elif source == "jira":
            alert_name = mission_ctx.subject

        # Factory for isolated agents — audit path is unique per agent; plugins built in BaseAgent.run()
        def build_expert(agent_cls: type[BaseAgent]) -> BaseAgent:
            return agent_cls(tenant_config=mission_tenant_config, model=self._model)

        experts = [
            build_expert(KafkaStrimziExpertAgent),
            build_expert(K8sGcpSreAgent),
            build_expert(PromAlertTriageAgent),
        ]

        async def run_expert(agent: BaseAgent, delay: float = 0.0) -> None:
            if delay > 0:
                await asyncio.sleep(delay)
            log.info("Pipeline: starting agent %s for mission %s", agent.SKILL_NAME, mission_ctx.mission_id)
            try:
                # Each agent gets its own database session for persistence
                # AsyncSession is not serializable — never pass via session.state
                async with AsyncSession(self._engine) as agent_session:
                    agent_ctx = mission_ctx.model_copy(update={"db_session": agent_session})
                    await agent.investigate(
                        agent_ctx,
                        alert_name=alert_name,
                        alert_namespace=alert_namespace,
                        db_conn=agent_session,
                    )
                    await agent_session.commit()
                log.info("Pipeline: agent %s completed successfully", agent.SKILL_NAME)
            except Exception as exc:
                log.error("Pipeline: agent %s failed for mission %s: %s", agent.SKILL_NAME, mission_ctx.mission_id, exc, exc_info=True)

        log.info("Pipeline: spawning 3 expert agents in parallel")
        await asyncio.gather(*(run_expert(agent) for agent in experts))

        # 4. Evidence Consolidation
        consolidator = EvidenceConsolidatorAgent(tenant_config=mission_tenant_config, model=self._model)
        
        log.info("Pipeline: consolidating evidence")
        async with AsyncSession(self._engine) as session:
            await consolidator.consolidate(mission_ctx, db_conn=session)
            await session.commit()

        log.info("Pipeline: mission %s consolidated", mission_ctx.mission_id)

        # 5. Post-Mortem & RAG Indexing (Auto-triggered)
        # We must refetch the mission from the DB to get the final status
        # set by the consolidator.
        from sqlalchemy import select
        async with AsyncSession(self._engine) as session:
            stmt = select(Mission).where(Mission.mission_id == mission_ctx.mission_id)
            refreshed_mission = (await session.execute(stmt)).scalar_one_or_none()
            if refreshed_mission:
                # MissionContext is frozen, use model_copy
                mission_ctx = mission_ctx.model_copy(update={"status": MissionStatus(refreshed_mission.status)})

        if mission_ctx.status in (MissionStatus.CLOSED, MissionStatus.PARTIAL):
            log.info("Pipeline: auto-triggering post-mortem for mission %s", mission_ctx.mission_id)
            post_mortem_agent = PostMortemAgent(tenant_config=mission_tenant_config, model=self._model)
            try:
                async with AsyncSession(self._engine) as session:
                    await post_mortem_agent.finalize(mission_ctx, db_conn=session)
                    await session.commit()
                log.info("Pipeline: post-mortem and RAG indexing complete for %s", mission_ctx.mission_id)
            except Exception:
                log.exception(
                    "Pipeline: post-mortem agent failed for mission %s. RAG indexing will be skipped.",
                    mission_ctx.mission_id,
                )

        log.info("Pipeline: mission %s processing finished", mission_ctx.mission_id)
        return mission_ctx.mission_id


