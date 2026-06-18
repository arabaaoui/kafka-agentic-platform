"""EvidenceConsolidatorAgent — consolidates expert reports into audit.md."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.mission import MissionContext, MissionStatus
from agents.base import BaseAgent, _OUTPUT_BASE

log = logging.getLogger(__name__)

_AUDIT_BASE = Path(os.getenv("AUDIT_DIR", "/app/audits"))

_EXPERT_AGENTS = ("kafka_strimzi_expert", "k8s_gcp_sre", "prom_alerts_triage")


class EvidenceConsolidatorAgent(BaseAgent):
    """Reads per-agent Markdown outputs and produces the final ranked audit.md."""

    SKILL_NAME = "evidence_consolidator"

    def _build_tools(self):
        return []  # reads files directly — no toolkit tools needed

    async def investigate(self, mission_ctx: MissionContext, db_conn: Any = None) -> str:
        """Compatibility wrapper for investigate (expert interface)."""
        return await self.consolidate(mission_ctx, db_conn=db_conn)

    async def consolidate(
        self,
        mission_ctx: MissionContext,
        db_conn: Any = None,
    ) -> str:
        """Read expert outputs, consolidate, write audits/{mission_id}/audit.md."""
        expert_sections = _load_expert_outputs(mission_ctx)
        available = [name for name, content in expert_sections.items() if content]
        missing = [name for name, content in expert_sections.items() if not content]

        if missing:
            log.warning("EvidenceConsolidator: missing outputs from %s", missing)

        combined = _format_combined_input(expert_sections, mission_ctx)
        # Pass db_session via model_copy so BaseAgent.run() can perform RAG pre-injection
        # without reactivating agent_outputs persistence (db_conn stays None).
        agent_ctx = mission_ctx.model_copy(update={"db_session": db_conn})
        audit_md = await self.run(agent_ctx, combined, db_conn=None)

        if not audit_md:
            audit_md = _partial_fallback(mission_ctx, missing)

        await _write_audit(audit_md, mission_ctx, db_conn)
        await _update_mission_status(mission_ctx, missing, db_conn)
        return audit_md


# ── Helpers ───────────────────────────────────────────────────────────────────


def _load_expert_outputs(mission_ctx: MissionContext) -> dict[str, str]:
    out_dir = _OUTPUT_BASE / mission_ctx.mission_id
    return {
        agent: _read_safe(out_dir / f"{agent}.md")
        for agent in _EXPERT_AGENTS
    }


def _read_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError:
        return ""


def _format_combined_input(
    expert_sections: dict[str, str],
    mission_ctx: MissionContext,
) -> str:
    header = (
        f"Mission: {mission_ctx.mission_id}\n"
        f"Env: {mission_ctx.env} | Cluster: {mission_ctx.cluster} | Subject: {mission_ctx.subject}\n"
        f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n\n"
        "Below are the expert agent reports.  Consolidate them into the final audit.md.\n"
        "CRITICAL: If an agent failed, you MUST still include it in the 'Agent Status' and 'Evidence Matrix' tables with a clear indicator (e.g. ❌ or —).\n"
        "DO NOT break the Markdown table structure.\n\n"
    )
    parts = [header]
    for agent, content in expert_sections.items():
        if content:
            parts.append(f"---\n## Input from {agent}\n\n{content}\n")
        else:
            parts.append(f"---\n## Input from {agent}\n\n*(agent failed or produced no output)*\n")
    return "\n".join(parts)


def _partial_fallback(mission_ctx: MissionContext, missing: list[str]) -> str:
    return (
        f"# Audit — {mission_ctx.mission_id}\n\n"
        "⚠ PARTIAL AUDIT — all expert agents failed to produce output.\n\n"
        f"Missing agents: {', '.join(missing) or 'all'}\n\n"
        "Recommend manual investigation."
    )


async def _write_audit(
    content: str,
    mission_ctx: MissionContext,
    db_conn: Any,
) -> None:
    audit_dir = _AUDIT_BASE / mission_ctx.mission_id
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_path = audit_dir / "audit.md"
    audit_path.write_text(content, encoding="utf-8")
    log.info("EvidenceConsolidator: wrote %s", audit_path)

    if db_conn is not None:
        try:
            from sqlalchemy import text
            await db_conn.execute(
                text("""
                    INSERT INTO audits (id, mission_id, agent, content_md, created_at, updated_at)
                    VALUES (:id, :mission_id, :agent, :content_md, now(), now())
                    ON CONFLICT DO NOTHING
                """),
                {
                    "id": str(uuid.uuid4()),
                    "mission_id": mission_ctx.mission_id,
                    "agent": "evidence_consolidator",
                    "content_md": content,
                }
            )
        except Exception as exc:
            log.warning("EvidenceConsolidator: DB persist failed: %s", exc)


async def _update_mission_status(
    mission_ctx: MissionContext,
    missing: list[str],
    db_conn: Any,
) -> None:
    status = "PARTIAL" if missing else "CLOSED"
    if db_conn is not None:
        try:
            from sqlalchemy import text
            await db_conn.execute(
                text("UPDATE missions SET status = :status, closed_at = now() WHERE mission_id = :mission_id"),
                {"status": status, "mission_id": mission_ctx.mission_id}
            )
        except Exception as exc:
            log.warning("EvidenceConsolidator: mission status update failed: %s", exc)
