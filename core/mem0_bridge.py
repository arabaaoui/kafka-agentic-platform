"""Bridges for providing context to agents from internal knowledge sources.

This module contains the new RAG-based index (`RAGIndex`) that performs
semantic search over the database, and the old token-based index
(`KBIndexLegacy`) which is kept for reference.

The `KBIndex` name is now an alias for `RAGIndex` for backward compatibility.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import sqlalchemy as sa
import yaml
from prometheus_client import Counter, Summary
from sqlalchemy.ext.asyncio import AsyncSession

from core.embeddings import embedding_service
from core.models import AuditChunk, KBChunk

log = logging.getLogger(__name__)

_PUNCT_RE = re.compile(r"[^\w\s-]")

# --- Prometheus Metrics ---

RAG_SEARCH_LATENCY = Summary(
    "rag_search_latency_seconds", "Latency of RAG search operations"
)
RAG_SEARCH_ERRORS = Counter(
    "rag_search_errors_total", "Total number of errors during RAG search"
)


# --- New RAG-based Index ---


@dataclass
class RAGResult:
    """A single result from a semantic search."""

    source: str  # "kb" or "audit"
    ref: str  # kb_slug or mission_id
    chunk_text: str
    distance: float
    metadata: dict = field(default_factory=dict)


class RAGIndex:
    """Performs semantic search over the database using pgvector."""

    def __init__(self, db: AsyncSession, scope: list[str] | None = None, limit: int = 3):
        self.db = db
        self.scope = scope or ["kb", "audit"]
        self.limit = limit

    @RAG_SEARCH_LATENCY.time()
    async def search(self, query: str) -> list[RAGResult]:
        """Finds the most semantically similar chunks in the database."""
        if not query.strip():
            return []

        log.info("Performing RAG search for query: '%s'", query)
        try:
            query_embedding = embedding_service.embed_query(query)

            selects = []
            if "kb" in self.scope:
                kb_select = (
                    sa.select(
                        sa.literal("kb").label("source"),
                        KBChunk.kb_slug.label("ref"),
                        KBChunk.chunk_text,
                        KBChunk.chunk_metadata.label("metadata"),
                        KBChunk.embedding.cosine_distance(query_embedding).label("distance"),
                    )
                    .order_by("distance")
                    .limit(self.limit)
                )
                selects.append(kb_select)

            if "audit" in self.scope:
                audit_select = (
                    sa.select(
                        sa.literal("audit").label("source"),
                        AuditChunk.mission_id.label("ref"),
                        AuditChunk.chunk_text,
                        AuditChunk.chunk_metadata.label("metadata"),
                        AuditChunk.embedding.cosine_distance(query_embedding).label("distance"),
                    )
                    .order_by("distance")
                    .limit(self.limit)
                )
                selects.append(audit_select)

            if not selects:
                return []

            full_query = sa.union_all(*selects).order_by("distance").limit(self.limit)
            results = await self.db.execute(full_query)

            return [
                RAGResult(
                    source=row.source,
                    ref=row.ref,
                    chunk_text=row.chunk_text,
                    distance=row.distance,
                    metadata=row.metadata or {},
                )
                for row in results.mappings()
            ]

        except Exception:
            log.exception("RAG search failed. Returning empty context.")
            RAG_SEARCH_ERRORS.inc()
            return []

    def to_context_block(self, results: list[RAGResult]) -> str:
        """Formats RAG results into a Markdown block for agent injection."""
        if not results:
            return ""

        header = f"""---
## 📚 Knowledge Base — {len(results)} résultat(s) sémantique(s)

"""
        body_parts = []
        for res in results:
            if res.source == "kb":
                title = res.metadata.get("title", res.ref)
                severity = res.metadata.get("severity", "info")
                body_parts.append(
                    f"""### KB: {title} [{severity}]
Slug: {res.ref} · Distance: {res.distance:.3f}
{res.chunk_text}
"""
                )
            elif res.source == "audit":
                body_parts.append(
                    f"""### Audit passé: {res.ref}
Distance: {res.distance:.3f}
{res.chunk_text}
"""
                )
        footer = """
---

