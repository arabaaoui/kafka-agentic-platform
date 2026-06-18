"""Tests for core/kb_writer.py."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from core.kb_writer import KBCardWriter, _validate_slug


# ── _validate_slug ────────────────────────────────────────────────────────────

def test_valid_slug():
    assert _validate_slug("pvc-saturation") == "pvc-saturation"


def test_slug_strips_yaml_comment():
    # Regression guard — spec 003 SC-005: YAML inline comment must be stripped
    assert _validate_slug("pvc-saturation # ex: urp-pvc") == "pvc-saturation"


def test_slug_too_long():
    with pytest.raises(ValueError, match="too long"):
        _validate_slug("a" * 65)


def test_slug_invalid_uppercase():
    with pytest.raises(ValueError, match="kebab-case"):
        _validate_slug("PVC-Saturation")


def test_slug_with_spaces():
    with pytest.raises(ValueError, match="kebab-case"):
        _validate_slug("pvc saturation")


# ── KBCardWriter ──────────────────────────────────────────────────────────────

@pytest.fixture
def kb_dir(tmp_path: Path) -> Path:
    (tmp_path / "incidents").mkdir()
    return tmp_path


@pytest.fixture
def writer(kb_dir: Path) -> KBCardWriter:
    return KBCardWriter(kb_dir=kb_dir)


def test_card_exists_false(writer):
    assert writer.card_exists("pvc-saturation") is False


def test_create_card(writer, kb_dir):
    path = writer.create_card(
        slug="pvc-saturation",
        title="PVC Saturation on Kafka Broker",
        theme="Storage & PVC",
        tags=["pvc", "kafka", "strimzi"],
        severity="critical",
        symptoms=["PVC used > 90%", "Broker log dir full"],
        root_cause="Log retention not configured, disk filled up.",
        body="## Description\nTest body.",
        mission_id="CARREFOUR-PREPROD-INCIDENT-PVC-SATURATION-20260511-001",
        env="PREPROD",
    )
    assert path.exists()
    assert writer.card_exists("pvc-saturation")
    content = path.read_text()
    assert "slug: pvc-saturation" in content
    assert "severity: critical" in content
    assert "CARREFOUR-PREPROD" in content


def test_create_card_duplicate_raises(writer):
    writer.create_card(
        slug="my-card",
        title="My Card",
        theme="Test",
        tags=[],
        severity="info",
        symptoms=["s1"],
        root_cause="test",
        body="body",
        mission_id="T-P-I-MY-CARD-20260511-001",
        env="PREPROD",
    )
    with pytest.raises(ValueError, match="already exists"):
        writer.create_card(
            slug="my-card",
            title="Dup",
            theme="Test",
            tags=[],
            severity="info",
            symptoms=["s1"],
            root_cause="test",
            body="body",
            mission_id="T-P-I-MY-CARD-20260511-002",
            env="PREPROD",
        )


def test_update_card_increments_occurrences(writer):
    writer.create_card(
        slug="update-me",
        title="Update Me",
        theme="Test",
        tags=["t"],
        severity="info",
        symptoms=["s1", "s2"],
        root_cause="root",
        body="body",
        mission_id="T-P-I-UPDATE-ME-20260511-001",
        env="PREPROD",
    )
    writer.update_card("update-me", "T-P-I-UPDATE-ME-20260511-002")
    content = (writer._incidents_dir / "update-me.md").read_text()
    assert "occurrences: 2" in content
    assert "T-P-I-UPDATE-ME-20260511-002" in content


def test_update_card_appends_mission_only_once(writer):
    writer.create_card(
        slug="once-card",
        title="Once Card",
        theme="Test",
        tags=[],
        severity="info",
        symptoms=["s1"],
        root_cause="r",
        body="b",
        mission_id="T-P-I-ONCE-CARD-20260511-001",
        env="PREPROD",
    )
    writer.update_card("once-card", "T-P-I-ONCE-CARD-20260511-001")  # same id
    content = (writer._incidents_dir / "once-card.md").read_text()
    assert content.count("T-P-I-ONCE-CARD-20260511-001") == 1


def test_update_card_not_found(writer):
    with pytest.raises(FileNotFoundError):
        writer.update_card("ghost-card", "T-P-I-GHOST-20260511-001")


def test_regenerate_index(writer):
    writer.create_card(
        slug="card-a",
        title="Card A",
        theme="Storage & PVC",
        tags=["pvc"],
        severity="critical",
        symptoms=["s1"],
        root_cause="r",
        body="b",
        mission_id="T-P-I-CARD-A-20260511-001",
        env="PREPROD",
    )
    writer.create_card(
        slug="card-b",
        title="Card B",
        theme="Consumer Performance",
        tags=["lag"],
        severity="warning",
        symptoms=["s1"],
        root_cause="r",
        body="b",
        mission_id="T-P-I-CARD-B-20260511-001",
        env="PREPROD",
    )
    count = writer.regenerate_index()
    assert count == 2
    index_content = (writer._kb_dir / "INDEX.md").read_text()
    assert "card-a" in index_content
    assert "card-b" in index_content
    assert "_Cartes : 2_" in index_content
    assert "**pvc**" in index_content
