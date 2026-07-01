"""Unit tests for agents/intake/agent.py — env/cluster extraction and classification.

Covers:
  - customfield_10200 → env=preprod
  - Jira label env:preprod → env=preprod
  - Summary regex kafka-preprod → env=preprod
  - Ambiguous env → status=env_ambiguous
  - subject slugification
  - MISSION_ID format regex
"""

from __future__ import annotations

import json
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.intake.agent import IntakeAgent, _extract_json
from core.mission import MissionContext, MissionType

# ── Regex under test (from core/mission.py) ───────────────────────────────────

_MISSION_ID_RE = re.compile(r"^[A-Z0-9]+-[A-Z]+-[A-Z]+-[A-Z0-9-]+-\d{8}-\d{3}$")


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_agent() -> IntakeAgent:
    return IntakeAgent(model="gemini-test")


def _jira_payload(
    *,
    summary: str = "PVC Saturation on kafka-preprod",
    labels: list[str] | None = None,
    customfield_10200: str | None = None,
    status: str = "Open",
    issuetype: str = "Incident",
) -> dict:
    fields: dict = {
        "summary": summary,
        "status": {"name": status},
        "issuetype": {"name": issuetype},
        "labels": labels or [],
        "assignee": {"name": "ops-user"},
        "project": {"key": "PHX"},
    }
    if customfield_10200 is not None:
        fields["customfield_10200"] = customfield_10200
    return {"key": "PHX-99999", "fields": fields}


def _llm_json_response(**kwargs) -> str:
    """Build a fenced JSON block the way the LLM would return it."""
    data = {
        "status": "ok",
        "env": "preprod",
        "cluster": "kafka-preprod",
        "type": "INCIDENT",
        "subject": "pvc-saturation",
        "confidence": "HIGH",
        "jira_ticket_id": "PHX-99999",
        **kwargs,
    }
    return f"```json\n{json.dumps(data)}\n```"


# ── _extract_json ─────────────────────────────────────────────────────────────


def test_extract_json_from_fenced_block():
    text = '```json\n{"env": "preprod", "subject": "pvc-saturation"}\n```'
    result = _extract_json(text)
    assert result == {"env": "preprod", "subject": "pvc-saturation"}


def test_extract_json_from_bare_object():
    text = 'Some preamble\n{"env": "prod", "status": "ok"} and trailing text'
    result = _extract_json(text)
    assert result is not None
    assert result["env"] == "prod"


def test_extract_json_returns_none_on_invalid():
    assert _extract_json("no JSON here at all") is None
    assert _extract_json("```json\n{broken json\n```") is None


# ── classify: customfield_10200 → env ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_classify_env_from_customfield_10200():
    """customfield_10200 = 'preprod' → LLM returns env=preprod."""
    agent = _make_agent()
    payload = _jira_payload(customfield_10200="preprod")

    llm_output = _llm_json_response(env="preprod", subject="pvc-saturation")
    with patch.object(agent, "run", new=AsyncMock(return_value=llm_output)):
        result = await agent.classify(
            trigger_payload=payload,
            tenant="enterprise",
            source="jira",
        )

    assert result is not None
    assert not result["rejected"]
    assert result["env"] == "PREPROD"


# ── classify: label env:preprod → env ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_classify_env_from_label():
    """Jira label 'env:preprod' → LLM guided classification returns env=preprod."""
    agent = _make_agent()
    payload = _jira_payload(labels=["env:preprod", "kafka"])

    llm_output = _llm_json_response(env="preprod", subject="pvc-saturation")
    with patch.object(agent, "run", new=AsyncMock(return_value=llm_output)):
        result = await agent.classify(
            trigger_payload=payload,
            tenant="enterprise",
            source="jira",
        )

    assert result is not None
    assert not result["rejected"]
    assert result["env"] == "PREPROD"


# ── classify: summary regex kafka-preprod → env ───────────────────────────────


@pytest.mark.asyncio
async def test_classify_env_from_summary_regex():
    """Summary containing 'kafka-preprod' → LLM classifies env=preprod."""
    agent = _make_agent()
    payload = _jira_payload(summary="PVC Saturation on kafka-preprod broker-1 is full")

    llm_output = _llm_json_response(env="preprod", subject="pvc-saturation")
    with patch.object(agent, "run", new=AsyncMock(return_value=llm_output)):
        result = await agent.classify(
            trigger_payload=payload,
            tenant="enterprise",
            source="jira",
        )

    assert result is not None
    assert not result["rejected"]
    assert result["env"] == "PREPROD"


# ── classify: no env determinable → env_ambiguous ────────────────────────────


@pytest.mark.asyncio
async def test_classify_env_ambiguous():
    """When LLM cannot determine env, it returns status=env_ambiguous."""
    agent = _make_agent()
    payload = _jira_payload(
        summary="Some generic issue with no environment hint",
        labels=[],
    )

    ambiguous_response = '{"status": "env_ambiguous", "reason": "No environment indicator found"}'
    with patch.object(agent, "run", new=AsyncMock(return_value=ambiguous_response)):
        result = await agent.classify(
            trigger_payload=payload,
            tenant="enterprise",
            source="jira",
        )

    assert result is not None
    assert result["rejected"] is True
    assert result["status"] == "env_ambiguous"
    assert result["reason"]


