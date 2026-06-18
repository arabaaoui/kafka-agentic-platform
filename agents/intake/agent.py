"""IntakeAgent — parses trigger payload and produces MissionContext kwargs."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from core.mission import MissionContext, MissionType
from agents.base import BaseAgent

log = logging.getLogger(__name__)


class IntakeAgent(BaseAgent):
    """Classifies a trigger payload into env/cluster/type/subject.

    Returns a dict suitable as kwargs for ``MissionContext`` on success,
    or a rejection dict on ``env_ambiguous`` / ``ignored``.
    """

    SKILL_NAME = "intake"

    def _build_tools(self):
        return []  # intake uses pure LLM reasoning — no toolkit tools

    async def classify(
        self,
        *,
        trigger_payload: dict[str, Any],
        tenant: str,
        source: str,
        mission_queue: Any = None,
        db_conn: Any = None,
    ) -> dict[str, Any] | None:
        """Classify the trigger and return MissionContext kwargs, or None on rejection."""
        from core.tenant import TenantRegistry
        try:
            tenant_cfg = TenantRegistry.get(tenant)
            available_envs = list(tenant_cfg.envs.keys())
        except Exception:
            available_envs = ["prod", "preprod", "lab"]

        today = datetime.now().strftime("%Y%m%d")
        temp_ctx = MissionContext(
            mission_id=f"{tenant.upper()}-INTAKE-INCIDENT-CLASSIFY-{today}-000",
            tenant=tenant,
            env="INTAKE",
            cluster="unknown",
            type=MissionType.INCIDENT,
            subject="intake",
        )

        prompt = (
            f"Source: {source}\n"
            f"Available Environments (STRICT): {available_envs}\n"
            f"Payload:\n```json\n{json.dumps(trigger_payload, ensure_ascii=False, indent=2)}\n```\n\n"
            "Classify this trigger. Use the 'env' field to specify which available environment matches. "
            "Output ONLY a JSON block as specified in your instructions."
        )


        raw = await self.run(temp_ctx, prompt, db_conn=None)

        parsed = _extract_json(raw)
        if parsed is None:
            log.error("IntakeAgent: could not parse JSON from LLM output: %s", raw[:200])
            return None

        status = parsed.get("status")
        if status in ("env_ambiguous", "ignored"):
            log.info("IntakeAgent: trigger rejected — %s: %s", status, parsed.get("reason"))
            return {"rejected": True, "status": status, "reason": parsed.get("reason", "")}

        subject = parsed.get("subject", "unknown")
        env = parsed.get("env", "preprod").upper()
        cluster = parsed.get("cluster", "")
        mission_type_str = parsed.get("type", "INCIDENT").upper()

        try:
            mission_type = MissionType[mission_type_str]
        except KeyError:
            mission_type = MissionType.INCIDENT

        # Extract original alertname and namespace for expert agents
        metadata = {}
        if source == "alertmanager":
            labels = trigger_payload.get("labels", {})
            if "alertname" in labels:
                metadata["alertname"] = labels["alertname"]
            
            # Use namespace from AI if possible, fallback to labels
            ns = parsed.get("namespace") or labels.get("namespace", "")
            if ns:
                metadata["alert_namespace"] = ns

        return {
            "rejected": False,
            "tenant": tenant,
            "env": env,
            "cluster": cluster,
            "type": mission_type,
            "subject": subject,
            "metadata": metadata,
            "confidence": parsed.get("confidence", "MEDIUM"),
            "jira_ticket_id": parsed.get("jira_ticket_id"),
        }


def _extract_json(text: str) -> dict | None:
    """Extract the first JSON object from LLM output (handles ``` fences)."""
    import re
    # Try fenced block first
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Try bare JSON object
    m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None
