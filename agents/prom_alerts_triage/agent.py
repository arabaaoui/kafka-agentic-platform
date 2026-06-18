"""PromAlertTriageAgent — Prometheus alert triage and false-positive detection."""

from __future__ import annotations

from typing import Any

from core.mission import MissionContext
from agents.base import BaseAgent


class PromAlertTriageAgent(BaseAgent):
    """Audits Prometheus rules and verifies whether a firing alert is genuine."""

    SKILL_NAME = "prom_alerts_triage"

    def __init__(self, *, tenant_config: Any, **kwargs) -> None:
        super().__init__(**kwargs)
        self._tenant_config = tenant_config

    def _build_tools(self):
        from kafka_agent_toolkit.tools.promrule_audit import audit as promrule_audit
        from kafka_agent_toolkit.tools.prom_query import query as prom_query

        promrule_audit.__name__ = "promrule_audit"
        promrule_audit.__doc__ = (
            "Audit a Prometheus alerting rule: check its PromQL expression, "
            "labels, severity, and whether it is likely to fire spuriously."
        )
        prom_query.__name__ = "prom_query"
        prom_query.__doc__ = (
            "Execute a PromQL query against the environment's Prometheus instance. "
            "Returns the query result as a JSON structure."
        )

        return [promrule_audit, prom_query]

    async def investigate(
        self,
        mission_ctx: MissionContext,
        alert_name: str = "",
        alert_namespace: str = "",
        db_conn: Any = None,
    ) -> str:
        env_cfg = self._tenant_config.envs.get(mission_ctx.env.lower())
        prom_url = env_cfg.prom_url if env_cfg else ""
        kubeconfig = env_cfg.kubeconfig if env_cfg else ""

        prompt = (
            f"Mission: {mission_ctx.mission_id}\n"
            f"Env: {mission_ctx.env} | Cluster: {mission_ctx.cluster} | Subject: {mission_ctx.subject}\n"
            f"Alert name (MANDATORY for verification): {alert_name or 'unknown'}\n"
            f"Alert Namespace (Target): {alert_namespace or 'unknown'}\n"
            f"Prometheus URL: {prom_url}\n"
            f"Kubeconfig: {kubeconfig}\n\n"
            "INSTRUCTIONS:\n"
            f"1. Use 'prom_query' with 'ALERTS{{alertname=\"{alert_name}\", alertstate=\"firing\"}}' to verify if the alert is currently active.\n"
            f"2. Use 'promrule_audit' with rule_name=\"{alert_name}\" to check ONLY the rule that is firing. This is crucial for performance.\n"
            "3. Only if the alert is NOT firing, perform a broader investigation.\n"
            "4. Produce a concise alert triage report."
        )
        return await self.run(mission_ctx, prompt, db_conn=db_conn)