"""
        return header + "\n".join(body_parts) + footer

    def format_context(self, results: list[RAGResult]) -> str:
        """Alias for to_context_block for compatibility."""
        return self.to_context_block(results)


# --- Legacy Token-based Index (kept for reference) ---


def _tokenize(text: str) -> set[str]:
    """Lowercase, strip punctuation, split on whitespace and hyphens."""
    text = _PUNCT_RE.sub(" ", text.lower())
    return {t for t in re.split(r"[\s\-]+", text) if len(t) > 2}


@dataclass
class KBCard:
    """Represents a single KB card from a Markdown file."""

    slug: str
    title: str
    theme: str
    tags: list[str]
    severity: str
    symptoms: list[str]
    root_cause: str
    body: str
    path: Path

    _tag_tokens: set[str] = field(default_factory=set, repr=False, compare=False)
    _title_tokens: set[str] = field(default_factory=set, repr=False, compare=False)
    _cause_tokens: set[str] = field(default_factory=set, repr=False, compare=False)
    _symptom_tokens: set[str] = field(default_factory=set, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._tag_tokens = {t.lower() for t in self.tags}
        self._title_tokens = _tokenize(self.title)
        self._cause_tokens = _tokenize(self.root_cause)
        self._symptom_tokens = _tokenize(" ".join(self.symptoms))

    def score(self, query_tokens: set[str]) -> float:
        """Token overlap score: tags×3, title×2, root_cause×1, symptoms×1."""
        return (
            3.0 * len(query_tokens & self._tag_tokens)
            + 2.0 * len(query_tokens & self._title_tokens)
            + 1.0 * len(query_tokens & self._cause_tokens)
            + 1.0 * len(query_tokens & self._symptom_tokens)
        )

    def to_context_block(self) -> str:
        """Compact Markdown block for injection into a tool result."""
        symptom_lines = "\n".join(f"  - {s}" for s in self.symptoms[:3])
        return f"""### KB: {self.title} [{self.severity}]
**Slug**: `{self.slug}` · **Thème**: {self.theme}
**Cause racine**: {self.root_cause}
**Symptômes**:
{symptom_lines}
"""

    @classmethod
    def from_file(cls, path: Path) -> "KBCard | None":
        """Parse a YAML-frontmatter Markdown file. Returns None on any error."""
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            log.debug("Cannot read KB card %s: %s", path, exc)
            return None

        if not text.startswith("---"):
            return None

        parts = text.split("---", 2)
        if len(parts) < 3:
            return None

        try:
            fm = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError as exc:
            log.debug("YAML parse error in %s: %s", path, exc)
            return None

        slug = str(fm.get("slug", path.stem))
        if " " in slug or "#" in slug:
            return None

        return cls(
            slug=slug,
            title=str(fm.get("title", slug)),
            theme=str(fm.get("theme", "")),
            tags=[str(t) for t in (fm.get("tags") or [])],
            severity=str(fm.get("severity", "info")),
            symptoms=[str(s) for s in (fm.get("symptoms") or [])],
            root_cause=str(fm.get("root_cause", "")),
            body=parts[2].strip(),
            path=path,
        )


class KBIndexLegacy:
    """[LEGACY] Loads all KB cards and provides token-overlap search."""

    _TTL_SECONDS: float = 60.0

    def __init__(self, kb_dir: str | Path = "kb") -> None:
        self._kb_dir = Path(kb_dir)
        self._cards: list[KBCard] = []
        self._loaded = False
        self._loaded_at: float = 0.0

    def invalidate(self) -> None:
        self._loaded = False
        self._loaded_at = 0.0

    def _ensure_loaded(self) -> None:
        now = time.monotonic()
        if self._loaded and (now - self._loaded_at) < self._TTL_SECONDS:
            return
        incidents_dir = self._kb_dir / "incidents"
        if incidents_dir.is_dir():
            self._cards = [
                card
                for path in incidents_dir.glob("*.md")
                if (card := KBCard.from_file(path)) is not None
            ]
        else:
            self._cards = []
        self._loaded = True
        self._loaded_at = time.monotonic()

    def search(self, query: str, limit: int = 3) -> list[KBCard]:
        self._ensure_loaded()
        if not self._cards or not query.strip():
            return []
        query_tokens = _tokenize(query)
        scored = [(card.score(query_tokens), card) for card in self._cards]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [card for score, card in scored if score > 0][:limit]

    def format_context(self, cards: Sequence[KBCard]) -> str:
        if not cards:
            return ""
        header = f"""---
## 📚 Knowledge Base — {len(cards)} carte(s) pertinente(s)

"""
        body = "\n".join(card.to_context_block() for card in cards)
        footer = """
---

"""
        return header + body + footer


# For backward compatibility, KBIndex now points to the new RAG implementation.
KBIndex = RAGIndex
