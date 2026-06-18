"""Unit tests for the RAG search bridge in core/mem0_bridge.py."""

import unittest.mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.mem0_bridge import RAGIndex, RAGResult


@pytest.fixture
def mock_db_session():
    """Fixture for a mocked AsyncSession."""
    session = unittest.mock.AsyncMock(spec=AsyncSession)
    
    # Mock the result of db.execute() to be an iterable of mock rows
    mock_result = unittest.mock.MagicMock()

    def mock_mappings():
        # Simulate rows returned by a SELECT query
        yield unittest.mock.MagicMock(
            source="kb",
            ref="test-slug",
            chunk_text="This is a KB chunk.",
            distance=0.123,
            metadata={"title": "Test KB", "severity": "high"},
        )
        yield unittest.mock.MagicMock(
            source="audit",
            ref="audit-123",
            chunk_text="This is an audit chunk.",
            distance=0.456,
            metadata={"mission_id": "audit-123"},
        )

    mock_result.mappings.return_value = mock_mappings()
    session.execute.return_value = mock_result
    return session


@pytest.fixture
def mock_embedding_service():
    """Fixture to mock the embedding service."""
    with unittest.mock.patch("core.mem0_bridge.embedding_service") as mock_service:
        mock_service.embed_query.return_value = [0.1] * 384
        yield mock_service


@pytest.mark.asyncio
async def test_search_returns_rag_results(mock_db_session, mock_embedding_service):
    """Test that the search method returns a list of RAGResult objects."""
    index = RAGIndex(db=mock_db_session)
    results = await index.search("test query")

    assert len(results) == 2
    assert isinstance(results[0], RAGResult)
    assert results[0].source == "kb"
    assert results[0].ref == "test-slug"
    assert results[0].distance == 0.123
    assert results[1].source == "audit"
    mock_db_session.execute.assert_called_once()
    # A simple check to ensure UNION ALL is likely in the query
    assert "UNION ALL" in str(mock_db_session.execute.call_args[0][0])


@pytest.mark.asyncio
async def test_search_db_unavailable(mock_db_session, mock_embedding_service):
    """Test that search returns an empty list if the DB raises an exception."""
    mock_db_session.execute.side_effect = Exception("DB connection failed")

    index = RAGIndex(db=mock_db_session)
    results = await index.search("test query")

    assert results == []


def test_to_context_block_format():
    """Test the formatting of the context block."""
    results = [
        RAGResult(
            source="kb",
            ref="slug-1",
            chunk_text="KB content.",
            distance=0.1,
            metadata={"title": "KB Title", "severity": "critical"},
        ),
        RAGResult(
            source="audit",
            ref="mission-456",
            chunk_text="Audit content.",
            distance=0.2,
            metadata={},
        ),
    ]
    # A dummy index is needed to call the method
    index = RAGIndex(db=unittest.mock.MagicMock())
    context_block = index.to_context_block(results)

    assert "Knowledge Base — 2 résultat(s) sémantique(s)" in context_block
    assert "### KB: KB Title [critical]" in context_block
    assert "Slug: slug-1 · Distance: 0.100" in context_block
    assert "KB content." in context_block
    assert "### Audit passé: mission-456" in context_block
    assert "Distance: 0.200" in context_block
    assert "Audit content." in context_block


def test_to_context_block_empty():
    """Test that an empty context block is returned for no results."""
    index = RAGIndex(db=unittest.mock.MagicMock())
    context_block = index.to_context_block([])
    assert context_block == ""
