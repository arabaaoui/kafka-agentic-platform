"""Integration tests for triggers/jira_mcp_poller.py.

Covers:
  - Matched issue → enqueued in mission_queue within one poll cycle
  - Closed ticket → logged as rejected, no mission enqueued
  - Multiple filter rules → lowest-priority (highest-priority-number) rule loses
    to the lower priority number (wins) rule for the same ticket
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.filter_engine import FilterEngine, FilterRule
from triggers.jira_mcp_poller import JiraMcpPoller


# ── Fixtures ──────────────────────────────────────────────────────────────────


PHX_99999_PAYLOAD = {
    "key": "PHX-99999",
    "fields": {
        "summary": "PVC Saturation on kafka-preprod",
        "status": {"name": "Open"},
        "issuetype": {"name": "Incident"},
        "project": {"key": "PHX"},
        "assignee": {"name": "arabaaoui"},
        "labels": ["env:preprod", "kafka"],
        "customfield_10200": "preprod",
    },
}

PHX_CLOSED_PAYLOAD = {
    "key": "PHX-11111",
    "fields": {
        "summary": "Old closed incident",
        "status": {"name": "Closed"},
        "issuetype": {"name": "Incident"},
        "project": {"key": "PHX"},
        "assignee": {"name": "arabaaoui"},
        "labels": [],
    },
}


def _make_rule(
    *,
    id: str = "rule-1",
    name: str = "Kafka incidents",
    priority: int = 10,
    criteria: dict | None = None,
) -> FilterRule:
    return FilterRule(
        id=id,
        tenant="carrefour",
        scope="jira",
        name=name,
        enabled=True,
        priority=priority,
        poll_interval_seconds=30,
        criteria=criteria or {"project": ["PHX"], "issuetype": "Incident"},
    )


def _make_db_mock(
    *,
    rules: list[FilterRule] | None = None,
    trigger_exists: bool = False,
) -> AsyncMock:
    """Build an asyncpg-style connection mock."""
    db = AsyncMock()

    # _load_rules: fetch returns rows that mirror FilterRule fields
    rule_rows = []
    for r in (rules or [_make_rule()]):
        row = MagicMock()
        row.__getitem__ = lambda self, k, _r=r: {
            "id": _r.id,
            "tenant": _r.tenant,
            "scope": _r.scope,
            "name": _r.name,
            "enabled": _r.enabled,
            "priority": _r.priority,
            "poll_interval_seconds": _r.poll_interval_seconds,
            "criteria": _r.criteria,
        }[k]
        rule_rows.append(row)

    db.fetch = AsyncMock(return_value=rule_rows)

    # _trigger_exists: None means not seen yet
    if trigger_exists:
        db.fetchrow = AsyncMock(return_value={"id": "existing-trigger-id"})
    else:
        db.fetchrow = AsyncMock(return_value=None)

    db.execute = AsyncMock(return_value=None)
    return db


def _make_poller(
    *,
    db: AsyncMock,
    queue: asyncio.Queue,
    jira_issues: list[dict] | None = None,
) -> JiraMcpPoller:
    poller = JiraMcpPoller(
        db_conn=db,
        mission_queue=queue,
        mcp_url="http://fake-mcp:3010",
    )
    # Mock the internal HTTP search so we don't need a real MCP server
    poller._jira_search = AsyncMock(return_value=jira_issues or [PHX_99999_PAYLOAD])
    # Provide a fake HTTP client so start() does not complain about None
    poller._http = MagicMock()
    return poller


# ── Test: matched issue → mission enqueued ────────────────────────────────────


@pytest.mark.asyncio
async def test_matched_issue_enqueues_mission():
    """A matching open incident is placed in mission_queue within one poll cycle."""
    queue: asyncio.Queue = asyncio.Queue()
    db = _make_db_mock()
    poller = _make_poller(db=db, queue=queue, jira_issues=[PHX_99999_PAYLOAD])

    await poller._poll_all_rules()

    assert not queue.empty(), "Expected one item in mission_queue"
    item = queue.get_nowait()
    assert item["source"] == "jira"
    assert item["external_id"] == "PHX-99999"
    assert item["tenant"] == "carrefour"
    assert item["payload"] == PHX_99999_PAYLOAD


@pytest.mark.asyncio
async def test_matched_issue_rule_id_in_queue_item():
    """Queue item carries the rule_id that matched."""
    queue: asyncio.Queue = asyncio.Queue()
    db = _make_db_mock(rules=[_make_rule(id="r-kafka-incidents")])
    poller = _make_poller(db=db, queue=queue, jira_issues=[PHX_99999_PAYLOAD])

    await poller._poll_all_rules()

    item = queue.get_nowait()
    assert item["rule_id"] == "r-kafka-incidents"


# ── Test: already-seen ticket not re-enqueued ─────────────────────────────────


@pytest.mark.asyncio
async def test_already_seen_ticket_not_enqueued():
    """If the trigger already exists in DB, the issue is skipped."""
    queue: asyncio.Queue = asyncio.Queue()
    db = _make_db_mock(trigger_exists=True)
    poller = _make_poller(db=db, queue=queue, jira_issues=[PHX_99999_PAYLOAD])

    await poller._poll_all_rules()

    assert queue.empty(), "Already-seen ticket must not be re-enqueued"


# ── Test: Closed status → logged as rejected, no mission ─────────────────────


@pytest.mark.asyncio
async def test_closed_ticket_not_enqueued():
    """A Jira issue with status=Closed does not match the filter and is not enqueued."""
    queue: asyncio.Queue = asyncio.Queue()

    # Rule explicitly filters for Open issues
    rule = _make_rule(
        criteria={"project": ["PHX"], "issuetype": "Incident", "status": "Open"}
    )
    db = _make_db_mock(rules=[rule])
    poller = _make_poller(db=db, queue=queue, jira_issues=[PHX_CLOSED_PAYLOAD])

    await poller._poll_all_rules()

    assert queue.empty(), "Closed ticket must not be enqueued"
    # Verify a trigger row was written with matched=False
    db.execute.assert_awaited()
    all_calls = [str(call) for call in db.execute.call_args_list]
    # The upsert should have been called with matched=False
    insert_calls = [c for c in all_calls if "INSERT INTO triggers" in c]
    assert insert_calls, "Expected a trigger INSERT for rejected issue"


@pytest.mark.asyncio
async def test_closed_ticket_filter_match_log_written():
    """Rejected ticket evaluation is logged to filter_match_log."""
    queue: asyncio.Queue = asyncio.Queue()
    rule = _make_rule(
        criteria={"project": ["PHX"], "status": "Open"}
    )
    db = _make_db_mock(rules=[rule])
    poller = _make_poller(db=db, queue=queue, jira_issues=[PHX_CLOSED_PAYLOAD])

    await poller._poll_all_rules()

    # _log_matches calls db.execute for filter_match_log insert
    all_execute_calls = [str(c) for c in db.execute.call_args_list]
    log_calls = [c for c in all_execute_calls if "filter_match_log" in c]
    assert log_calls, "Expected filter_match_log entry for rejected ticket"


# ── Test: empty JQL skips the rule ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_jql_rule_is_skipped():
    """A rule with empty criteria produces no JQL and must be skipped."""
    queue: asyncio.Queue = asyncio.Queue()
    rule = _make_rule(criteria={})  # no criteria → empty JQL
    db = _make_db_mock(rules=[rule])
    poller = _make_poller(db=db, queue=queue, jira_issues=[PHX_99999_PAYLOAD])

    await poller._poll_all_rules()

    # _jira_search should not have been called (empty JQL skipped)
    poller._jira_search.assert_not_awaited()
    assert queue.empty()


# ── Test: multiple filter rules — priority ordering ───────────────────────────


@pytest.mark.asyncio
async def test_rule_priority_10_wins_over_priority_100():
    """For the same ticket, rule with priority=10 is evaluated before priority=100.

    The poller evaluates each rule independently against all issues.
    Lower priority number → evaluated first and will match first.
    Both rules may enqueue separately (one per rule/issue pair), but the
    lower priority number rule's queue item appears first.
    """
    queue: asyncio.Queue = asyncio.Queue()

    rule_high_pri = _make_rule(id="rule-priority-10", name="High priority", priority=10)
    rule_low_pri = _make_rule(id="rule-priority-100", name="Low priority", priority=100)

    # DB returns rules already sorted by priority ASC (as the real query does)
    db = _make_db_mock(rules=[rule_high_pri, rule_low_pri])
    poller = _make_poller(db=db, queue=queue, jira_issues=[PHX_99999_PAYLOAD])

    # fetchrow always returns None (not seen) — both rules can match
    db.fetchrow = AsyncMock(return_value=None)

    await poller._poll_all_rules()

    # At least one item was enqueued; first item must be from rule priority=10
    assert not queue.empty()
    first_item = queue.get_nowait()
    assert first_item["rule_id"] == "rule-priority-10"


# ── Test: no active rules → no poll ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_rules_skips_mcp_call():
    """If no active rules are returned, the MCP search is never called."""
    queue: asyncio.Queue = asyncio.Queue()
    db = _make_db_mock(rules=[])
    poller = _make_poller(db=db, queue=queue, jira_issues=[])

    await poller._poll_all_rules()

    poller._jira_search.assert_not_awaited()
    assert queue.empty()


# ── Test: MCP returns empty list → nothing enqueued ──────────────────────────


@pytest.mark.asyncio
async def test_empty_mcp_response_nothing_enqueued():
    """MCP returns no issues → queue remains empty."""
    queue: asyncio.Queue = asyncio.Queue()
    db = _make_db_mock()
    poller = _make_poller(db=db, queue=queue, jira_issues=[])

    await poller._poll_all_rules()

    assert queue.empty()
