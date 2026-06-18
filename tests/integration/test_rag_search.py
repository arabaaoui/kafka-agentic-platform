"""Integration tests for the RAG search pipeline.

These tests require a live PostgreSQL database with the pgvector extension
enabled. They are slower and should be run separately from unit tests.

The tests will:
1. Set up a real database session.
2. Ingest sample documents (KB cards, audits).
3. Perform a semantic search.
4. Verify that the correct documents are returned.
"""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from core.mem0_bridge import RAGIndex
from core.rag_ingest import ingest_audit, ingest_kb_card

# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
async def test_db_session():
    """
    Provides a real database session for the duration of the module's tests.
    Assumes the test database is already created and the extension is available.
    """
    # For a real project, you'd use a dedicated test DB and run migrations.
    # Here, we'll just use the configured DB and assume the schema is up-to-date.
    async with get_session() as session:
        yield session


@pytest.mark.asyncio
async def test_rag_e2e_search(test_db_session: AsyncSession):
    """
    Tests the full RAG pipeline: ingest -> search -> verify.
    """
    # --- Test Data ---
    # Mock file system reads for ingestion
    kb_content_en = """
    ## Symptoms
    - High producer latency on p95
    - Broker CPU is high
    """
    kb_content_fr = """
    ## Symptômes
    - Le lag consommateur est élevé
    - Le groupe de consommateurs est instable
    """
    audit_content = """
    ## Findings
    The root cause was a saturated PVC on `kafka-data-0`.
    """

    # --- Ingestion ---
    # We need to mock the file reads for the ingestion functions
    with unittest.mock.patch("pathlib.Path.exists", return_value=True):
        with unittest.mock.patch(
            "pathlib.Path.read_text",
            side_effect=[kb_content_en, kb_content_fr, audit_content],
        ):
            await ingest_kb_card("latency-card-en", test_db_session)
            await ingest_kb_card("lag-card-fr", test_db_session)
            await ingest_audit("pvc-audit", test_db_session)

    # --- Search ---
    index = RAGIndex(db=test_db_session, limit=1)

    # 1. Test English query matching English document
    results_en = await index.search("producer is slow")
    assert len(results_en) == 1
    assert results_en[0].source == "kb"
    assert results_en[0].ref == "latency-card-en"

    # 2. Test French query matching French document
    results_fr = await index.search("problème de consommation")
    assert len(results_fr) == 1
    assert results_fr[0].source == "kb"
    assert results_fr[0].ref == "lag-card-fr"

    # 3. Test bilingual search: English query matching French document
    results_bilingual_1 = await index.search("consumer lag is high")
    assert len(results_bilingual_1) == 1
    assert results_bilingual_1[0].source == "kb"
    assert results_bilingual_1[0].ref == "lag-card-fr"

    # 4. Test bilingual search: French query matching English document
    results_bilingual_2 = await index.search("latence de production")
    assert len(results_bilingual_2) == 1
    assert results_bilingual_2[0].source == "kb"
    assert results_bilingual_2[0].ref == "latency-card-en"

    # 5. Test query matching audit content
    results_audit = await index.search("disk is full on broker")
    assert len(results_audit) == 1
    assert results_audit[0].source == "audit"
    assert results_audit[0].ref == "pvc-audit"
