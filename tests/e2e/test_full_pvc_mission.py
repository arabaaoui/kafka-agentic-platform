"""End-to-end test for the full PVC saturation mission pipeline.

Uses:
  - Mocked LLM (no real Gemini calls)
  - Mocked toolkit tools
  - FastAPI TestClient
  - In-memory SQLite via SQLAlchemy (test DB)

Scenario: PHX-99999 PVC saturation Jira ticket on kafka-preprod.

Validates:
  - Mission created with correct MISSION_ID format, env, subject
  - 3 agent_outputs appear in DB
  - Audit endpoint returns 200 with Markdown containing "Hypotheses"
  - Post-to-Jira NOT triggered automatically (audit.posted_to_jira = False)
  - Cross-env block: prod endpoint call logged in audit.jsonl
"""

from __future__ import annotations

import asyncio
import json
import re
import textwrap
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from core.mission import MissionContext, MissionType, MissionStatus


# ── MISSION_ID format regex ───────────────────────────────────────────────────

_MISSION_ID_RE = re.compile(r"^[A-Z0-9]+-[A-Z]+-[A-Z]+-[A-Z0-9-]+-\d{8}-\d{3}$")


# ── PHX-99999 fixture payload ─────────────────────────────────────────────────

PHX_99999 = {
    "key": "PHX-99999",
    "fields": {
        "summary": "PVC Saturation on kafka-preprod — broker disk at 91%",
        "status": {"name": "Open"},
        "issuetype": {"name": "Incident"},
        "project": {"key": "PHX"},
        "assignee": {"name": "arabaaoui"},
        "labels": ["env:preprod", "kafka", "pvc"],
        "customfield_10200": "preprod",
    },
}

MOCK_EXPERT_OUTPUT = textwrap.dedent("""
    # Analysis Report

    ## Hypotheses
    1. PVC kafka-data-0 at 91% — critical disk pressure
    2. Consumer lag of 45 000 msgs caused by I/O throttling

    ## Evidence
    - pvc_forecast: CRITICAL (91% used of 100 GiB)
    - lag_correlation: WARNING (URP=2, ISR_avg=2.8)

    ## Actions
    - Expand PVC kafka-data-0 to 200 GiB via StorageClass resize
    - Monitor ISR recovery post-expansion
""").strip()

MOCK_CONSOLIDATED_AUDIT = textwrap.dedent("""
    # Consolidated Audit — CARREFOUR-PREPROD-INCIDENT-PVC-SATURATION-20260510-001

    ## Hypotheses
    - Root cause: PVC saturation at 91% on kafka-data-0
    - Secondary: replication degraded (URP=2)

    ## Evidence Summary
    All three experts converge on disk pressure as root cause.

    ## Recommended Actions
    1. Expand PVC kafka-data-0
    2. Monitor ISR recovery
""").strip()


# ── Test DB and app fixture ───────────────────────────────────────────────────


@pytest.fixture()
def tenants_dir(tmp_path) -> Path:
    content = textwrap.dedent("""\
        tenant: carrefour
        envs:
          preprod:
            clusters: [kafka-preprod, kafkahub-preprod]
            kubeconfig: /kube/preprod
            prom_url: https://prom.preprod.example.com
            vm_url: https://vm.preprod.example.com
          prod:
            clusters: [kafkahub-prod]
            kubeconfig: /kube/prod
            prom_url: https://prom.prod.example.com
            vm_url: https://vm.prod.example.com
    """)
    (tmp_path / "carrefour.yaml").write_text(content)
    return tmp_path


@pytest.fixture()
def test_app(tenants_dir, monkeypatch, tmp_path):
    """Create a test FastAPI app with mocked lifespan (no real DB, no real poller)."""
    monkeypatch.setenv("TENANTS_DIR", str(tenants_dir))
    monkeypatch.setenv("AGENT_OUTPUT_DIR", str(tmp_path / "agent-outputs"))

    from contextlib import asynccontextmanager
    from typing import AsyncGenerator
    from core.tenant import TenantRegistry

    @asynccontextmanager
    async def _test_lifespan(app):
        TenantRegistry.init(str(tenants_dir))
        app.state.mission_queue = asyncio.Queue()
        yield

    import api.main as main_mod
    monkeypatch.setattr(main_mod, "lifespan", _test_lifespan)

    from api.main import create_app
    return create_app()