# ── classify: subject slug from summary ───────────────────────────────────────


@pytest.mark.asyncio
async def test_classify_subject_kebab_case():
    """LLM produces subject as kebab-case slug: 'PVC Saturation' → 'pvc-saturation'."""
    agent = _make_agent()
    payload = _jira_payload(summary="PVC Saturation Critical Alert")

    llm_output = _llm_json_response(env="preprod", subject="pvc-saturation")
    with patch.object(agent, "run", new=AsyncMock(return_value=llm_output)):
        result = await agent.classify(
            trigger_payload=payload,
            tenant="enterprise",
            source="jira",
        )

    assert result is not None
    assert not result["rejected"]
    assert result["subject"] == "pvc-saturation"


@pytest.mark.asyncio
async def test_classify_subject_broker_down():
    """LLM produces subject for broker-down scenario."""
    agent = _make_agent()
    payload = _jira_payload(summary="Kafka Broker Down in Production Cluster")

    llm_output = _llm_json_response(env="prod", subject="broker-down")
    with patch.object(agent, "run", new=AsyncMock(return_value=llm_output)):
        result = await agent.classify(
            trigger_payload=payload,
            tenant="enterprise",
            source="jira",
        )

    assert result is not None
    assert result["subject"] == "broker-down"


# ── classify: ignored status ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_classify_ignored_status():
    """Ticket that does not match Kafka criteria → status=ignored."""
    agent = _make_agent()
    payload = _jira_payload(issuetype="Task", summary="Update documentation")

    ignored_response = '{"status": "ignored", "reason": "Not a Kafka incident"}'
    with patch.object(agent, "run", new=AsyncMock(return_value=ignored_response)):
        result = await agent.classify(
            trigger_payload=payload,
            tenant="enterprise",
            source="jira",
        )

    assert result is not None
    assert result["rejected"] is True
    assert result["status"] == "ignored"


# ── classify: unparseable LLM output → None ───────────────────────────────────


@pytest.mark.asyncio
async def test_classify_returns_none_on_unparseable_output():
    """If LLM returns garbage, classify returns None."""
    agent = _make_agent()
    payload = _jira_payload()

    with patch.object(agent, "run", new=AsyncMock(return_value="Sorry, I cannot help.")):
        result = await agent.classify(
            trigger_payload=payload,
            tenant="enterprise",
            source="jira",
        )

    assert result is None


# ── classify: full result shape ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_classify_full_result_shape():
    """Successful classification returns all expected keys."""
    agent = _make_agent()
    payload = _jira_payload(
        summary="PVC Saturation kafka-preprod",
        customfield_10200="preprod",
    )

    llm_output = _llm_json_response(
        env="preprod",
        cluster="kafka-preprod",
        subject="pvc-saturation",
        type="INCIDENT",
        confidence="HIGH",
        jira_ticket_id="PHX-99999",
    )
    with patch.object(agent, "run", new=AsyncMock(return_value=llm_output)):
        result = await agent.classify(
            trigger_payload=payload,
            tenant="enterprise",
            source="jira",
        )

    assert result is not None
    assert not result["rejected"]
    assert result["tenant"] == "enterprise"
    assert result["env"] == "PREPROD"
    assert result["cluster"] == "kafka-preprod"
    assert result["subject"] == "pvc-saturation"
    assert result["type"] == MissionType.INCIDENT
    assert result["confidence"] == "HIGH"
    assert result["jira_ticket_id"] == "PHX-99999"


# ── MISSION_ID format regex ────────────────────────────────────────────────────


@pytest.mark.parametrize("mission_id", [
    "ENTERPRISE-PREPROD-INCIDENT-PVC-SATURATION-20260510-001",
    "TESTCO-PROD-INCIDENT-BROKER-DOWN-20260101-042",
    "ENTERPRISE-PREPROD-REVIEW-CERT-EXPIRY-20260315-007",
    "A1-B-C-D-20260101-001",
])
def test_mission_id_format_valid(mission_id):
    assert _MISSION_ID_RE.match(mission_id), f"Expected to match: {mission_id!r}"


@pytest.mark.parametrize("mission_id", [
    "enterprise-preprod-INCIDENT-pvc-saturation-20260510-001",  # lowercase
    "ENTERPRISE-PREPROD-20260510-001",                          # missing type/subject
    "BAD-ID",
    "ENTERPRISE-PREPROD-INCIDENT-PVC-SATURATION-2026051-001",   # date wrong
    "ENTERPRISE-PREPROD-INCIDENT-PVC-SATURATION-20260510-01",   # seq too short
])
def test_mission_id_format_invalid(mission_id):
    assert not _MISSION_ID_RE.match(mission_id), f"Expected NOT to match: {mission_id!r}"


# ── classify: MissionType fallback ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_classify_unknown_type_falls_back_to_incident():
    """Unknown mission type in LLM output → defaults to MissionType.INCIDENT."""
    agent = _make_agent()
    payload = _jira_payload()

    llm_output = _llm_json_response(type="BOGUS_TYPE", subject="lag-urp", env="preprod")
    with patch.object(agent, "run", new=AsyncMock(return_value=llm_output)):
        result = await agent.classify(
            trigger_payload=payload,
            tenant="enterprise",
            source="jira",
        )

    assert result is not None
    assert result["type"] == MissionType.INCIDENT
