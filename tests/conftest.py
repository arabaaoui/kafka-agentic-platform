"""Shared pytest fixtures for kafka-agentic-platform tests."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.mission import MissionContext, MissionType
from core.tenant import EnvConfig, TenantConfig


# ── Mission fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def preprod_mission() -> MissionContext:
    return MissionContext(
        mission_id="ENTERPRISE-PREPROD-INCIDENT-PVC-SATURATION-20260510-001",
        tenant="enterprise",
        env="preprod",
        cluster="kafka-preprod",
        type=MissionType.INCIDENT,
        subject="pvc-saturation",
    )


@pytest.fixture()
def prod_mission() -> MissionContext:
    return MissionContext(
        mission_id="ENTERPRISE-PROD-INCIDENT-LAG-URP-20260510-001",
        tenant="enterprise",
        env="prod",
        cluster="kafkahub-prod",
        type=MissionType.INCIDENT,
        subject="lag-urp",
    )


# ── Tenant config fixtures ────────────────────────────────────────────────────


@pytest.fixture()
def tenant_config() -> TenantConfig:
    return TenantConfig(
        tenant="enterprise",
        envs={
            "preprod": EnvConfig(
                clusters=["kafka-preprod", "kafka-v1-preprod"],
                kubeconfig="/kube/preprod",
                prom_url="https://prom.preprod.example.com",
                vm_url="https://vm.preprod.example.com",
            ),
            "prod": EnvConfig(
                clusters=["kafkahub-prod"],
                kubeconfig="/kube/prod",
                prom_url="https://prom.prod.example.com",
                vm_url="https://vm.prod.example.com",
            ),
        },
    )


@pytest.fixture()
def tenant_yaml(tmp_path) -> Path:
    """Write enterprise.yaml to a temp dir and return the dir path."""
    content = textwrap.dedent("""\
        tenant: enterprise
        envs:
          preprod:
            clusters: [kafka-preprod]
            kubeconfig: /kube/preprod
            prom_url: https://prom.preprod.example.com
          prod:
            clusters: [kafkahub-prod]
            kubeconfig: /kube/prod
            prom_url: https://prom.prod.example.com
    """)
    (tmp_path / "enterprise.yaml").write_text(content)
    return tmp_path


# ── Plugin chain fixtures ─────────────────────────────────────────────────────


@pytest.fixture()
def audit_path(tmp_path) -> Path:
    return tmp_path / "audit.jsonl"


# ── Mock DB connection ────────────────────────────────────────────────────────


@pytest.fixture()
def mock_db() -> AsyncMock:
    """asyncpg-style connection mock."""
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value={"seq": 1})
    db.fetch = AsyncMock(return_value=[])
    db.execute = AsyncMock(return_value=None)
    return db


# ── Prometheus response factories ─────────────────────────────────────────────


def prom_instant_response(metric: dict, value: float) -> dict:
    """Build a Prometheus instant query response dict (vector result)."""
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [{"metric": metric, "value": ["1715340000", str(value)]}],
        },
    }


def prom_empty_response() -> dict:
    return {"status": "success", "data": {"resultType": "vector", "result": []}}
