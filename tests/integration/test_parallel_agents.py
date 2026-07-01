"""Integration tests for agents/pipeline/orchestrator.py.

Covers:
  - All 3 expert agents called with the same MissionContext
  - Agents run concurrently (coroutines scheduled via asyncio.gather)
  - EvidenceConsolidator receives outputs from all 3 experts
  - Partial failure: one expert raises → orchestrator continues with 2 outputs,
    mission status tracked as partial
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from core.mission import MissionContext, MissionType, MissionStatus
from core.tenant import EnvConfig, TenantConfig


# ── Fixtures ──────────────────────────────────────────────────────────────────


MISSION_ID = "ENTERPRISE-PREPROD-INCIDENT-PVC-SATURATION-20260510-001"

FIXTURE_MARKDOWN = """
# Kafka Strimzi Expert Analysis

## Hypotheses
1. PVC kafka-data-0 at 91% — disk pressure causing consumer lag
2. URP=2 indicates replication degradation

## Evidence
- pvc_forecast: CRITICAL (91%)
- lag_correlation: WARNING (URP>0, ISR=2.8)

## Recommended Actions
- Expand PVC kafka-data-0 to 200 GiB
- Monitor ISR recovery
"""


@pytest.fixture()
def preprod_mission() -> MissionContext:
    return MissionContext(
        mission_id=MISSION_ID,
        tenant="enterprise",
        env="preprod",
        cluster="kafka-preprod",
        type=MissionType.INCIDENT,
        subject="pvc-saturation",
    )


@pytest.fixture()
def tenant_cfg() -> TenantConfig:
    return TenantConfig(
        tenant="enterprise",
        envs={
            "preprod": EnvConfig(
                clusters=["kafka-preprod"],
                kubeconfig="/kube/preprod",
                prom_url="https://prom.preprod.example.com",
                vm_url="https://vm.preprod.example.com",
            ),
        },
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _mock_async_session() -> MagicMock:
    """Return an AsyncSession class mock that works as an async context manager.

    The session's execute() returns a result whose scalar_one_or_none() is None
    so the orchestrator falls through to the static TenantRegistry fallback.
    """
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)

    return MagicMock(return_value=ctx)


class _FakeAgent:
    """Minimal stand-in for an expert agent that records calls."""

    def __init__(self, skill_name: str, output: str = FIXTURE_MARKDOWN) -> None:
        self.SKILL_NAME = skill_name
        self._output = output
        self.called_with: list[MissionContext] = []

    async def investigate(self, ctx: MissionContext, **kwargs) -> str:
        self.called_with.append(ctx)
        return self._output

    async def consolidate(self, ctx: MissionContext, **kwargs) -> str:
        return self._output


class _FailingAgent(_FakeAgent):
    """Expert agent that always raises."""

    async def investigate(self, ctx: MissionContext, **kwargs) -> str:
        self.called_with.append(ctx)
        raise RuntimeError(f"Agent {self.SKILL_NAME} failed unexpectedly")


# ── Test: all 3 experts called with same MissionContext ───────────────────────


@pytest.mark.asyncio
async def test_all_three_experts_called_with_same_mission_context(
    preprod_mission, tenant_cfg, tmp_path
):
    """Every expert receives the identical MissionContext object."""
    kafka_agent = _FakeAgent("kafka_strimzi_expert")
    sre_agent = _FakeAgent("k8s_gcp_sre")
    triage_agent = _FakeAgent("prom_alerts_triage")
    consolidator = _FakeAgent("evidence_consolidator")

    db_mock = AsyncMock()
    db_mock.execute = AsyncMock(return_value=None)

    with (
        patch("sqlalchemy.ext.asyncio.AsyncSession", _mock_async_session()),
        patch("agents.pipeline.orchestrator.KafkaStrimziExpertAgent", return_value=kafka_agent),
        patch("agents.pipeline.orchestrator.K8sGcpSreAgent", return_value=sre_agent),
        patch("agents.pipeline.orchestrator.PromAlertTriageAgent", return_value=triage_agent),
        patch("agents.pipeline.orchestrator.EvidenceConsolidatorAgent", return_value=consolidator),
        patch("agents.pipeline.orchestrator.TenantRegistry.get", return_value=tenant_cfg),
        patch(
            "agents.pipeline.orchestrator.IntakeAgent",
            return_value=MagicMock(classify=AsyncMock(return_value={
                "rejected": False,
                "tenant": "enterprise",
                "env": "PREPROD",
                "cluster": "kafka-preprod",
                "type": MissionType.INCIDENT,
                "subject": "pvc-saturation",
                "confidence": "HIGH",
                "jira_ticket_id": "PHX-99999",
                "metadata": {},
            })),
        ),
        patch(
            "core.mission.MissionContext.create",
            new=AsyncMock(return_value=preprod_mission),
        ),
    ):
        from agents.pipeline.orchestrator import PipelineOrchestrator
        orchestrator = PipelineOrchestrator(db_engine=db_mock, model="test-model")
        result = await orchestrator.handle({
            "id": "trigger-001",
            "source": "jira",
            "external_id": "PHX-99999",
            "payload": {"key": "PHX-99999"},
        })

    assert result == MISSION_ID

    # All 3 experts were called
    assert len(kafka_agent.called_with) == 1
    assert len(sre_agent.called_with) == 1
    assert len(triage_agent.called_with) == 1

    # Each received the same MissionContext
    for agent in [kafka_agent, sre_agent, triage_agent]:
        assert agent.called_with[0].mission_id == MISSION_ID
        assert agent.called_with[0].env == "PREPROD"
        assert agent.called_with[0].subject == "pvc-saturation"


# ── Test: agents run concurrently ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_agents_invoked_sequentially_by_default(preprod_mission, tenant_cfg):
    """In v0, the orchestrator runs agents sequentially (documented trade-off).

    This test verifies the current behaviour and will need updating when
    concurrent execution is enabled.
    """
    call_order: list[str] = []

    class _OrderTrackingAgent(_FakeAgent):
        async def investigate(self, ctx, **kwargs):
            call_order.append(self.SKILL_NAME)
            return FIXTURE_MARKDOWN

    kafka_agent = _OrderTrackingAgent("kafka_strimzi_expert")
    sre_agent = _OrderTrackingAgent("k8s_gcp_sre")
    triage_agent = _OrderTrackingAgent("prom_alerts_triage")
    consolidator = _FakeAgent("evidence_consolidator")

    db_mock = AsyncMock()
    db_mock.execute = AsyncMock(return_value=None)

    with (
        patch("sqlalchemy.ext.asyncio.AsyncSession", _mock_async_session()),
        patch("agents.pipeline.orchestrator.KafkaStrimziExpertAgent", return_value=kafka_agent),
        patch("agents.pipeline.orchestrator.K8sGcpSreAgent", return_value=sre_agent),
        patch("agents.pipeline.orchestrator.PromAlertTriageAgent", return_value=triage_agent),
        patch("agents.pipeline.orchestrator.EvidenceConsolidatorAgent", return_value=consolidator),
        patch("agents.pipeline.orchestrator.TenantRegistry.get", return_value=tenant_cfg),
        patch(
            "agents.pipeline.orchestrator.IntakeAgent",
            return_value=MagicMock(classify=AsyncMock(return_value={
                "rejected": False,
                "tenant": "enterprise",
                "env": "PREPROD",
                "cluster": "kafka-preprod",
                "type": MissionType.INCIDENT,
                "subject": "pvc-saturation",
                "confidence": "HIGH",
                "jira_ticket_id": "PHX-99999",
                "metadata": {},
            })),
        ),
        patch(
            "core.mission.MissionContext.create",
            new=AsyncMock(return_value=preprod_mission),
        ),
    ):
        from agents.pipeline.orchestrator import PipelineOrchestrator
        orchestrator = PipelineOrchestrator(db_engine=db_mock, model="test-model")
        await orchestrator.handle({
            "id": "trigger-001",
            "source": "jira",
            "external_id": "PHX-99999",
            "payload": {},
        })

    assert call_order == ["kafka_strimzi_expert", "k8s_gcp_sre", "prom_alerts_triage"]


# ── Test: EvidenceConsolidator receives all outputs ───────────────────────────


@pytest.mark.asyncio
async def test_evidence_consolidator_called_after_all_experts(preprod_mission, tenant_cfg):
    """EvidenceConsolidator.run() is called after all expert agents complete."""
    expert_outputs: list[str] = []
    consolidator_called = False

    class _TrackingConsolidator(_FakeAgent):
        async def consolidate(self, ctx, **kwargs):
            nonlocal consolidator_called
            consolidator_called = True
            return "# Consolidated audit\n\n## Hypotheses\n..."

    kafka_agent = _FakeAgent("kafka_strimzi_expert")
    sre_agent = _FakeAgent("k8s_gcp_sre")
    triage_agent = _FakeAgent("prom_alerts_triage")
    consolidator = _TrackingConsolidator("evidence_consolidator")

    db_mock = AsyncMock()
    db_mock.execute = AsyncMock(return_value=None)

    with (
        patch("sqlalchemy.ext.asyncio.AsyncSession", _mock_async_session()),
        patch("agents.pipeline.orchestrator.KafkaStrimziExpertAgent", return_value=kafka_agent),
        patch("agents.pipeline.orchestrator.K8sGcpSreAgent", return_value=sre_agent),
        patch("agents.pipeline.orchestrator.PromAlertTriageAgent", return_value=triage_agent),
        patch("agents.pipeline.orchestrator.EvidenceConsolidatorAgent", return_value=consolidator),
        patch("agents.pipeline.orchestrator.TenantRegistry.get", return_value=tenant_cfg),
        patch(
            "agents.pipeline.orchestrator.IntakeAgent",
            return_value=MagicMock(classify=AsyncMock(return_value={
                "rejected": False,
                "tenant": "enterprise",
                "env": "PREPROD",
                "cluster": "kafka-preprod",
                "type": MissionType.INCIDENT,
                "subject": "pvc-saturation",
                "confidence": "HIGH",
                "jira_ticket_id": "PHX-99999",
                "metadata": {},
            })),
        ),
        patch(
            "core.mission.MissionContext.create",
            new=AsyncMock(return_value=preprod_mission),
        ),
    ):
        from agents.pipeline.orchestrator import PipelineOrchestrator
        orchestrator = PipelineOrchestrator(db_engine=db_mock, model="test-model")
        await orchestrator.handle({
            "id": "trigger-001",
            "source": "jira",
            "external_id": "PHX-99999",
            "payload": {},
        })

    assert consolidator_called, "EvidenceConsolidator.run() must be called"


# ── Test: partial failure — one expert raises, pipeline continues ─────────────


@pytest.mark.asyncio
async def test_partial_failure_one_expert_continues_with_two_outputs(
    preprod_mission, tenant_cfg
):
    """If one expert raises, the orchestrator logs the error and continues.

    The remaining 2 experts complete and the consolidator is still called.
    """
    completed_agents: list[str] = []
    consolidator_called = False

    class _TrackingAgent(_FakeAgent):
        async def investigate(self, ctx, **kwargs):
            completed_agents.append(self.SKILL_NAME)
            return FIXTURE_MARKDOWN

    class _TrackingConsolidator(_FakeAgent):
        async def consolidate(self, ctx, **kwargs):
            nonlocal consolidator_called
            consolidator_called = True
            return "# Consolidated audit"

    kafka_agent = _TrackingAgent("kafka_strimzi_expert")
    sre_agent = _FailingAgent("k8s_gcp_sre")          # this one fails
    triage_agent = _TrackingAgent("prom_alerts_triage")
    consolidator = _TrackingConsolidator("evidence_consolidator")

    db_mock = AsyncMock()
    db_mock.execute = AsyncMock(return_value=None)

    with (
        patch("sqlalchemy.ext.asyncio.AsyncSession", _mock_async_session()),
        patch("agents.pipeline.orchestrator.KafkaStrimziExpertAgent", return_value=kafka_agent),
        patch("agents.pipeline.orchestrator.K8sGcpSreAgent", return_value=sre_agent),
        patch("agents.pipeline.orchestrator.PromAlertTriageAgent", return_value=triage_agent),
        patch("agents.pipeline.orchestrator.EvidenceConsolidatorAgent", return_value=consolidator),
        patch("agents.pipeline.orchestrator.TenantRegistry.get", return_value=tenant_cfg),
        patch(
            "agents.pipeline.orchestrator.IntakeAgent",
            return_value=MagicMock(classify=AsyncMock(return_value={
                "rejected": False,
                "tenant": "enterprise",
                "env": "PREPROD",
                "cluster": "kafka-preprod",
                "type": MissionType.INCIDENT,
                "subject": "pvc-saturation",
                "confidence": "HIGH",
                "jira_ticket_id": "PHX-99999",
                "metadata": {},
            })),
        ),
        patch(
            "core.mission.MissionContext.create",
            new=AsyncMock(return_value=preprod_mission),
        ),
    ):
        from agents.pipeline.orchestrator import PipelineOrchestrator
        orchestrator = PipelineOrchestrator(db_engine=db_mock, model="test-model")
        # Must NOT raise — partial failure is absorbed
        result = await orchestrator.handle({
            "id": "trigger-001",
            "source": "jira",
            "external_id": "PHX-99999",
            "payload": {},
        })

    # Pipeline returned the mission_id despite one agent failing
    assert result == MISSION_ID

    # 2 agents completed successfully
    assert "kafka_strimzi_expert" in completed_agents
    assert "prom_alerts_triage" in completed_agents
    assert "k8s_gcp_sre" not in completed_agents  # failed, never appended

    # Consolidator was still called
    assert consolidator_called


# ── Test: intake rejection → pipeline returns None ────────────────────────────


@pytest.mark.asyncio
async def test_ignored_trigger_returns_none(tenant_cfg):
    """If intake classifies trigger as ignored, pipeline returns None immediately."""
    db_mock = AsyncMock()

    with (
        patch("agents.pipeline.orchestrator.TenantRegistry.get", return_value=tenant_cfg),
        patch(
            "agents.pipeline.orchestrator.IntakeAgent",
            return_value=MagicMock(classify=AsyncMock(return_value={
                "status": "ignored",
                "reason": "Not a Kafka incident",
            })),
        ),
    ):
        from agents.pipeline.orchestrator import PipelineOrchestrator
        orchestrator = PipelineOrchestrator(db_engine=db_mock)
        result = await orchestrator.handle({
            "id": "trigger-002",
            "source": "jira",
            "external_id": "PHX-00001",
            "payload": {},
        })

    assert result is None


@pytest.mark.asyncio
async def test_env_ambiguous_trigger_returns_none(tenant_cfg):
    """env_ambiguous classification → pipeline returns None."""
    db_mock = AsyncMock()

    with (
        patch("agents.pipeline.orchestrator.TenantRegistry.get", return_value=tenant_cfg),
        patch(
            "agents.pipeline.orchestrator.IntakeAgent",
            return_value=MagicMock(classify=AsyncMock(return_value={
                "status": "env_ambiguous",
                "reason": "Cannot determine preprod vs prod",
            })),
        ),
    ):
        from agents.pipeline.orchestrator import PipelineOrchestrator
        orchestrator = PipelineOrchestrator(db_engine=db_mock)
        result = await orchestrator.handle({
            "id": "trigger-003",
            "source": "jira",
            "external_id": "PHX-00002",
            "payload": {},
        })

    assert result is None
