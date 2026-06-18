# Implementation Plan: RAG Semantic Search & Agent Auto-Learning Loop

**Spec**: [spec.md](./spec.md)
**Created**: 2026-05-20

---

## 1. Technology Stack

This feature will be implemented within the existing Python backend of the `kafka-agentic-platform`. No new services are introduced.

- **Language**: Python 3.11+
- **Framework**: FastAPI (existing)
- **Database**: PostgreSQL (existing)
- **Vector Storage**: `pgvector` extension for PostgreSQL.
- **Embedding Model**: `intfloat/multilingual-e5-small` (local, served by `sentence-transformers`).
- **Dependencies to add**:
    - `pgvector`: For vector similarity search in Postgres.
    - `sentence-transformers`: To load and run the embedding model.
    - `torch`: CPU-only version, as a dependency for `sentence-transformers`.

## 2. Architecture

The implementation will extend the existing architecture by introducing a semantic search capability that replaces the current keyword-based search. The core components are:

1.  **Database Schema**:
    - An **Alembic migration** will be created to add the `vector` extension to PostgreSQL.
    - Two new tables, `kb_chunks` and `audit_chunks`, will be created to store text chunks and their corresponding 384-dimension embeddings.
    - HNSW indexes will be used on the embedding columns for efficient similarity search.

2.  **SQLAlchemy Models**:
    - New models `KBChunk` and `AuditChunk` will be added to `core/models.py` to represent the new tables, using the `Vector` type from the `pgvector` library.

3.  **Embedding Service (`core/embeddings.py`)**:
    - A new singleton service will manage the `SentenceTransformer` model.
    - It will be loaded lazily on its first use to avoid slowing down application startup.
    - It will expose functions to embed single texts or batches of text. The model name and path will be configurable via environment variables.

4.  **Ingestion Service (`core/rag_ingest.py`)**:
    - This service will be responsible for processing Markdown files (`KB cards` and `mission audits`), chunking them according to the defined strategy (512 tokens, 10% overlap), generating embeddings using the Embedding Service, and storing the results in the database.
    - Ingestion will be idempotent (deleting old chunks before inserting new ones) to handle re-indexing.

5.  **Search Service (`core/mem0_bridge.py`)**:
    - The existing `KBIndex` will be replaced by a new `RAGIndex` class.
    - This class will perform semantic search by converting a query string into an embedding and using it to find the most similar chunks in the `kb_chunks` and `audit_chunks` tables via a `UNION ALL` query.
    - It will be responsible for formatting the search results into the context block format that investigation agents expect, ensuring backward compatibility.
    - It includes a graceful fallback mechanism to return an empty context block if the database or search fails, preventing mission failures.

6.  **Auto-learning Loop Integration**:
    - The `post_mortem_analyst` agent will be updated to call the Ingestion Service after a mission is finalized, ensuring new audits and any generated KB cards are immediately indexed.
    - The main pipeline orchestrator will be modified to automatically trigger this finalization step for every closed mission, thus closing the learning loop.

7.  **RAG Pre-injection into Agent Prompts** *(Session 2026-05-22 — realignment with spec intent)*:
    - `BaseAgent.run()` performs a RAG search (reusing `RAGIndex.search` + `to_context_block`) and **prefixes the KB context block to the user task prompt** before the `LlmAgent` is created, for all agents in `_RAG_PREINJECT_AGENTS` = `{kafka_strimzi_expert, k8s_gcp_sre, prom_alerts_triage, evidence_consolidator}`.
    - A helper `BaseAgent._fetch_kb_context(mission_ctx, db)` encapsulates the search and is independently testable (no ADK Runner spin-up).
    - The DB session is sourced from `db_conn` (investigators) or `mission_ctx.db_session` (consolidator via `model_copy`). If no session is available, injection is silently skipped (FR-006 / FR-012).
    - `Mem0MemoryPlugin` is **removed entirely** from `core/plugins.py` and `agents/pipeline/orchestrator.py`. The plugin chain now has 8 plugins. The `RAGIndex` import in `core/plugins.py` is removed.

8.  **Bootstrap Script (`scripts/reindex_all.py`)**:
    - A standalone script will be created to perform a one-time indexing of all existing KB cards and mission audits, allowing the feature to be deployed with a pre-populated search index.

## 3. File Structure

The following files will be **created**:

- `alembic/versions/<rev>_add_pgvector_rag.py`: The database migration script.
- `core/embeddings.py`: The embedding model service.
- `core/rag_ingest.py`: The data ingestion and chunking service.
- `scripts/reindex_all.py`: The one-shot historical re-indexing script.
- `tests/unit/test_embeddings.py`: Unit tests for the embedding service.
- `tests/unit/test_rag_ingest.py`: Unit tests for the ingestion service.
- `tests/unit/test_mem0_bridge_rag.py`: Unit tests for the new RAG search bridge.
- `tests/integration/test_rag_search.py`: Integration tests requiring a live `pgvector` database.

The following files will be **modified**:

- `pyproject.toml`: To add new dependencies.
- `core/models.py`: To add new SQLAlchemy models.
- `core/mem0_bridge.py`: To replace the old index with the new `RAGIndex`.
- `core/plugins.py`: ~~To inject the `RAGIndex` into the agent context~~ → `Mem0MemoryPlugin` removed; injection is in `BaseAgent.run()`.
- `agents/base.py`: Pre-injection helper `_fetch_kb_context` + `_RAG_PREINJECT_AGENTS` gating in `run()`.
- `agents/evidence_consolidator/agent.py`: Pass `db_session` via `model_copy` for RAG pre-injection.
- `agents/post_mortem_analyst/agent.py`: To trigger indexing after finalization.
- `.env.example`: To add new environment variables for configuration.
- Deployment documentation (e.g., in `docs/`): To add notes on deploying the embedding model and `pgvector`.
