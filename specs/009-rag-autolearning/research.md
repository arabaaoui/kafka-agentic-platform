# Research & Brainstorming: RAG Semantic Search & Auto-Learning

**Spec**: [spec.md](./spec.md)
**Created**: 2026-05-19
**Type**: Archived brainstorming — decisions, trade-offs, pedagogical notes

---

## 1. Token Overlap vs Semantic Search — Why Make the Switch?

### How the current search works (token overlap / BM25-like)

`KBIndex.search()` in `core/mem0_bridge.py` tokenises the query and scores each KB card by counting how many query tokens appear in the card's fields (tags × 3 weight, title × 2, root_cause × 1, symptoms × 1). This is fast, requires no model, and works well when the vocabulary is stable and shared between queries and documents.

**The problem on incident data**: operators and agents describe the same incident differently depending on context.

| Query | Matching card | Overlap? |
|-------|---------------|---------|
| "broker crash" | "pod CrashLoopBackOff kafka-broker-0" | ❌ zero tokens in common |
| "lag consommateur élevé" | "consumer group lag spike [English card]" | ❌ language mismatch |
| "stockage plein" | "PVC saturation kafka-data-0" | ❌ different vocabulary |
| "PVC saturation" | "PVC saturation kafka-data-0" | ✅ exact match |

The system works when the vocabulary is identical. It fails silently when it is not — it returns no results, agents get no KB context, and they start from scratch on known problems.

### How semantic search works (embeddings + cosine distance)

A text embedding model converts any sentence into a dense vector (here: 384 floating-point numbers). Texts that mean the same thing produce vectors that are close in cosine space, even if they share no words.

```
embed("broker crash")         → [0.12, -0.45, 0.88, ...]  (384 dims)
embed("pod CrashLoopBackOff") → [0.13, -0.44, 0.87, ...]  (very close!)
cosine_distance = 1 - dot_product ≈ 0.03  ← near-zero = near-identical meaning
```

pgvector stores these vectors in Postgres and answers "find the N vectors closest to this query vector" efficiently using an HNSW index (no full-table scan).

### The embedding model is NOT a language model

A common confusion: the embedding model (`intfloat/multilingual-e5-small`) is a separate, much smaller model (470 MB) that does one thing — text → vector. It does not generate text, it does not "understand" instructions, and it is not the same LLM used by the agents for investigation. It runs offline, is loaded once per platform process (singleton), and responds in milliseconds for a single sentence.

The platform LLM (Gemini/Claude) is used for reasoning and report generation. The embedding model is used for indexing and retrieval. They operate independently.

---

## 2. Why Markdown Files Are Kept as Source of Truth

Initial question: should agent outputs, audits, and KB cards be stored only in DB, replacing the Markdown files?

**Decision: keep Markdown, add DB as indexed view.**

Reasons:
1. **Debuggability**: a human on-call can read `audits/MISSION_ID/audit.md` directly without a DB query. Markdown is universally readable.
2. **Agent exchange format**: agents produce and consume Markdown naturally. Replacing it with DB reads would require changing every agent's output handling.
3. **Rejouabilité / audit trail**: Enterprise compliance and incident review require files that can be versioned, inspected, and attached to Jira. DB rows are harder to share.
4. **IA pattern**: the dominant pattern in agentic systems is to use documents (Markdown, PDFs, text) as the "memory substrate" and vector stores as the "retrieval index" over those documents. The DB is a derived index, not the source.
5. **Practical**: the existing code already reads and writes Markdown. Migrating to DB-only would require rewriting every agent.

The DB adds a searchable index on top of the Markdown without replacing it. A `scripts/reindex_all.py` can always rebuild the index from the files.

---

## 3. Embedding Model Choice: multilingual-e5-small

### Why not use the platform LLM for embeddings?

LLMs (Claude, Gemini) can compute embeddings via API, but:
- **Cost**: every mission start would make an API call to embed the subject string
- **Latency**: API round-trip adds 200–500ms per search
- **Offline requirement**: the platform must work without internet access (production Enterprise constraint)

### Why multilingual-e5-small specifically?

| Criterion | multilingual-e5-small |
|-----------|----------------------|
| Size | 470 MB (fits comfortably in a container with 2GB+ RAM) |
| Dimensions | 384 (sufficient for semantic matching; pgvector HNSW works well at this size) |
| Languages | 100+ languages, FR and EN validated |
| Offline | yes — downloaded once, served from local volume |
| Licence | MIT |
| Inference speed | ~5ms per sentence on CPU (singleton loaded once) |

Alternatives considered:
- `all-MiniLM-L6-v2`: English only → rejected (agents produce French text)
- `multilingual-e5-large`: 1.1 GB, 768 dims → overkill for ≤10k chunks
- OpenAI `text-embedding-3-small`: API-only, paid → rejected (offline constraint)
- `paraphrase-multilingual-mpnet-base-v2`: 970 MB → too heavy

