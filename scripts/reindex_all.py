"""One-shot bootstrap script to index all existing KB cards and mission audits.

This script iterates through the `kb/incidents` and `audits` directories,
calling the ingestion service for each document found. It's intended to be
run once after deploying the RAG feature to populate the database with
historical data.
"""

import asyncio
import logging
from pathlib import Path

from core.db import dispose_engine, get_session
from core.rag_ingest import ingest_audit, ingest_kb_card

# Configure logging to see the output from the ingestion service
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
log = logging.getLogger(__name__)


async def main() -> None:
    """Finds and ingests all KB cards and mission audits."""
    log.info("Starting historical data re-indexing...")

    total_kb_chunks = 0
    total_audit_chunks = 0
    kb_card_count = 0
    audit_count = 0

    async with get_session() as session:
        # Ingest KB cards
        kb_path = Path("kb/incidents")
        if kb_path.is_dir():
            log.info("Scanning for KB cards in %s...", kb_path)
            kb_files = list(kb_path.glob("*.md"))
            kb_card_count = len(kb_files)
            for kb_file in kb_files:
                slug = kb_file.stem
                total_kb_chunks += await ingest_kb_card(slug, session)
        else:
            log.warning("KB incidents directory not found: %s", kb_path)

        # Ingest mission audits
        audits_path = Path("audits")
        if audits_path.is_dir():
            log.info("Scanning for mission audits in %s...", audits_path)
            audit_files = list(audits_path.glob("*/audit.md"))
            audit_count = len(audit_files)
            for audit_file in audit_files:
                mission_id = audit_file.parent.name
                total_audit_chunks += await ingest_audit(mission_id, session)
        else:
            log.warning("Audits directory not found: %s", audits_path)

    log.info("--- Re-indexing complete ---")
    log.info("Processed %d KB cards, ingested %d chunks.", kb_card_count, total_kb_chunks)
    log.info("Processed %d mission audits, ingested %d chunks.", audit_count, total_audit_chunks)
    log.info(
        "Total chunks ingested: %d", total_kb_chunks + total_audit_chunks
    )

    # Gracefully shut down the database connection pool
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
