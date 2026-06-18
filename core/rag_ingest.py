"""Service for ingesting and chunking Markdown documents for RAG.

This module provides functions to read KB cards and mission audits from
the filesystem, split them into manageable chunks, generate embeddings,
and store them in the database.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from prometheus_client import Counter
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from core.embeddings import embedding_service
from core.models import AuditChunk, KBChunk

logger = logging.getLogger(__name__)

# --- Prometheus Metrics ---

RAG_INGEST_ERRORS = Counter(
    "rag_ingest_errors_total", "Total number of errors during RAG ingestion", ["type"]
)
RAG_CHUNKS_INGESTED = Counter(
    "rag_chunks_ingested_total", "Total number of chunks ingested into RAG index", ["type"]
)


# A simple proxy for token counting. In a real-world scenario, this should use
# the actual tokenizer for the model (e.g., len(tokenizer.encode(text))).
# For `e5-small`, a rough approximation is 1 token ~ 4 chars.
TOKEN_PROXY_CHAR_DIVISOR = 4


def _chunk_markdown(
    markdown_content: str, max_tokens: int = 512, overlap_tokens: int = 51
) -> list[tuple[str | None, str]]:
    """
    Splits a Markdown document into chunks.

    The strategy is to first split by H2 headings ('##'), then sub-split
    any long sections using a sliding token window.

    Args:
        markdown_content: The Markdown text to chunk.
        max_tokens: The maximum number of tokens per chunk.
        overlap_tokens: The number of tokens to overlap between chunks of a long section.

    Returns:
        A list of (section_title, chunk_text) tuples.
    """
    chunks = []
    # Split by H2 headings, keeping the heading with the content
    sections = re.split(r"(##\s.*)", markdown_content)
    if not sections:
        return [(None, markdown_content)]

    # The first element is content before the first H2, which we pair with a None title.
    # Then, we iterate through pairs of (H2_title, content_after_H2).
    if sections[0].strip():
        chunks.append((None, sections[0].strip()))

    for i in range(1, len(sections), 2):
        title = sections[i].strip().replace("## ", "")
        content = sections[i + 1].strip()
        section_text = f"""## {title}
{content}"""

        # Use character count as a rough proxy for token count
        max_chars = max_tokens * TOKEN_PROXY_CHAR_DIVISOR
        if len(section_text) <= max_chars:
            chunks.append((title, section_text))
        else:
            # Sliding window for long sections
            overlap_chars = overlap_tokens * TOKEN_PROXY_CHAR_DIVISOR
            start = 0
            while start < len(section_text):
                end = start + max_chars
                chunk = section_text[start:end]
                chunks.append((title, chunk))
                start += max_chars - overlap_chars
    return chunks


async def ingest_kb_card(slug: str, db: AsyncSession) -> int:
    """
    Ingests a single KB card into the database.

    This is an idempotent operation. It will delete any existing chunks
    for the given slug before inserting the new ones.

    Returns:
        The number of chunks ingested.
    """
    kb_path = Path(f"kb/incidents/{slug}.md")
    if not kb_path.exists():
        logger.warning("KB card not found for ingestion: %s", kb_path)
        return 0

    try:
        logger.info("Ingesting KB card: %s", slug)
        content = kb_path.read_text(encoding="utf-8")
        # TODO: Extract metadata (severity, tags) from the card's frontmatter
        metadata = {"slug": slug}

        await db.execute(delete(KBChunk).where(KBChunk.kb_slug == slug))

        chunk_tuples = _chunk_markdown(content)
        if not chunk_tuples:
            return 0

        chunk_texts = [text for _, text in chunk_tuples]
        embeddings = embedding_service.embed_passage(chunk_texts)

        new_chunks = [
            KBChunk(
                kb_slug=slug,
                chunk_index=i,
                chunk_text=chunk_texts[i],
                embedding=embeddings[i],
                chunk_metadata={**metadata, "section_title": title},
                )            for i, (title, _) in enumerate(chunk_tuples)
        ]

        db.add_all(new_chunks)
        await db.flush()

        count = len(new_chunks)
        RAG_CHUNKS_INGESTED.labels(type="kb").inc(count)
        logger.info("Ingested %d chunks for KB card '%s'", count, slug)
        return count
    except Exception:
        RAG_INGEST_ERRORS.labels(type="kb").inc()
        logger.exception("Failed to ingest KB card '%s'", slug)
        return 0


async def ingest_audit(mission_id: str, db: AsyncSession) -> int:
    """
    Ingests a single mission audit into the database.

    Idempotent operation: deletes existing chunks before inserting new ones.

    Returns:
        The number of chunks ingested.
    """
    audit_path = Path(f"audits/{mission_id}/audit.md")
    if not audit_path.exists():
        logger.warning("Mission audit not found for ingestion: %s", audit_path)
        return 0

    try:
        logger.info("Ingesting mission audit: %s", mission_id)
        content = audit_path.read_text(encoding="utf-8")
        # TODO: Extract metadata (env, cluster, type, subject) from the audit
        metadata = {"mission_id": mission_id}

        await db.execute(delete(AuditChunk).where(AuditChunk.mission_id == mission_id))

        chunk_tuples = _chunk_markdown(content)
        if not chunk_tuples:
            return 0

        chunk_texts = [text for _, text in chunk_tuples]
        embeddings = embedding_service.embed_passage(chunk_texts)

        new_chunks = [
            AuditChunk(
                mission_id=mission_id,
                chunk_index=i,
                chunk_text=chunk_texts[i],
                embedding=embeddings[i],
                chunk_metadata={**metadata, "section_title": title},
                )            for i, (title, _) in enumerate(chunk_tuples)
        ]

        db.add_all(new_chunks)
        await db.flush()

        count = len(new_chunks)
        RAG_CHUNKS_INGESTED.labels(type="audit").inc(count)
        logger.info("Ingested %d chunks for mission audit '%s'", count, mission_id)
        return count
    except Exception:
        RAG_INGEST_ERRORS.labels(type="audit").inc()
        logger.exception("Failed to ingest mission audit '%s'", mission_id)
        return 0
