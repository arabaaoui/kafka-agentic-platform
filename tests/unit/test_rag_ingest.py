"""Unit tests for the RAG ingestion service."""

import unittest.mock
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core import rag_ingest

# Sample Markdown content for testing
SAMPLE_KB_MD = """
# Kafka Producer Latency

Some introductory text.

## Symptoms

- High produce latency on p95
- Increased broker CPU

## Analysis

The broker CPU was high due to a misconfiguration in the log flush settings.
This is a very long section that will definitely need to be chunked. Let's add more text to make sure it exceeds the threshold. The quick brown fox jumps over the lazy dog. This sentence is repeated multiple times to increase the character count. The quick brown fox jumps over the lazy dog. The quick brown fox jumps over the lazy dog. The quick brown fox jumps over the lazy dog. The quick brown fox jumps over the lazy dog. The quick brown fox jumps over the lazy dog. The quick brown fox jumps over thelazy dog. The quick brown fox jumps over the lazy dog. The quick brown fox jumps over the lazy dog.
"""

SAMPLE_AUDIT_MD = """
# Mission audit-123

This is an audit file.

## Findings

The root cause was a saturated PVC on `kafka-data-0`.
"""


@pytest.fixture
def mock_db_session():
    """Fixture for a mocked AsyncSession."""
    session = unittest.mock.AsyncMock(spec=AsyncSession)
    session.execute.return_value = unittest.mock.MagicMock()
    return session


@pytest.fixture
def mock_embedding_service():
    """Fixture to mock the embedding service."""
    with unittest.mock.patch("core.rag_ingest.embedding_service") as mock_service:
        def mock_embed_passage(texts):
            return [[0.1] * 384 for _ in texts]

        mock_service.embed_passage.side_effect = mock_embed_passage
        yield mock_service


def test_chunk_markdown():
    """Test the markdown chunking logic."""
    chunks = rag_ingest._chunk_markdown(SAMPLE_KB_MD, max_tokens=100, overlap_tokens=10)
    # Expect 3 chunks: intro, symptoms, and 2 for the long analysis section
    assert len(chunks) == 4
    assert chunks[0][0] is None  # Intro before first H2
    assert chunks[1][0] == "Symptoms"
    assert chunks[2][0] == "Analysis"
    assert chunks[3][0] == "Analysis"
    assert chunks[1][1].startswith("## Symptoms")
    assert "log flush settings" in chunks[2][1]
    # Check for overlap: the last overlap_chars*4=40 chars of chunk2 appear at the start of chunk3
    overlap_chars = 10 * 4
    assert chunks[2][1][-overlap_chars:] in chunks[3][1]


@pytest.mark.asyncio
async def test_ingest_kb_card(mock_db_session, mock_embedding_service):
    """Test the KB card ingestion function."""
    with unittest.mock.patch("pathlib.Path.exists", return_value=True):
        with unittest.mock.patch(
            "pathlib.Path.read_text", return_value=SAMPLE_KB_MD
        ) as mock_read:
            count = await rag_ingest.ingest_kb_card("test-slug", mock_db_session)

    mock_read.assert_called_once()
    # Check that delete was called for idempotency
    assert "DELETE" in str(mock_db_session.execute.call_args[0][0])
    # Check that chunks were added
    mock_db_session.add_all.assert_called_once()
    assert count == 3  # ingest_kb_card uses default max_tokens=512, fitting this sample in 3 chunks
    mock_embedding_service.embed_passage.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_audit(mock_db_session, mock_embedding_service):
    """Test the mission audit ingestion function."""
    with unittest.mock.patch("pathlib.Path.exists", return_value=True):
        with unittest.mock.patch(
            "pathlib.Path.read_text", return_value=SAMPLE_AUDIT_MD
        ) as mock_read:
            count = await rag_ingest.ingest_audit("audit-123", mock_db_session)

    mock_read.assert_called_once()
    assert "DELETE" in str(mock_db_session.execute.call_args[0][0])
    mock_db_session.add_all.assert_called_once()
    assert count == 2  # Intro + Findings
    mock_embedding_service.embed_passage.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_missing_file(mock_db_session):
    """Test that ingestion returns 0 if the file does not exist."""
    with unittest.mock.patch("pathlib.Path.exists", return_value=False):
        count = await rag_ingest.ingest_kb_card("not-exist", mock_db_session)
    assert count == 0
    mock_db_session.execute.assert_not_called()
