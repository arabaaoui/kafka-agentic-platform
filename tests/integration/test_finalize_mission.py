"""Integration tests for POST /v1/missions/{id}/finalize (spec 004)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def closed_mission_id():
    return "ENTERPRISE-PREPROD-INCIDENT-PVC-SATURATION-20260511-001"


@pytest.fixture
def audit_md(closed_mission_id, tmp_path):
    """Write a fixture audit.md in the expected location."""
    audit_dir = Path("audits") / closed_mission_id
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_path = audit_dir / "audit.md"
    audit_path.write_text(
        f"## Consolidated Audit — {closed_mission_id}\n\n"
        "### Hypotheses (ranked)\n"
        "| Rank | Hypothesis | Confidence | Evidence |\n"
        "|------|-----------|-----------|----------|\n"
        "| 1 | PVC kafka-data-0 saturation | 90% | kubelet_volume_stats=93% |\n"
        "| 2 | Log compaction starvation | 45% | logcleaner metrics |\n",
        encoding="utf-8",
    )
    yield audit_path
    # Cleanup
    import shutil
    if audit_dir.exists():
        shutil.rmtree(audit_dir)


class _FakeResult:
    mission_id = "ENTERPRISE-PREPROD-INCIDENT-PVC-SATURATION-20260511-001"
    brief_path = "audits/ENTERPRISE-PREPROD-INCIDENT-PVC-SATURATION-20260511-001/BRIEF.md"
    kb_card_slug = "pvc-saturation-v2"
    kb_card_action = "created"
    kb_index_card_count = 18
    finalized_at = __import__("datetime").datetime(2026, 5, 11, 10, 0, 0, tzinfo=__import__("datetime").timezone.utc)


@pytest.mark.asyncio
async def test_finalize_returns_result_on_closed_mission(closed_mission_id, audit_md):
    """Happy path: CLOSED mission → returns FinalizeResult."""
    mock_agent = AsyncMock()
    mock_agent.finalize = AsyncMock(return_value=_FakeResult())

    with (
        patch("agents.post_mortem_analyst.agent.PostMortemAgent", return_value=mock_agent),
        patch("api.routes.missions._get_or_404") as mock_get,
        patch("core.tenant.TenantRegistry"),
    ):
        mock_mission = MagicMock()
        mock_mission.status = "CLOSED"
        mock_mission.mission_id = closed_mission_id
        mock_mission.tenant = "enterprise"
        mock_mission.env = "PREPROD"
        mock_mission.cluster = "kafka-preprod"
        mock_mission.type = "INCIDENT"
        mock_mission.subject = "pvc-saturation"
        mock_mission.autonomy_level = "L2"
        mock_mission.metadata_ = {}
        mock_get.return_value = mock_mission

        from api.routes.missions import finalize_mission
        from unittest.mock import MagicMock as MMock

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MMock(scalar_one_or_none=MMock(return_value=None)))

        result = await finalize_mission(closed_mission_id, mock_db)

    assert result["mission_id"] == closed_mission_id
    assert result["kb_card_slug"] == "pvc-saturation-v2"
    assert result["kb_card_action"] == "created"
    assert result["kb_index_card_count"] == 18


@pytest.mark.asyncio
async def test_finalize_409_on_open_mission():
    """OPEN mission → 409 mission_not_completed."""
    from fastapi import HTTPException

    with patch("api.routes.missions._get_or_404") as mock_get:
        mock_mission = MagicMock()
        mock_mission.status = "OPEN"
        mock_get.return_value = mock_mission

        from api.routes.missions import finalize_mission

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

        with pytest.raises(HTTPException) as exc_info:
            await finalize_mission("SOME-MISSION-001", mock_db)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "mission_not_completed"


@pytest.mark.asyncio
async def test_finalize_409_on_already_finalized():
    """Already-finalized mission → 409 already_finalized."""
    from fastapi import HTTPException
    import datetime

    with patch("api.routes.missions._get_or_404") as mock_get:
        mock_mission = MagicMock()
        mock_mission.status = "CLOSED"
        mock_get.return_value = mock_mission

        mock_audit = MagicMock()
        mock_audit.finalized_at = datetime.datetime(2026, 5, 11, tzinfo=datetime.timezone.utc)
        mock_audit.kb_card_slug = "pvc-saturation-test"

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=mock_audit))
        )

        from api.routes.missions import finalize_mission

        kb_writer_mock = MagicMock()
        kb_writer_mock.card_exists.return_value = True

        with (
            patch("api.routes.missions.KBCardWriter", return_value=kb_writer_mock),
            pytest.raises(HTTPException) as exc_info,
        ):
            await finalize_mission("SOME-MISSION-001", mock_db)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"] == "already_finalized"