### e5 instruction prefixes (query: / passage:)

`multilingual-e5-small` is an instruction-tuned model that requires a short prefix to distinguish
query vectors from passage vectors during encoding:
- **Search path**: `"query: <text>"` — produces query-side vectors optimised for retrieval.
- **Indexing path**: `"passage: <text>"` — produces document-side vectors optimised for ranking.

Without these prefixes the vectors are still semantically valid (the model falls back to a symmetric
mode) but the query↔passage asymmetry that e5 was trained for is not exploited, leading to
degraded ranking. This is implemented in `core/embeddings.py` via `embed_query()` / `embed_passage()`
which wrap the low-level `embed_text()` / `embed_batch()` API.

### Cold start and memory

The model is a singleton loaded on first call and kept in memory for the lifetime of the FastAPI process. On a keep-alive deployment (GKE, Docker), this means one load at startup (3–8s on CPU) and zero overhead after. On serverless/ephemeral deployments, cold start would add latency — not applicable here.

---

## 4. Why pgvector Over SQLite + sqlite-vec

During brainstorming, SQLite + sqlite-vec was considered as a simpler alternative.

| Criterion | pgvector (Postgres) | sqlite-vec |
|-----------|--------------------|----|
| Already deployed | ✅ (`core/db.py` uses asyncpg) | ❌ new dependency |
| Concurrent writes | ✅ MVCC | ⚠️ WAL mode required, single-writer |
| HNSW index | ✅ native | ✅ (recent versions) |
| Backup/restore | ✅ Postgres tooling (pg_dump, GCP managed) | ⚠️ file-level only |
| JSONB metadata filters | ✅ GIN index | ❌ JSON stored as text |
| GKE / production fit | ✅ Cloud SQL for Postgres | ⚠️ requires persistent volume per pod |
| Code change | minimal (Alembic migration) | new SQLite client, new connection management |

Decision: pgvector. The codebase already depends on Postgres (JSONB columns in `core/models.py`, `asyncpg` driver). Adding a pgvector extension is a one-line migration. There is no operational value in introducing SQLite as a second database.

---

## 5. Why 2 Tables (kb_chunks vs audit_chunks)

A single table with a `source` discriminator column was considered. The 2-table design was kept because:

1. **Different search weighting**: KB cards are curated patterns (high-quality, hand-validated by LLM post-mortem). Audits are raw investigation history (useful context, lower precision). A UNION ALL with separate per-table `LIMIT K` ensures both sources contribute to results, even if one dominates by distance.
2. **Different metadata schemas**: KB chunks carry slug, severity, tags. Audit chunks carry mission_id, env, cluster, type. A shared JSONB `metadata` column could handle this, but separate tables make schema evolution cleaner.
3. **Separate cleanup policies**: future v2 may age out audit chunks older than 90 days without touching KB chunks. Separate tables make this a one-line DELETE.

The UNION ALL query is simple and reads cleanly. A discriminator column on a single table would require more complex WHERE conditions for the per-source limits.

---

## 6. Auto-Trigger of finalize() — Closing the Loop

### Current state (v0.5)

`finalize()` is opt-in: `POST /v1/missions/{id}/finalize`. An on-call engineer must remember to click "Capitalise" in the UI. In practice, this is often skipped, so the KB never grows from real incidents.

### New state (v1.0)

`finalize()` is called automatically by the orchestrator after `evidence_consolidator` completes (mission closes). The `POST /v1/missions/{id}/finalize` endpoint remains for manual re-triggers (idempotent: re-running refreshes the index without creating duplicates).

KB card creation remains conditional: the LLM decides during finalize whether the pattern is novel enough to warrant a card. No card for PARTIAL missions. Audit indexing happens always (even PARTIAL audits contain diagnostic value for future missions).

### Fire-and-forget consideration

Indexing (embedding + DB insert) takes ~50ms for a typical audit. Since finalize already takes several seconds (LLM calls for BRIEF.md + card extraction), the indexing overhead is negligible and can run inline (not fire-and-forget). If the platform moves to async finalize (background task), the indexing moves with it naturally.

---

## 7. Chunking Strategy

Why chunk Markdown at all? A full KB card or audit can be 2,000–5,000 tokens. Embedding a 5,000-token text loses granularity — the vector averages the entire document and becomes less discriminating for specific sub-topics.

Chunking strategy chosen:
1. Split on `##` H2 section boundaries — each section is a thematic unit
2. For sections longer than ~500 tokens: sliding window with 50-token overlap
3. Preserve section title in `metadata.section_title` for display in the KB context block
4. Embed each chunk independently

This means a search for "PVC compaction starvation" can match the "Disk Full Emergency Protocol" section of a card even if the card's title is "Kafka Broker Storage Saturation" — the relevant section gets its own embedding.

---

## 8. Quality Comparison: Token Overlap vs RAG — État post-implémentation

