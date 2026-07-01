"""Alertmanager webhook — receives POST /webhooks/alertmanager and feeds the filter engine.

Alertmanager calls this endpoint on every firing / resolved group.
Only FIRING alerts are forwarded to the filter engine; resolved alerts are dropped.

Payload schema (Alertmanager v2):
    {
      "version": "4",
      "alerts": [
        {
          "status": "firing",
          "labels": {"alertname": "KafkaBrokerDown", "severity": "critical", "cluster": "kafkahub-preprod"},
          "annotations": {"summary": "Broker 2 is down"},
          "startsAt": "...",
          "endsAt": "0001-01-01T00:00:00Z"
        }
      ]
    }
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from core.filter_engine import FilterEngine, FilterRule

log = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/alertmanager", status_code=202)
async def receive_alertmanager(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Receive alerts from Prometheus Alertmanager.

    Returns 202 immediately; processing runs in a background task to avoid
    blocking Alertmanager (which retries on slow responses).
    """
    payload = await request.json()
    background_tasks.add_task(_process_alertmanager_payload, payload)
    return {"status": "accepted"}


async def _process_alertmanager_payload(payload: dict[str, Any]) -> None:
    """Background processing: evaluate filter rules and insert matched triggers as durable queue entries."""
    from core.db import _SessionLocal

    async with _SessionLocal() as session:
        conn = await session.connection()
        handler = AlertmanagerWebhookHandler(
            db_conn=conn,
            tenant="enterprise",
        )
        result = await handler.handle(payload)
        await session.commit()

    for item in result.get("matched_items", []):
        log.info("Alertmanager: trigger inserted for %s (workers will claim it)", item["external_id"])


class AlertmanagerWebhookHandler:
    """Processes one Alertmanager POST payload against active filter rules.

    Parameters
    ----------
    db_conn : asyncpg connection or SQLAlchemy async session.
    mission_queue : asyncio.Queue for matched alerts.
    engine : FilterEngine instance (injected for testability).
    tenant : Tenant slug to load rules for.
    """

    def __init__(
        self,
        *,
        db_conn: Any,
        engine: FilterEngine | None = None,
        tenant: str = "enterprise",
    ) -> None:
        self._db = db_conn
        self._engine = engine or FilterEngine()
        self._tenant = tenant

    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        alerts = payload.get("alerts", [])
        firing = []
        for a in alerts:
            status = a.get("status", "")
            if isinstance(status, dict):
                # API v2 format: status is a dict with 'state' field
                if status.get("state") == "active":
                    firing.append(a)
            elif str(status).lower() == "firing":
                # Webhook format: status is a direct string
                firing.append(a)

        if not firing:
            return {"accepted": 0, "reason": "no firing alerts in payload", "matched_items": []}

        rules = await self._load_filter_rules()
        accepted = 0
        matched_items = []

        for alert in firing:
            external_id = _fingerprint(alert)
            already_seen = await self._trigger_exists(self._tenant, "alertmanager", external_id)
            if already_seen:
                continue

            result, evaluated = self._engine.evaluate(alert, rules, "alertmanager")
            trigger_id = await self._upsert_trigger(
                self._tenant, "alertmanager", external_id, alert, result.matched
            )
            await self._log_matches(trigger_id, evaluated)

            if result.matched:
                log.info(
                    "Alertmanager match: rule='%s' alert='%s'",
                    result.rule_name, external_id,
                )
                matched_items.append({
                    "trigger_id": trigger_id,
                    "tenant": self._tenant,
                    "source": "alertmanager",
                    "external_id": external_id,
                    "payload": alert,
                    "rule_id": result.rule_id,
                })
                accepted += 1

        return {
            "accepted": accepted, 
            "total_firing": len(firing),
            "matched_items": matched_items
        }

    # ── DB helpers ────────────────────────────────────────────────────────────

    async def _load_filter_rules(self) -> list[FilterRule]:
        from sqlalchemy import text
        q = text(
            "SELECT id, tenant, scope, name, enabled, priority, poll_interval_seconds, criteria "
            "FROM filter_rules WHERE scope = 'alertmanager' AND enabled = TRUE AND tenant = :tenant "
            "ORDER BY priority ASC"
        )
        res = await self._db.execute(q, {"tenant": self._tenant})
        rows = res.fetchall()
        return [
            FilterRule(
                id=str(r.id),
                tenant=r.tenant,
                scope=r.scope,
                name=r.name,
                enabled=r.enabled,
                priority=r.priority,
                poll_interval_seconds=r.poll_interval_seconds,
                criteria=r.criteria,
            )
            for r in rows
        ]

    async def _trigger_exists(self, tenant: str, source: str, external_id: str) -> bool:
        from sqlalchemy import text
        q = text("SELECT id FROM triggers WHERE tenant=:tenant AND source=:source AND external_id=:ext_id")
        res = await self._db.execute(q, {"tenant": tenant, "source": source, "ext_id": external_id})
        return res.fetchone() is not None

    async def _upsert_trigger(
        self, tenant: str, source: str, external_id: str,
        payload: dict, matched: bool,
    ) -> str:
        import json
        from sqlalchemy import text
        trigger_id = str(uuid.uuid4())
        q = text(
            """
            INSERT INTO triggers (id, tenant, source, external_id, payload, matched, received_at)
            VALUES (:id, :tenant, :source, :ext_id, :payload, :matched, :now)
            ON CONFLICT (tenant, source, external_id) DO UPDATE
              SET matched = EXCLUDED.matched, processed_at = now()
            RETURNING id
            """
        )
        res = await self._db.execute(
            q,
            {
                "id": trigger_id,
                "tenant": tenant,
                "source": source,
                "ext_id": external_id,
                "payload": json.dumps(payload),
                "matched": matched,
                "now": datetime.now(timezone.utc),
            }
        )
        row = res.fetchone()
        return str(row.id)

    async def _log_matches(self, trigger_id: str, evaluated: list) -> None:
        from sqlalchemy import text
        for rule, matched, reason in evaluated:
            q = text(
                """
                INSERT INTO filter_match_log (id, rule_id, trigger_id, matched, reason, matched_at)
                VALUES (:id, :rule_id, :trigger_id, :matched, :reason, :now)
                """
            )
            await self._db.execute(
                q,
                {
                    "id": str(uuid.uuid4()),
                    "rule_id": rule.id,
                    "trigger_id": trigger_id,
                    "matched": matched,
                    "reason": reason,
                    "now": datetime.now(timezone.utc),
                }
            )


def _fingerprint(alert: dict[str, Any]) -> str:
    """Derive a stable ID from the alert labels (mirrors Alertmanager fingerprinting)."""
    labels = alert.get("labels", {})
    parts = ":".join(f"{k}={v}" for k, v in sorted(labels.items()))
    # Use a deterministic UUID5 so the same alert always gets the same external_id.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, parts))
