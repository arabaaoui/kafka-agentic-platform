"""PostMortemAgent — capitalisation agent that runs after mission completion.

Reads audit.md + per-agent outputs, produces BRIEF.md, creates/updates a KB card
in kb/incidents/, and regenerates kb/INDEX.md.

Not part of the active investigation pipeline — invoked via
POST /v1/missions/{id}/finalize (opt-in, explicit action).
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.base import BaseAgent, _OUTPUT_BASE
from core.kb_writer import KBCardWriter
from core.mission import MissionContext, MissionStatus
from core.rag_ingest import ingest_audit, ingest_kb_card

log = logging.getLogger(__name__)

_AUDIT_BASE = Path(os.getenv("AUDIT_DIR", "/app/audits"))

# Regex to extract the top-ranked hypothesis from audit.md
# Matches the first content row of a ranked-hypotheses table
_HYPOTHESIS_RE = re.compile(
    r"\|\s*1\s*\|\s*([^|]+)\|[^|]*\|[^|]*\|", re.MULTILINE
)
_SEVERITY_WORDS = {"critical", "high", "warning", "info", "low"}


class FinalizeResult:
    """Result of a finalize operation."""

    def __init__(
        self,
        *,
        mission_id: str,
        brief_path: str,
        kb_card_slug: str | None,
        kb_card_action: str,  # "created" | "updated" | "skipped"
        kb_index_card_count: int,
        finalized_at: datetime,
    ) -> None:
        self.mission_id = mission_id
        self.brief_path = brief_path
        self.kb_card_slug = kb_card_slug
        self.kb_card_action = kb_card_action
        self.kb_index_card_count = kb_index_card_count
        self.finalized_at = finalized_at

    def to_dict(self) -> dict:
        return {
            "mission_id": self.mission_id,
            "brief_path": self.brief_path,
            "kb_card_slug": self.kb_card_slug,
            "kb_card_action": self.kb_card_action,
            "kb_index_card_count": self.kb_index_card_count,
            "finalized_at": self.finalized_at.isoformat(),
        }


class PostMortemAgent(BaseAgent):
    """Capitalisation agent — invoked after mission completion."""

    SKILL_NAME = "post_mortem_analyst"

    def __init__(
        self,
        *,
        kb_dir: str | None = None,
        model: str | None = None,
        tenant_config: Any | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model=model, tenant_config=tenant_config, **kwargs)
        kb_path = kb_dir or os.getenv("KB_DIR", "/app/kb")
        self._kb_writer = KBCardWriter(kb_dir=kb_path)

    def _build_tools(self):
        return []  # reads files directly, no toolkit tools

    async def finalize(
        self,
        mission_ctx: MissionContext,
        db_conn: Any = None,
    ) -> FinalizeResult:
        """Run the full post-mortem workflow and return a FinalizeResult."""
        audit_md = _read_audit(mission_ctx)
        expert_outputs = _read_expert_outputs(mission_ctx)

        brief_md = await self._generate_brief(mission_ctx, audit_md, expert_outputs)
        brief_path = _write_brief(brief_md, mission_ctx)

        kb_slug: str | None = None
        kb_action = "skipped"
        card_count = 0

        if mission_ctx.status != MissionStatus.PARTIAL:
            kb_slug, kb_action = await self._create_or_update_card(
                mission_ctx, audit_md, brief_md
            )
            card_count = self._kb_writer.regenerate_index()

        finalized_at = datetime.now(timezone.utc)

        if db_conn is not None:
            await _persist_finalize(db_conn, mission_ctx, str(brief_path), kb_slug, finalized_at)
            try:
                await ingest_audit(mission_ctx.mission_id, db_conn)
                if kb_slug and kb_action in ("created", "updated"):
                    await ingest_kb_card(kb_slug, db_conn)
            except Exception as exc:
                log.warning("PostMortem: RAG indexing failed (non-fatal): %s", exc)

        log.info(
            "PostMortem %s: brief=%s card=%s action=%s index=%d",
            mission_ctx.mission_id,
            brief_path,
            kb_slug,
            kb_action,
            card_count,
        )
        return FinalizeResult(
            mission_id=mission_ctx.mission_id,
            brief_path=str(brief_path),
            kb_card_slug=kb_slug,
            kb_card_action=kb_action,
            kb_index_card_count=card_count,
            finalized_at=finalized_at,
        )

    async def _generate_brief(
        self,
        mission_ctx: MissionContext,
        audit_md: str,
        expert_outputs: dict[str, str],
    ) -> str:
        """Ask LLM to produce a structured BRIEF.md from the audit."""
        experts_block = "\n\n".join(
            f"### {agent} output\n{content}"
            for agent, content in expert_outputs.items()
            if content
        )
        prompt = (
            f"Mission: {mission_ctx.mission_id}\n"
            f"Env: {mission_ctx.env} | Cluster: {mission_ctx.cluster}\n"
            f"Subject: {mission_ctx.subject} | Type: {mission_ctx.type.value}\n\n"
            f"## Consolidated Audit\n\n{audit_md}\n\n"
            f"## Expert Reports\n\n{experts_block}\n\n"
            "---\nProduce a complete BRIEF.md following your SKILL.md template. "
            "Include all 5 sections: Résumé exécutif, Cause racine, Impact, "
            "Actions prises, Leçons apprises."
        )
        brief = await self.run(mission_ctx, prompt, db_conn=None)
        if not brief:
            brief = _fallback_brief(mission_ctx, audit_md)
        return brief

    async def _create_or_update_card(
        self,
        mission_ctx: MissionContext,
        audit_md: str,
        brief_md: str,
    ) -> tuple[str, str]:
        """Ask LLM to extract card fields, then write/update the card."""
        prompt = (
            f"Mission: {mission_ctx.mission_id} | Subject: {mission_ctx.subject}\n\n"
            f"## Audit\n\n{audit_md}\n\n"
            "---\nExtract the KB card fields as JSON with these keys:\n"
            '{"slug": "kebab-case-max-30-chars", "title": "...", "theme": "...", '
            '"tags": [...], "severity": "critical|high|warning|info|low", '
            '"symptoms": ["...","..."], "root_cause": "one sentence", '
            '"analysis_logic": "2-3 paragraphs for Logique d analyse section"}\n\n'
            "Rules: slug = kebab-case, max 30 chars, no spaces or YAML comments. "
            "symptoms: at least 2 observable signals."
        )
        raw = await self.run(mission_ctx, prompt, db_conn=None)
        fields = _parse_json_from_llm(raw)
        if not fields:
            log.warning("PostMortem: could not parse card fields from LLM output")
            return (None, "skipped")  # type: ignore[return-value]

        slug = fields.get("slug", "")
        if not slug:
            return (None, "skipped")  # type: ignore[return-value]

        body = _build_card_body(fields, mission_ctx)

        try:
            if self._kb_writer.card_exists(slug):
                self._kb_writer.update_card(slug, mission_ctx.mission_id)
                return slug, "updated"
            else:
                self._kb_writer.create_card(
                    slug=slug,
                    title=fields.get("title", slug),
                    theme=fields.get("theme", ""),
                    tags=fields.get("tags", []),
                    severity=fields.get("severity", "info"),
                    symptoms=fields.get("symptoms", []),
                    root_cause=fields.get("root_cause", ""),
                    body=body,
                    mission_id=mission_ctx.mission_id,
                    env=mission_ctx.env,
                )
                return slug, "created"
        except (ValueError, FileNotFoundError) as exc:
            log.error("PostMortem: KB card write failed: %s", exc)
            return (slug, "error")


# ── File helpers ──────────────────────────────────────────────────────────────

def _read_audit(mission_ctx: MissionContext) -> str:
    audit_path = _AUDIT_BASE / mission_ctx.mission_id / "audit.md"
    if not audit_path.exists():
        log.warning("No audit.md found at %s", audit_path)
        return ""
    return audit_path.read_text(encoding="utf-8")


def _read_expert_outputs(mission_ctx: MissionContext) -> dict[str, str]:
    out_dir = _OUTPUT_BASE / mission_ctx.mission_id
    outputs: dict[str, str] = {}
    if out_dir.is_dir():
        for md_file in sorted(out_dir.glob("*.md")):
            outputs[md_file.stem] = md_file.read_text(encoding="utf-8")
    return outputs


def _write_brief(brief_md: str, mission_ctx: MissionContext) -> Path:
    brief_dir = _AUDIT_BASE / mission_ctx.mission_id
    brief_dir.mkdir(parents=True, exist_ok=True)
    brief_path = brief_dir / "BRIEF.md"
    brief_path.write_text(brief_md, encoding="utf-8")
    return brief_path


def _fallback_brief(mission_ctx: MissionContext, audit_md: str) -> str:
    match = _HYPOTHESIS_RE.search(audit_md)
    top_hypothesis = match.group(1).strip() if match else "Unknown"
    return (
        f"---\nmission_id: {mission_ctx.mission_id}\n"
        f"env: {mission_ctx.env}\nstatus: partial\n---\n\n"
        f"# BRIEF — {mission_ctx.mission_id}\n\n"
        "## Résumé exécutif\n[LLM unavailable — partial brief]\n\n"
        f"## Cause racine identifiée\n{top_hypothesis}\n\n"
        "## Impact\n[Unknown]\n\n## Actions prises\nRead-only investigation.\n\n"
        "## Leçons apprises\n[To be completed manually.]\n"
    )


def _build_card_body(fields: dict, mission_ctx: MissionContext) -> str:
    analysis = fields.get("analysis_logic", "Analyse extraite de l'audit.")
    return (
        f"## Description\n\n{analysis}\n\n"
        f"## Logique d'analyse appliquée ★\n\n"
        "### Heuristiques déclenchantes\n\n"
        "[Extrait de l'audit — à affiner manuellement après relecture.]\n\n"
        "### Arbre de décision réellement appliqué\n\n"
        f"1. Mission {mission_ctx.mission_id} déclenchée.\n"
        "2. Agents experts lancés en parallèle (kafka-strimzi-expert, k8s-gcp-sre, prom-alerts-triage).\n"
        "3. Evidence consolidator a classé les hypothèses.\n\n"
        "### Signal clé qui a orienté le diagnostic\n\n"
        "[Extrait de l'audit — à affiner manuellement.]\n"
    )


def _parse_json_from_llm(raw: str) -> dict | None:
    """Extract the first JSON object from an LLM response string."""
    if not raw:
        return None
    # Try direct parse first
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass
    # Find JSON block in markdown code fence
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Find bare JSON object
    match = re.search(r"\{[^{}]*\"slug\"[^{}]*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


async def _persist_finalize(
    db_conn: Any,
    mission_ctx: MissionContext,
    brief_path: str,
    kb_card_slug: str | None,
    finalized_at: datetime,
) -> None:
    from sqlalchemy import text
    try:
        await db_conn.execute(
            text("""
                UPDATE audits 
                SET brief_path = :brief_path, kb_card_slug = :kb_card_slug, finalized_at = :finalized_at
                WHERE mission_id = :mission_id
            """),
            {
                "brief_path": brief_path,
                "kb_card_slug": kb_card_slug,
                "finalized_at": finalized_at,
                "mission_id": mission_ctx.mission_id,
            },
        )
    except Exception as exc:
        log.warning("PostMortem: DB update failed: %s", exc)
