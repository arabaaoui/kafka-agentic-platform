"""Integration tests for triggers/alertmanager_webhook.py.

Tests the AlertmanagerWebhookHandler directly (not via HTTP) to isolate
the business logic from the FastAPI/DB wiring.

Covers:
  - KafkaBrokerDown firing payload → 202, trigger inserted, matched=True
  - Cluster matching no active rule → trigger inserted, matched=False
  - Malformed payload (missing alerts) → handled gracefully (no firing → 0 accepted)
  - JSON fixture from tests/e2e/fixtures/alert-broker-down-preprod.json
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from core.filter_engine import FilterEngine, FilterRule
from triggers.alertmanager_webhook import AlertmanagerWebhookHandler, _fingerprint


# ── Fixtures ──────────────────────────────────────────────────────────────────


FIXTURES_DIR = Path(__file__).parent.parent / "e2e" / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def _broker_down_payload() -> dict:
    """Alertmanager V2 payload for KafkaBrokerDown on kafkahub-preprod."""
    return _load_fixture("alert-broker-down-preprod.json")


def _firing_alert(
    alertname: str = "KafkaBrokerDown",
    cluster: str = "kafkahub-preprod",
    severity: str = "critical",
    env: str = "preprod",
) -> dict:
    return {
        "status": "firing",
        "labels": {
            "alertname": alertname,
            "cluster": cluster,
            "severity": severity,
            "env": env,
            "namespace": f"kafka-{env}",
        },
        "annotations": {"summary": f"{alertname} in {cluster}"},
        "startsAt": "2026-05-10T10:00:00Z",
        "endsAt": "0001-01-01T00:00:00Z",
    }


def _make_rule(
    *,
    id: str = "rule-am-1",
    name: str = "Kafka alerts",
    priority: int = 10,
    criteria: dict | None = None,
    tenant: str = "enterprise",
) -> FilterRule:
    return FilterRule(
        id=id,
        tenant=tenant,
        scope="alertmanager",
        name=name,
        enabled=True,
        priority=priority,
        poll_interval_seconds=60,
        criteria=criteria or {
            "matchers": {"alertname": "KafkaBrokerDown", "severity": "critical"}
        },
    )


def _make_db_mock(*, trigger_exists: bool = False, rules: list[FilterRule] | None = None) -> AsyncMock:
    db = AsyncMock()

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
    db.fetchrow = AsyncMock(return_value={"id": "tid"} if trigger_exists else None)
    db.execute = AsyncMock(return_value=None)
    return db


def _make_handler(
    *,
    db: AsyncMock,
    rules: list[FilterRule] | None = None,
    trigger_exists: bool = False,
    tenant: str = "enterprise",
) -> AlertmanagerWebhookHandler:
    queue: asyncio.Queue = asyncio.Queue()
    handler = AlertmanagerWebhookHandler(
        db_conn=db,
        mission_queue=queue,
        tenant=tenant,
    )
    return handler


# ── Test: KafkaBrokerDown fixture → matched ───────────────────────────────────


@pytest.mark.asyncio
async def test_broker_down_fixture_accepted():
    """Full fixture payload → handler returns accepted=1."""
    payload = _broker_down_payload()
    db = _make_db_mock()
    handler = _make_handler(db=db)

    result = await handler.handle(payload)

    assert result["accepted"] == 1
    assert result["total_firing"] == 1


@pytest.mark.asyncio
async def test_broker_down_trigger_inserted_in_db():
    """Matched alert causes a trigger row to be inserted."""
    payload = _broker_down_payload()
    db = _make_db_mock()
    handler = _make_handler(db=db)

    await handler.handle(payload)

    execute_calls = [str(c) for c in db.execute.call_args_list]
    insert_calls = [c for c in execute_calls if "INSERT INTO triggers" in c]
    assert insert_calls, "Expected a trigger INSERT for matched alert"


@pytest.mark.asyncio
async def test_broker_down_mission_enqueued():
    """Matched alert is placed in the mission queue."""
    payload = _broker_down_payload()
    db = _make_db_mock()
    queue: asyncio.Queue = asyncio.Queue()
    handler = AlertmanagerWebhookHandler(
        db_conn=db,
        mission_queue=queue,
        tenant="enterprise",
    )

    await handler.handle(payload)

    assert not queue.empty()
    item = queue.get_nowait()
    assert item["source"] == "alertmanager"
    assert item["tenant"] == "enterprise"


# ── Test: cluster matching no active rule → rejected ─────────────────────────


@pytest.mark.asyncio
async def test_no_matching_rule_trigger_not_matched():
    """Alert for a cluster with no matching rule → trigger rejected (matched=False)."""
    payload = {
        "version": "4",
        "status": "firing",
        "alerts": [_firing_alert(cluster="kafkahub-staging", alertname="SomeOtherAlert")],
    }

    # Rule only matches KafkaBrokerDown on kafkahub-preprod
    rule = _make_rule(criteria={
        "matchers": {"alertname": "KafkaBrokerDown", "cluster": "kafkahub-preprod"}
    })
    db = _make_db_mock(rules=[rule])
    queue: asyncio.Queue = asyncio.Queue()
    handler = AlertmanagerWebhookHandler(
        db_conn=db,
        mission_queue=queue,
        tenant="enterprise",
    )

    result = await handler.handle(payload)

    assert result["accepted"] == 0
    assert result["total_firing"] == 1
    assert queue.empty(), "Unmatched alert must not be enqueued"


@pytest.mark.asyncio
async def test_no_matching_rule_filter_match_log_written():
    """Even rejected alerts are logged to filter_match_log."""
    payload = {
        "version": "4",
        "status": "firing",
        "alerts": [_firing_alert(cluster="kafkahub-staging", alertname="SomeOtherAlert")],
    }
    rule = _make_rule(criteria={
        "matchers": {"alertname": "KafkaBrokerDown", "cluster": "kafkahub-preprod"}
    })
    db = _make_db_mock(rules=[rule])
    queue: asyncio.Queue = asyncio.Queue()
    handler = AlertmanagerWebhookHandler(
        db_conn=db,
        mission_queue=queue,
        tenant="enterprise",
    )

    await handler.handle(payload)

    execute_calls = [str(c) for c in db.execute.call_args_list]
    log_calls = [c for c in execute_calls if "filter_match_log" in c]
    assert log_calls, "Expected filter_match_log entry for rejected alert"


# ── Test: malformed payload (missing commonLabels) → graceful ─────────────────


@pytest.mark.asyncio
async def test_missing_alerts_key_returns_zero_accepted():
    """Payload without 'alerts' key → no firing alerts → 0 accepted."""
    payload = {
        "version": "4",
        "status": "firing",
        "commonLabels": {
            "alertname": "KafkaBrokerDown",
            "cluster": "kafkahub-preprod",
        },
        # 'alerts' key deliberately omitted
    }
    db = _make_db_mock()
    handler = _make_handler(db=db)

    result = await handler.handle(payload)

    assert result["accepted"] == 0
    assert "no firing alerts" in result.get("reason", "").lower()


@pytest.mark.asyncio
async def test_resolved_alerts_not_processed():
    """Resolved alerts (status=resolved) must be ignored."""
    payload = {
        "version": "4",
        "status": "resolved",
        "alerts": [{
            "status": "resolved",
            "labels": {
                "alertname": "KafkaBrokerDown",
                "cluster": "kafkahub-preprod",
                "severity": "critical",
            },
            "annotations": {},
            "startsAt": "2026-05-10T10:00:00Z",
            "endsAt": "2026-05-10T10:30:00Z",
        }],
    }
    db = _make_db_mock()
    queue: asyncio.Queue = asyncio.Queue()
    handler = AlertmanagerWebhookHandler(
        db_conn=db,
        mission_queue=queue,
        tenant="enterprise",
    )

    result = await handler.handle(payload)

    assert result["accepted"] == 0
    assert queue.empty()


@pytest.mark.asyncio
async def test_empty_alerts_list_returns_zero():
    """Empty alerts array → no firing alerts → 0 accepted."""
    payload = {"version": "4", "status": "firing", "alerts": []}
    db = _make_db_mock()
    handler = _make_handler(db=db)

    result = await handler.handle(payload)

    assert result["accepted"] == 0


# ── Test: already-seen alert not re-enqueued ─────────────────────────────────


@pytest.mark.asyncio
async def test_already_seen_alert_not_enqueued():
    """If the alert fingerprint already exists in DB, it is skipped."""
    payload = _broker_down_payload()
    db = _make_db_mock(trigger_exists=True)
    queue: asyncio.Queue = asyncio.Queue()
    handler = AlertmanagerWebhookHandler(
        db_conn=db,
        mission_queue=queue,
        tenant="enterprise",
    )

    result = await handler.handle(payload)

    assert result["accepted"] == 0
    assert queue.empty()


# ── Test: _fingerprint stability ──────────────────────────────────────────────


def test_fingerprint_is_deterministic():
    """Same alert labels always produce the same fingerprint."""
    alert = _firing_alert()
    fp1 = _fingerprint(alert)
    fp2 = _fingerprint(alert)
    assert fp1 == fp2


def test_fingerprint_differs_for_different_clusters():
    """Different clusters produce different fingerprints."""
    alert_preprod = _firing_alert(cluster="kafkahub-preprod")
    alert_prod = _firing_alert(cluster="kafkahub-prod")
    assert _fingerprint(alert_preprod) != _fingerprint(alert_prod)


# ── Test: multiple alerts in one payload ──────────────────────────────────────


@pytest.mark.asyncio
async def test_multiple_firing_alerts_all_processed():
    """Two distinct firing alerts → both processed."""
    payload = {
        "version": "4",
        "status": "firing",
        "alerts": [
            _firing_alert(cluster="kafkahub-preprod"),
            {
                **_firing_alert(cluster="kafkahub-preprod"),
                "labels": {
                    "alertname": "KafkaBrokerDown",
                    "cluster": "kafkahub-preprod",
                    "severity": "critical",
                    "env": "preprod",
                    "namespace": "kafka-preprod",
                    "instance": "kafka-preprod-broker-2",  # different instance
                },
            },
        ],
    }
    db = _make_db_mock()
    queue: asyncio.Queue = asyncio.Queue()
    handler = AlertmanagerWebhookHandler(
        db_conn=db,
        mission_queue=queue,
        tenant="enterprise",
    )

    result = await handler.handle(payload)

    assert result["total_firing"] == 2
