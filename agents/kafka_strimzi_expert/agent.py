"""KafkaStrimziExpertAgent — Kafka/Strimzi layer investigation."""

from __future__ import annotations

from typing import Any

from core.mission import MissionContext
from agents.base import BaseAgent


class KafkaStrimziExpertAgent(BaseAgent):
    """Investigates Kafka/Strimzi layer: lag, URP/ISR, PVC, cluster health."""

    SKILL_NAME = "kafka_strimzi_expert"

    def __init__(self, *, tenant_config: Any, **kwargs) -> None:
        super().__init__(**kwargs)
        self._tenant_config = tenant_config

    def _build_tools(self):
        from kafka_agent_toolkit.tools.lag_correlation import analyze as lag_correlation
        from kafka_agent_toolkit.tools.pvc_forecast import analyze as pvc_forecast
        from kafka_agent_toolkit.tools.cluster_health import check as cluster_health
        from kafka_agent_toolkit.tools.prom_query import query as prom_query
        from kafka_agent_toolkit.tools.k8s_client import run_kubectl

        lag_correlation.__name__ = "kafka_lag_analysis"
        lag_correlation.__doc__ = (
            "Analyze Kafka consumer group lag across partitions. "
            "Returns lag per partition, consumer group, and topic."
        )
        pvc_forecast.__name__ = "disk_usage_forecast"
        pvc_forecast.__doc__ = (
            "Forecast Kafka broker disk usage based on current throughput and retention. "
            "Returns estimated time to full disk and usage trend."
        )
        cluster_health.__name__ = "cluster_health_check"
        cluster_health.__doc__ = (
            "Check Kafka cluster health: broker status, under-replicated partitions, ISR. "
            "Returns a structured health report with severity."
        )
        prom_query.__name__ = "prom_query"
        prom_query.__doc__ = (
            "Execute a PromQL query against the environment's Prometheus instance. "
            "Returns the query result as a JSON structure."
        )
        run_kubectl.__name__ = "kubectl"
        run_kubectl.__doc__ = (
            "Run a kubectl command against the environment's Kubernetes cluster. "
            "Returns command stdout/stderr. Read-only commands only at autonomy L2."
        )

        return [cluster_health, lag_correlation, pvc_forecast, prom_query, run_kubectl]

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
        kafka_ns = env_cfg.kafka_namespace if env_cfg else "kafka"

        prompt = (
            f"Mission: {mission_ctx.mission_id}\n"
            f"Env: {mission_ctx.env} | Cluster: {mission_ctx.cluster} | Subject: {mission_ctx.subject}\n"
            f"Alert name (if known): {alert_name or 'unknown'}\n"
            f"Alert Namespace (Target): {alert_namespace or 'unknown'}\n"
            f"Prometheus URL: {prom_url}\n"
            f"Kubeconfig: {kubeconfig}\n"
            f"Kafka Namespace (System): {kafka_ns}\n\n"
            "INSTRUCTIONS:\n"
            "1. Start your investigation in the 'Alert Namespace' provided above.\n"
            "2. Execute your mandatory first gestures (cluster_health_check, kafka_lag_analysis, disk_usage_forecast).\n"
            "3. CRITICAL: If 'cluster_health_check' reports a CRITICAL status (e.g. Pending pods or Lost PVCs), "
            "you MUST prioritize this information in your verdict, even if metrics like lag or URP are 0. "
            "Explain that metrics might be stale if the infrastructure is unstable.\n"
            "4. Produce the full investigation report."
        )
        return await self.run(mission_ctx, prompt, db_conn=db_conn)
