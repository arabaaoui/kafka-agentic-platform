"""Unit tests for core/mission.py (spec 003 T028-T037)."""

import pytest
from datetime import date
from pydantic import ValidationError

from core.mission import (
    MissionContext,
    MissionStatus,
    MissionType,
    build_mission_id,
)


# ── build_mission_id ──────────────────────────────────────────────────────────


def test_build_mission_id_canonical():
    mid = build_mission_id(
        "carrefour", "preprod", MissionType.INCIDENT, "pvc-saturation",
        date(2026, 5, 10), 1,
    )
    assert mid == "CARREFOUR-PREPROD-INCIDENT-PVC-SATURATION-20260510-001"


def test_build_mission_id_seq_padding():
    mid = build_mission_id(
        "tenant", "prod", MissionType.REVIEW, "cert-expiry",
        date(2026, 1, 1), 42,
    )
    assert mid.endswith("-20260101-042")


def test_build_mission_id_uppercase_inputs():
    mid = build_mission_id(
        "carrefour", "dev", MissionType.MAINTENANCE, "lag-urp",
        date(2026, 5, 10), 7,
    )
    assert mid.startswith("CARREFOUR-DEV-MAINTENANCE-LAG-URP-")


# ── MissionContext — valid construction ───────────────────────────────────────


def test_mission_context_valid():
    ctx = MissionContext(
        mission_id="CARREFOUR-PREPROD-INCIDENT-PVC-SATURATION-20260510-001",
        tenant="carrefour",
        env="preprod",
        cluster="kafkahub-preprod",
        type=MissionType.INCIDENT,
        subject="pvc-saturation",
    )
    assert ctx.mission_id == "CARREFOUR-PREPROD-INCIDENT-PVC-SATURATION-20260510-001"
    assert ctx.tenant == "CARREFOUR"  # uppercased by validator
    assert ctx.env == "PREPROD"
    assert ctx.status == MissionStatus.OPEN
    assert ctx.autonomy_level == "L2"


def test_mission_context_frozen():
    ctx = MissionContext(
        mission_id="CARREFOUR-PREPROD-INCIDENT-PVC-SATURATION-20260510-001",
        tenant="carrefour",
        env="preprod",
        cluster="kafkahub-preprod",
        type=MissionType.INCIDENT,
        subject="pvc-saturation",
    )
    with pytest.raises(Exception):  # frozen model raises on assignment
        ctx.status = MissionStatus.CLOSED  # type: ignore[misc]


# ── MissionContext — MISSION_ID validation ────────────────────────────────────


def test_mission_id_bad_format_rejected():
    with pytest.raises(ValidationError, match="MISSION_ID"):
        MissionContext(
            mission_id="bad-id",
            tenant="carrefour",
            env="preprod",
            cluster="kafkahub-preprod",
            type=MissionType.INCIDENT,
            subject="pvc-saturation",
        )


def test_mission_id_lowercase_rejected():
    with pytest.raises(ValidationError):
        MissionContext(
            mission_id="carrefour-preprod-INCIDENT-pvc-saturation-20260510-001",
            tenant="carrefour",
            env="preprod",
            cluster="c",
            type=MissionType.INCIDENT,
            subject="pvc-saturation",
        )


# ── MissionContext — subject validation (spec 003 FR-002, SC-005) ─────────────


def test_subject_too_long_rejected():
    long_subject = "a" * 65
    with pytest.raises(ValidationError, match="too long"):
        MissionContext(
            mission_id="CARREFOUR-PREPROD-INCIDENT-A-20260510-001",
            tenant="carrefour",
            env="preprod",
            cluster="c",
            type=MissionType.INCIDENT,
            subject=long_subject,
        )


def test_subject_max_len_30_accepted():
    subject_30 = "a" * 30
    ctx = MissionContext(
        mission_id=f"CARREFOUR-PREPROD-INCIDENT-{'A' * 30}-20260510-001",
        tenant="carrefour",
        env="preprod",
        cluster="c",
        type=MissionType.INCIDENT,
        subject=subject_30,
    )
    assert ctx.subject == subject_30


def test_subject_strips_yaml_comment():
    """SC-005 regression: YAML comment must be stripped before validation."""
    ctx = MissionContext(
        mission_id="CARREFOUR-PREPROD-INCIDENT-PVC-SATURATION-20260510-001",
        tenant="carrefour",
        env="preprod",
        cluster="c",
        type=MissionType.INCIDENT,
        subject="pvc-saturation  # ex: my-topic-lag",
    )
    assert ctx.subject == "pvc-saturation"


def test_subject_uppercase_rejected():
    with pytest.raises(ValidationError, match="kebab-case"):
        MissionContext(
            mission_id="CARREFOUR-PREPROD-INCIDENT-PVC-SATURATION-20260510-001",
            tenant="carrefour",
            env="preprod",
            cluster="c",
            type=MissionType.INCIDENT,
            subject="PVC-Saturation",
        )


def test_subject_underscore_rejected():
    with pytest.raises(ValidationError, match="kebab-case"):
        MissionContext(
            mission_id="CARREFOUR-PREPROD-INCIDENT-PVC-SATURATION-20260510-001",
            tenant="carrefour",
            env="preprod",
            cluster="c",
            type=MissionType.INCIDENT,
            subject="pvc_saturation",
        )


# ── MissionContext — SLUG_PATTERN reuse (no regex duplication, SC-005) ────────


def test_mission_uses_toolkit_slug_pattern():
    """core/mission.py must import SLUG_PATTERN from kafka-agent-toolkit, not redefine it."""
    import inspect
    import core.mission as m_mod
    source = inspect.getsource(m_mod)
    assert "from kafka_agent_toolkit.kb.schemas import SLUG_PATTERN" in source
    # The local _MISSION_ID_RE must exist but no local _SLUG_PATTERN should be defined.
    assert "SLUG_PATTERN = re.compile" not in source
