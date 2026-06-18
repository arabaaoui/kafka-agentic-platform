"""Tests for KBIndex TTL reload behaviour (spec 004 FR-006 / SC-004)."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from core.mem0_bridge import KBIndexLegacy as KBIndex


_CARD_TEMPLATE = """---
slug: {slug}
title: "Test Card"
theme: "Storage & PVC"
tags: [pvc, test]
severity: critical
environments_seen: [PREPROD]
first_seen: 2026-05-11
last_seen: 2026-05-11
occurrences: 1
symptoms:
  - "Symptom 1"
root_cause: "Test root cause for {slug}."
agents_involved: []
related_missions: [T-P-I-{slug_upper}-20260511-001]
---

## Description
Test card body.
"""


@pytest.fixture
def kb_dir(tmp_path: Path) -> Path:
    (tmp_path / "incidents").mkdir()
    return tmp_path


def _write_card(kb_dir: Path, slug: str) -> None:
    content = _CARD_TEMPLATE.format(slug=slug, slug_upper=slug.upper().replace("-", "-"))
    (kb_dir / "incidents" / f"{slug}.md").write_text(content, encoding="utf-8")


def test_initial_load(kb_dir):
    _write_card(kb_dir, "pvc-saturation")
    idx = KBIndex(kb_dir=kb_dir)
    results = idx.search("pvc saturation")
    assert len(results) == 1
    assert results[0].slug == "pvc-saturation"


def test_no_reload_within_ttl(kb_dir):
    _write_card(kb_dir, "pvc-saturation")
    idx = KBIndex(kb_dir=kb_dir)
    idx.search("pvc")  # initial load

    # Write a new card AFTER initial load
    _write_card(kb_dir, "lag-consumer")

    # Search again — still within TTL, should NOT see new card
    with patch("time.monotonic", return_value=idx._loaded_at + 30.0):
        results = idx.search("lag consumer")
    assert not any(r.slug == "lag-consumer" for r in results)


def test_reload_after_ttl(kb_dir):
    _write_card(kb_dir, "pvc-saturation")
    idx = KBIndex(kb_dir=kb_dir)
    idx.search("pvc")  # initial load
    loaded_at = idx._loaded_at

    # Write a new card
    _write_card(kb_dir, "lag-consumer")

    # Simulate TTL expiry
    with patch.object(idx, "_loaded_at", loaded_at - 61.0):
        results = idx.search("lag consumer")
    assert any(r.slug == "lag-consumer" for r in results)


def test_invalidate_forces_reload(kb_dir):
    _write_card(kb_dir, "pvc-saturation")
    idx = KBIndex(kb_dir=kb_dir)
    idx.search("pvc")  # initial load

    # Write new card
    _write_card(kb_dir, "new-card")

    # Invalidate — next search must reload
    idx.invalidate()
    assert idx._loaded is False

    results = idx.search("new card")
    assert any(r.slug == "new-card" for r in results)


def test_search_returns_empty_for_no_match(kb_dir):
    _write_card(kb_dir, "pvc-saturation")
    idx = KBIndex(kb_dir=kb_dir)
    results = idx.search("totally-unrelated-xyz")
    assert results == []


def test_search_skips_malformed_stub(kb_dir, tmp_path):
    # The broken test-lag card (slug has spaces) should be silently skipped
    bad_content = """---
slug: test-lag                          # ex: urp-pvc-saturation (kebab-case, unique)
title: "bad template"
---
body
"""
    (kb_dir / "incidents" / "test-lag.md").write_text(bad_content, encoding="utf-8")
    idx = KBIndex(kb_dir=kb_dir)
    results = idx.search("lag")
    assert not any(r.slug.startswith("test-lag ") for r in results)
