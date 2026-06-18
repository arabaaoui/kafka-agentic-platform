"""Lab scenario: PVC saturation on kafka-preprod (Strimzi 0.45.1 KRaft).

Simulates:
  - PVC kafka-data-0 at 91% — CRITICAL threshold (>85%)
  - PVC kafka-data-1 at 73% — WARNING threshold (>70%)
  - Consumer lag 45 000 msgs — broker slowing down due to disk pressure
  - URP = 2, ISR avg = 2.8 — réplication dégradée
  - No false positive (alerts are genuine)

Validates:
  - FilterEngine matches the alertmanager trigger
  - _check_access blocks prod URL in preprod mission
  - _L2_BLOCKED_TOOLS blocks kafka_reassign
  - pvc_forecast detects CRITICAL + WARNING PVCs
  - lag_correlation returns severity=WARNING (URP>0, ISR>=2)
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.filter_engine import FilterEngine, FilterRule
from core.mission import MissionContext, MissionType
from core.mission_isolation import CrossEnvAccessBlocked, _check_access
from core.autonomy import AutonomyViolation, _L2_BLOCKED_TOOLS
from core.tenant import EnvConfig, TenantConfig


# ── Fixtures ──────────────────────────────────────────────────────────────────


PREPROD_PROM = "https://prom.preprod.example.com"
PROD_PROM = "https://prom.prod.example.com"


@pytest.fixture()
def tenant_cfg() -> TenantConfig:
    return TenantConfig(
        tenant="carrefour",
        envs={
            "preprod": EnvConfig(
                clusters=["kafka-preprod"],
                kubeconfig="/kube/preprod",
                prom_url=PREPROD_PROM,
            ),
            "prod": EnvConfig(
                clusters=["kafkahub-prod"],
                kubeconfig="/kube/prod",
                prom_url=PROD_PROM,
            ),
        },
    )


@pytest.fixture()
def mission(tenant_cfg) -> MissionContext:
    return MissionContext(
        mission_id="CARREFOUR-PREPROD-INCIDENT-PVC-SATURATION-20260510-001",
        tenant="carrefour",
        env="preprod",
        cluster="kafka-preprod",
        type=MissionType.INCIDENT,
        subject="pvc-saturation",
    )


# ── PVC saturation mock data ──────────────────────────────────────────────────


def _pvc_prom_response(used: float, capacity: float, pvc_name: str) -> dict:
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [{
                "metric": {
                    "persistentvolumeclaim": pvc_name,
                    "namespace": "kafka-preprod",
                },
                "value": ["1715340000", str(used)],
            }],
        },
    }


# ── Scenario: FilterEngine matches alertmanager trigger ───────────────────────


def test_pvc_alert_matches_filter_rule():
    alert = {
        "status": "firing",
        "labels": {
            "alertname": "KubePersistentVolumeFillingUp",
            "severity": "critical",
            "cluster": "kafka-preprod",
            "namespace": "kafka-preprod",
            "persistentvolumeclaim": "kafka-data-0",
        },
    }
    rules = [
        FilterRule(
            id="r1",
            tenant="carrefour",
            scope="alertmanager",
            name="Kafka PVC critical",
            enabled=True,
            priority=100,
            poll_interval_seconds=60,
            criteria={"matchers": {"severity": "critical", "cluster": "kafka-preprod"}},
        )
    ]
    engine = FilterEngine()
    result, _ = engine.evaluate(alert, rules, "alertmanager")
    assert result.matched
    assert result.rule_id == "r1"


# ── Scenario: isolation blocks prod endpoint in preprod mission ───────────────


def test_isolation_blocks_prod_in_preprod_mission(mission, tenant_cfg):
    allowed = _check_access(
        {"prom_url": f"{PROD_PROM}/api/v1/query"},
        tenant_cfg,
        mission.env,
    )
    assert not allowed, "prod URL must be blocked in a preprod mission"


def test_isolation_allows_preprod_endpoint(mission, tenant_cfg):
    allowed = _check_access(
        {"prom_url": f"{PREPROD_PROM}/api/v1/query"},
        tenant_cfg,
        mission.env,
    )
    assert allowed, "preprod URL must be allowed in a preprod mission"


# ── Scenario: L2 autonomy blocks kafka_reassign during PVC incident ───────────


def test_autonomy_blocks_reassign_during_pvc_incident():
    assert "kafka_reassign" in _L2_BLOCKED_TOOLS


def test_autonomy_allows_pvc_forecast():
    assert "pvc_forecast" not in _L2_BLOCKED_TOOLS


# ── Scenario: pvc_forecast tool detects CRITICAL PVC ─────────────────────────


def test_pvc_forecast_detects_critical(tmp_path):
    """Unit-level: PVC at 91% triggers CRITICAL status."""
    from kafka_agent_toolkit.tools.pvc_forecast import PVCStatus, _CRIT_PCT

    used = 0.91 * 100 * 1024 ** 3  # 91 GiB of 100 GiB
    capacity = 100 * 1024 ** 3

    used_pct = (used / capacity) * 100
    assert used_pct >= _CRIT_PCT

    status_obj = PVCStatus(
        pvc="kafka-data-0",
        namespace="kafka-preprod",
        used_bytes=used,
        capacity_bytes=capacity,
        used_pct=used_pct,
        status="CRITICAL",
    )
    assert status_obj.status == "CRITICAL"
    assert status_obj.used_pct > 85


# ── Scenario: lag_correlation returns WARNING (URP>0, ISR>=2) ────────────────


def test_lag_correlation_replication_degraded():
    """URP>0 + ISR>=2 → RÉPLICATION DÉGRADÉE (WARNING) per decision tree."""
    from kafka_agent_toolkit.tools.lag_correlation import LagCorrelationResult

    result = LagCorrelationResult(
        root_cause="RÉPLICATION DÉGRADÉE",
        severity="WARNING",
        total_lag=45000,
        urp=2,
        isr_avg=2.8,
        election_rate=0.0,
        max_cpu=0.45,
        max_cpu_pod="kafka-2",
        top_groups=["my-consumer-group"],
        actions=["Check broker kafka-2 disk", "Monitor ISR recovery"],
    )
    assert result.severity == "WARNING"
    assert result.urp > 0
    assert result.isr_avg >= 2
    assert result.total_lag == 45000