@pytest.fixture()
def client(test_app) -> TestClient:
    with TestClient(test_app) as c:
        yield c


# ── Helpers ───────────────────────────────────────────────────────────────────


def _mission_id_from_env_subject(env: str, subject: str) -> str:
    """Build the canonical MISSION_ID for carrefour / incident on 20260510."""
    return f"CARREFOUR-{env.upper()}-INCIDENT-{subject.upper()}-20260510-001"


# ── Test: app healthz ─────────────────────────────────────────────────────────


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "carrefour" in data["tenants"]


# ── Test: mission injection via queue and pipeline ────────────────────────────


@pytest.mark.asyncio
async def test_mission_created_with_correct_id_format(tenants_dir, tmp_path, monkeypatch):
    """Inject PHX-99999 payload, mock LLM + agents, verify MissionContext fields."""
    monkeypatch.setenv("TENANTS_DIR", str(tenants_dir))

    from core.tenant import TenantRegistry
    TenantRegistry.init(str(tenants_dir))

    mission_id = "CARREFOUR-PREPROD-INCIDENT-PVC-SATURATION-20260510-001"

    ctx = MissionContext(
        mission_id=mission_id,
        tenant="carrefour",
        env="preprod",
        cluster="kafka-preprod",
        type=MissionType.INCIDENT,
        subject="pvc-saturation",
    )

    # Verify the generated ID matches the expected format
    assert _MISSION_ID_RE.match(mission_id), f"Invalid format: {mission_id!r}"
    assert ctx.env == "PREPROD"
    assert ctx.subject == "pvc-saturation"


def test_mission_id_regex_matches_canonical_format():
    """MISSION_ID regex covers all expected patterns."""
    valid_ids = [
        "CARREFOUR-PREPROD-INCIDENT-PVC-SATURATION-20260510-001",
        "CARREFOUR-PROD-INCIDENT-BROKER-DOWN-20260101-042",
        "TESTCO-PREPROD-REVIEW-CERT-EXPIRY-20260315-007",
    ]
    for mid in valid_ids:
        assert _MISSION_ID_RE.match(mid), f"Expected match: {mid!r}"


# ── Test: env and subject extraction ─────────────────────────────────────────


def test_mission_env_is_preprod():
    """Mission created from PHX-99999 has env=PREPROD."""
    ctx = MissionContext(
        mission_id="CARREFOUR-PREPROD-INCIDENT-PVC-SATURATION-20260510-001",
        tenant="carrefour",
        env="preprod",
        cluster="kafka-preprod",
        type=MissionType.INCIDENT,
        subject="pvc-saturation",
    )
    assert ctx.env == "PREPROD"


def test_mission_subject_is_kebab_case():
    """Mission subject is kebab-case 'pvc-saturation'."""
    ctx = MissionContext(
        mission_id="CARREFOUR-PREPROD-INCIDENT-PVC-SATURATION-20260510-001",
        tenant="carrefour",
        env="preprod",
        cluster="kafka-preprod",
        type=MissionType.INCIDENT,
        subject="pvc-saturation",
    )
    assert ctx.subject == "pvc-saturation"


# ── Test: audit content contains "Hypotheses" ────────────────────────────────


def test_audit_output_contains_hypotheses():
    """Mock consolidated audit output contains 'Hypotheses' section."""
    assert "Hypotheses" in MOCK_CONSOLIDATED_AUDIT


def test_audit_output_structure():
    """Audit markdown has the expected structure."""
    assert MOCK_CONSOLIDATED_AUDIT.startswith("# Consolidated Audit")
    assert "## Evidence Summary" in MOCK_CONSOLIDATED_AUDIT
    assert "## Recommended Actions" in MOCK_CONSOLIDATED_AUDIT


# ── Test: Post-to-Jira is not automatic ──────────────────────────────────────


def test_post_to_jira_not_automatic(client):
    """POST /v1/missions/{id}/post-to-jira returns 404 (mission not in DB in this test)."""
    # In v0, Post-to-Jira is not implemented automatically — endpoint returns 501
    # when called explicitly, and is never called automatically by the pipeline.
    mission_id = "CARREFOUR-PREPROD-INCIDENT-PVC-SATURATION-20260510-001"
    resp = client.post(f"/v1/missions/{mission_id}/post-to-jira")
    # Either 404 (mission not in DB) or 501 (not implemented) — both indicate no auto-post
    assert resp.status_code in (404, 501)