> **Validation d'intégration E2E** : requiert un stack PostgreSQL+pgvector opérationnel.
> Les tests unitaires (`tests/unit/test_mem0_bridge_rag.py`, `test_rag_ingest.py`) valident la
> logique de chunking, d'embedding (mocks), et de formatage. Les tests d'intégration sont dans
> `tests/integration/test_rag_search.py` (requiert `DB_URL` avec pgvector).

### Comparaison théorique basée sur les cas de test unitaires

| Query | `KBIndexLegacy` (token-overlap) | `RAGIndex` (sémantique) | Avantage RAG |
|-------|----------------------------------|------------------------|--------------|
| "slow produce upstream" | ❌ 0 tokens communs avec les cartes EN/FR existantes | ✅ cosine proche de "producer latency" | +++ |
| "lag consommateur élevé" | ❌ mismatch langue — cartes EN uniquement | ✅ multilingual-e5 → vecteur bilingue | +++ |
| "broker crash stockage" | ⚠️ match partiel si "crash" dans symptoms | ✅ match sémantique sur "CrashLoopBackOff" | ++ |
| "pod restart kafka-0" | ⚠️ "pod" et "kafka" matchent plusieurs cartes sans discriminer | ✅ cosine discrimine sur le contexte restart | + |
| "MM2 heartbeat manquant" | ✅ "heartbeat" ∈ tags de mm2-heartbeat-cascade-loops | ✅ également un bon match | = |

### Résultats des tests automatisés (2026-05-20)

| Fichier de test | Résultat | Couverture |
|-----------------|----------|-----------|
| `test_mem0_bridge_rag.py` | ✅ 4/4 pass | search, format_context, fallback DB error, empty query |
| `test_rag_ingest.py` | ✅ 4/4 pass | chunk_markdown overlap, ingest_kb_card (3 chunks), ingest_audit, file manquant |
| `test_embeddings.py` | ✅ 7/7 pass | singleton, dimensions, batch, normalisation, lazy loading, préfixes e5 query/passage |
| `tests/integration/test_rag_search.py` | ⏳ requiert pgvector DB | search bilingue, précision sémantique |

### Validation E2E manuelle (à effectuer avec stack complet)

```bash
# 1. Lancer stack local
docker-compose up -d postgres  # avec pgvector

# 2. Migrer DB
uv run alembic upgrade head

# 3. Bootstrap index
uv run python scripts/reindex_all.py

# 4. Tester via API
curl -X POST http://localhost:8000/api/v1/missions \
  -H "Content-Type: application/json" \
  -d '{"subject": "lag-consommateur-eleve", "env": "preprod", ...}'
# Vérifier que l'agent reçoit des chunks RAG pertinents dans son contexte
```

---

## 9. Décision d'architecture : Injection pré-prompt vs post-outil (Session 2026-05-22)

### Contexte

L'implémentation initiale (T007) injectait le bloc KB via `Mem0MemoryPlugin.after_tool_callback` — c'est-à-dire **après** le premier appel d'outil. L'agent choisissait donc son premier outil sans connaissance des apprentissages passés. Ce comportement contredisait l'intention du spec (FR qui décrit l'injection « at mission start »).

### Comparaison des approches

| Critère | Post-outil (plugin) | Pré-prompt (BaseAgent.run) |
|---------|---------------------|---------------------------|
| Agent voit la méthodologie KB | Après le 1er outil | Avant tout outil ✅ |
| Appels d'outils évités par KB | Non (déjà commis) | Potentiellement oui ✅ |
| Coût RAG (nb de recherches) | 1 par mission | 1 par mission (neutre) |
| Respect FR-010 / SC-007 (format) | ✅ | ✅ |
| Cohérence avec spec intent | ❌ (dérive) | ✅ (réalignement) |
| Testabilité du helper | Difficile (plugin + ADK) | Facile (helper isolé) ✅ |

### Décision

Injection **pré-prompt** adoptée (FR-011, FR-012, SC-009). `Mem0MemoryPlugin` **supprimé entièrement** du code (plugin chain réduite à 8 plugins). Le helper `BaseAgent._fetch_kb_context()` réutilise `RAGIndex.search` + `to_context_block` et est testable sans lancer le Runner ADK.

**Portée** : `kafka_strimzi_expert`, `k8s_gcp_sre`, `prom_alerts_triage`, `evidence_consolidator`. Les agents générateurs (`post_mortem_analyst`, `intake`) exclus — ils utilisent `run()` pour des tâches de génération sans décision d'outils d'investigation.

### Rationale clé

Les cartes KB encodent la **méthodologie de diagnostic** (arbre de décision, heuristiques, pièges) — ex. « les métriques Kafka semblaient saines car le plan de contrôle K8s était dégradé ». Fournir ces informations **avant** la décision d'outils évite des appels coûteux vers des mauvaises directions. Coût identique (1 recherche RAG), bénéfice = moins de gaspillage d'appels d'outils.
