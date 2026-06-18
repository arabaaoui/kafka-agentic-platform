"""Jira MCP poller — polls Jira via c4-atlassian MCP and feeds the filter engine.

Runs as a long-lived asyncio task started by the FastAPI lifespan.
For each poll cycle it:
  1. Loads active Jira filter rules from Postgres.
  2. For each rule: calls ``jira_search_issues`` via MCP using the rule JQL.
  3. Passes each returned issue through FilterEngine local pre-filter.
  4. Creates a Trigger row and enqueues a mission-creation task on match.
  5. Logs all evaluations to filter_match_log.

MCP transport: HTTP SSE (c4-atlassian MCP server at MCP_C4_ATLASSIAN_URL).
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import text

from core.filter_engine import FilterEngine, FilterRule, build_jql

log = logging.getLogger(__name__)

_MCP_URL = os.getenv("MCP_C4_ATLASSIAN_URL", "http://localhost:3010")
_DEFAULT_POLL_INTERVAL = 60  # seconds — overridden per rule


class JiraMcpPoller:
    """Polls Jira via MCP and routes matching issues to the mission creation queue.

    Parameters
    ----------
    db_engine:
        SQLAlchemy engine used to create isolated sessions.
    mission_queue:
        asyncio.Queue into which matched (trigger_id, mission_context_kwargs) dicts
        are placed for the pipeline orchestrator to consume.
    """

    def __init__(
        self,
        *,
        db_engine: Any,
        engine: FilterEngine | None = None,
        mcp_url: str = _MCP_URL,
    ) -> None:
        self._db_engine = db_engine
        self._engine = engine or FilterEngine()
        self._mcp_url = mcp_url
        self._stop_event = asyncio.Event()
        self._http: httpx.AsyncClient | None = None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start polling loop — runs until stop() is called."""
        headers = {
            "x-jira-token": os.getenv("JIRA_MCP_TOKEN", ""),
            "jwt-username": os.getenv("MCP_USERNAME", ""),
        }
        self._http = httpx.AsyncClient(
            base_url=self._mcp_url, 
            headers=headers,
            timeout=30.0,
            verify=False
        )
        log.info("JiraMcpPoller started (MCP: %s, User: %s)", self._mcp_url, headers["jwt-username"])
        try:
            await self._run()
        finally:
            await self._http.aclose()
            self._http = None
            log.info("JiraMcpPoller stopped")

    async def stop(self) -> None:
        self._stop_event.set()

    # ── Main loop ────────────────────────────────────────────────────────────

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                # Use a fresh connection for each poll cycle
                async with self._db_engine.begin() as conn:
                    await self._poll_all_rules(conn)
            except Exception as exc:
                log.error("JiraMcpPoller poll cycle error: %s", exc, exc_info=True)
            
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=_DEFAULT_POLL_INTERVAL
                )
            except asyncio.TimeoutError:
                pass

    async def _poll_all_rules(self, db: Any) -> None:
        rules = await self._load_rules(db)
        if not rules:
            log.debug("No active Jira filter rules — skipping poll")
            return

        for rule in rules:
            try:
                await self._poll_rule(rule, db)
            except Exception as exc:
                log.warning("Poll failed for rule '%s': %s", rule.name, exc)

    # ── Per-rule poll ─────────────────────────────────────────────────────────

    async def _poll_rule(self, rule: FilterRule, db: Any) -> None:
        jql = build_jql(rule.criteria)
        if not jql:
            log.warning("Rule '%s' produced empty JQL — skipping", rule.name)
            return

        issues = await self._jira_search(jql)
        log.debug("Rule '%s': %d issues from Jira", rule.name, len(issues))

        for issue in issues:
            external_id = issue.get("key", "")
            if not external_id:
                continue

            already_seen = await self._trigger_exists(rule.tenant, "jira", external_id, db)
            if already_seen:
                continue

            result, evaluated = self._engine.evaluate(issue, [rule], "jira")
            trigger_id = await self._upsert_trigger(rule.tenant, "jira", external_id, issue, result.matched, db)
            await self._log_matches(trigger_id, evaluated, db)

            if result.matched:
                log.info(
                    "Matched: rule='%s' issue='%s' — trigger inserted (workers will claim it)",
                    rule.name, external_id,
                )

    # ── MCP call ─────────────────────────────────────────────────────────────

    async def _jira_search(self, jql: str, max_results: int = 50) -> list[dict]:
        """Call jira_search_issues tool via MCP HTTP."""
        assert self._http is not None
        try:
            resp = await self._http.post(
                "/tools/call",
                json={
                    "tool": "jira_search_issues",
                    "arguments": {"jql": jql, "maxResults": max_results},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            # Assuming the response is a dict with 'issues' key
            return data.get("issues", [])
        except httpx.HTTPStatusError as exc:
            log.error("MCP jira_search_issues HTTP error %s: %s", exc.response.status_code, exc)
            return []
        except Exception as exc:
            log.error("MCP jira_search_issues error: %s", exc)
            return []

    # ── DB helpers ────────────────────────────────────────────────────────────

    async def _load_rules(self, db: Any) -> list[FilterRule]:
        q = text(
            "SELECT id, tenant, scope, name, enabled, priority, poll_interval_seconds, criteria "
            "FROM filter_rules WHERE scope = 'jira' AND enabled = TRUE ORDER BY priority ASC"
        )
        res = await db.execute(q)
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

    async def _trigger_exists(self, tenant: str, source: str, external_id: str, db: Any) -> bool:
        q = text("SELECT id FROM triggers WHERE tenant=:tenant AND source=:source AND external_id=:ext_id")
        res = await db.execute(q, {"tenant": tenant, "source": source, "ext_id": external_id})
        return res.fetchone() is not None

    async def _upsert_trigger(
        self, tenant: str, source: str, external_id: str,
        payload: dict, matched: bool, db: Any,
    ) -> str:
        import json
        trigger_id = str(uuid.uuid4())
        q = text(
            """
            INSERT INTO triggers (id, tenant, source, external_id, payload, matched, received_at)
            VALUES (:id, :tenant, :source, :ext_id, :payload, :matched, :now)
            ON CONFLICT (tenant, source, external_id) DO UPDATE
              SET matched = EXCLUDED.matched,
                  processed_at = now()
            RETURNING id
            """
        )
        res = await db.execute(
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

    async def _log_matches(
        self,
        trigger_id: str,
        evaluated: list,
        db: Any,
    ) -> None:
        for rule, matched, reason in evaluated:
            q = text(
                """
                INSERT INTO filter_match_log (id, rule_id, trigger_id, matched, reason, matched_at)
                VALUES (:id, :rule_id, :trigger_id, :matched, :reason, :now)
                """
            )
            await db.execute(
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