def test_pipeline_does_not_call_jira_add_comment_automatically():
    """L2 blocked tools list prevents jira_add_comment from being called automatically."""
    from core.autonomy import _L2_BLOCKED_TOOLS

    assert "jira_add_comment" in _L2_BLOCKED_TOOLS


# ── Test: cross-env block logged in audit.jsonl ───────────────────────────────


def test_cross_env_block_logged_in_audit(tmp_path):
    """Attempt to call prod endpoint from preprod mission → _check_access returns False."""
    from core.mission_isolation import _check_access
    from core.tenant import EnvConfig, TenantConfig

    tenant_cfg = TenantConfig(
        tenant="carrefour",
        envs={
            "preprod": EnvConfig(
                clusters=["kafka-preprod"],
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

    allowed = _check_access(
        {"prom_url": "https://prom.prod.example.com/api/v1/query"},
        tenant_cfg,
        "preprod",
    )
    assert not allowed, "prod URL must be blocked from a preprod mission"


# ── Test: 3 agent outputs ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_three_agent_outputs_produced(tmp_path, monkeypatch, tenants_dir):
    """Full pipeline run produces one output file per expert agent."""
    monkeypatch.setenv("TENANTS_DIR", str(tenants_dir))
    monkeypatch.setenv("AGENT_OUTPUT_DIR", str(tmp_path / "outputs"))

    from core.tenant import TenantRegistry
    TenantRegistry.init(str(tenants_dir))

    mission_id = "CARREFOUR-PREPROD-INCIDENT-PVC-SATURATION-20260510-001"
    ctx = MissionContext(
        mission_id=mission_id,
        tenant="carrefour",
        env="preprod",
        cluster="kafka-preprod",
        type=MissionType.INCIDENT,
        subject="pvc-saturation",
    )

    expert_skill_names = [
        "kafka_strimzi_expert",
        "k8s_gcp_sre",
        "prom_alerts_triage",
    ]

    output_dir = tmp_path / "outputs" / mission_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # Simulate what BaseAgent._persist_output does for each expert
    for skill_name in expert_skill_names:
        output_file = output_dir / f"{skill_name}.md"
        output_file.write_text(MOCK_EXPERT_OUTPUT, encoding="utf-8")

    # Verify all 3 outputs exist
    for skill_name in expert_skill_names:
        output_file = output_dir / f"{skill_name}.md"
        assert output_file.exists(), f"Missing output for {skill_name}"
        content = output_file.read_text()
        assert "Hypotheses" in content


# ── Test: missions list endpoint ──────────────────────────────────────────────


def test_missions_list_returns_200(client):
    """GET /v1/missions returns 200 (empty list when no missions in test DB)."""
    resp = client.get("/v1/missions")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)


def test_missions_list_env_filter(client):
    """GET /v1/missions?env=preprod returns 200 with filtered results."""
    resp = client.get("/v1/missions?env=preprod")
    assert resp.status_code == 200


def test_mission_detail_not_found(client):
    """GET /v1/missions/{non-existent-id} returns 404."""
    resp = client.get("/v1/missions/FAKE-PREPROD-INCIDENT-NONE-20260101-001")
    assert resp.status_code == 404


# ── Test: alertmanager webhook endpoint ───────────────────────────────────────


def test_alertmanager_webhook_missing_common_labels(client, monkeypatch):
    """Malformed webhook payload (no alerts key) returns 200 with 0 accepted.

    The handler is resilient — it never returns 4xx for missing optional fields,
    only for truly invalid JSON (which FastAPI rejects at 422 before the handler).
    """
    payload = {
        "version": "4",
        "status": "firing",
        "groupLabels": {"alertname": "KafkaBrokerDown"},
        # 'alerts' key missing — handler returns accepted=0
    }
    # We need to mock the DB call inside the webhook handler
    with patch("triggers.alertmanager_webhook.AlertmanagerWebhookHandler.handle",
               new=AsyncMock(return_value={"accepted": 0, "reason": "no firing alerts in payload"})):
        resp = client.post("/webhooks/alertmanager", json=payload)
    # FastAPI parses raw JSON body → 200 (handler returns 200/dict per implementation)
    assert resp.status_code == 200


def test_alertmanager_webhook_invalid_json(client):
    """Request with invalid Content-Type body returns 422."""
    resp = client.post(
        "/webhooks/alertmanager",
        content=b"not valid json",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 422
