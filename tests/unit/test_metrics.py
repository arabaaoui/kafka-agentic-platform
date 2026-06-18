"""Unit tests for the RAG Prometheus metrics."""

import unittest.mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.mem0_bridge import RAGIndex
from core.rag_ingest import ingest_audit, ingest_kb_card

# Import the metric objects to inspect them
from core.mem0_bridge import RAG_SEARCH_ERRORS, RAG_SEARCH_LATENCY
from core.rag_ingest import RAG_CHUNKS_INGESTED, RAG_INGEST_ERRORS


@pytest.mark.asyncio
async def test_search_metrics_success():
    """Test that search latency and count are recorded on success."""
    db_session = unittest.mock.AsyncMock(spec=AsyncSession)
    db_session.execute.return_value = unittest.mock.MagicMock()
    db_session.execute.return_value.mappings.return_value = []

    with unittest.mock.patch("core.mem0_bridge.embedding_service"):
        index = RAGIndex(db=db_session)

        # Get metric values before the call
        latency_before = RAG_SEARCH_LATENCY._sum.get()
        count_before = RAG_SEARCH_LATENCY._count.get()

        await index.search("test query")

        # Check that the count increased by 1 and latency was added
        assert RAG_SEARCH_LATENCY._count.get() == count_before + 1
        assert RAG_SEARCH_LATENCY._sum.get() > latency_before


@pytest.mark.asyncio
async def test_search_metrics_error():
    """Test that the error counter is incremented on search failure."""
    db_session = unittest.mock.AsyncMock(spec=AsyncSession)
    db_session.execute.side_effect = Exception("DB Error")

    with unittest.mock.patch("core.mem0_bridge.embedding_service"):
        index = RAGIndex(db=db_session)

        errors_before = RAG_SEARCH_ERRORS._value.get()
        await index.search("test query")
        errors_after = RAG_SEARCH_ERRORS._value.get()

        assert errors_after == errors_before + 1


@pytest.mark.asyncio
async def test_ingest_metrics_success():
    """Test that the ingested chunks counter is incremented on success."""
    db_session = unittest.mock.AsyncMock(spec=AsyncSession)

    with unittest.mock.patch("pathlib.Path.exists", return_value=True):
        with unittest.mock.patch(
            "pathlib.Path.read_text", return_value="## A section"
        ):
            with unittest.mock.patch("core.rag_ingest.embedding_service"):
                kb_chunks_before = RAG_CHUNKS_INGESTED.labels(type="kb")._value.get()
                audit_chunks_before = RAG_CHUNKS_INGESTED.labels(type="audit")._value.get()

                await ingest_kb_card("test-slug", db_session)
                await ingest_audit("test-mission", db_session)

                kb_chunks_after = RAG_CHUNKS_INGESTED.labels(type="kb")._value.get()
                audit_chunks_after = RAG_CHUNKS_INGESTED.labels(type="audit")._value.get()

                assert kb_chunks_after > kb_chunks_before
                assert audit_chunks_after > audit_chunks_before


@pytest.mark.asyncio
async def test_ingest_metrics_error():
    """Test that the ingest error counter is incremented on failure."""
    db_session = unittest.mock.AsyncMock(spec=AsyncSession)

    with unittest.mock.patch("pathlib.Path.exists", return_value=True):
        with unittest.mock.patch(
            "pathlib.Path.read_text", side_effect=Exception("Read Error")
        ):
            kb_errors_before = RAG_INGEST_ERRORS.labels(type="kb")._value.get()
            audit_errors_before = RAG_INGEST_ERRORS.labels(type="audit")._value.get()

            await ingest_kb_card("test-slug", db_session)
            await ingest_audit("test-mission", db_session)

            kb_errors_after = RAG_INGEST_ERRORS.labels(type="kb")._value.get()
            audit_errors_after = RAG_INGEST_ERRORS.labels(type="audit")._value.get()

            assert kb_errors_after == kb_errors_before + 1
            assert audit_errors_after == audit_errors_before + 1
