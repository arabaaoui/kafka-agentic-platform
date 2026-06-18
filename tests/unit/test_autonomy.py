"""Unit tests for core/autonomy.py — _L2_BLOCKED_TOOLS coverage."""

import pytest

from core.autonomy import AutonomyViolation, _L2_BLOCKED_TOOLS


# ── Blocked set completeness ──────────────────────────────────────────────────


def test_blocked_tools_set_is_frozen():
    """_L2_BLOCKED_TOOLS must be a frozenset (immutable at runtime)."""
    assert isinstance(_L2_BLOCKED_TOOLS, frozenset)


def test_blocked_tools_covers_kafka_mutations():
    must_have = {
        "topic_create", "topic_delete", "kafka_reassign",
        "kubectl_apply", "kubectl_delete",
        "scram_user_create", "acl_create",
        "jira_add_comment",
    }
    assert must_have.issubset(_L2_BLOCKED_TOOLS)
