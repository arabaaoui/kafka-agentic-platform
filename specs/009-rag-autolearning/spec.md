# Feature Specification: RAG Semantic Search & Agent Auto-Learning Loop

**Feature Branch**: `004-rag-autolearning`
**Created**: 2026-05-19
**Status**: Approved
**Scope**: v1.0 — closes the KB auto-learning loop with semantic retrieval

---

## Context

Investigation agents currently receive a Knowledge Base context block at the start of each mission, injected by a keyword-overlap search over KB cards. This search does not understand meaning — "broker crash" does not match "pod CrashLoopBackOff" despite describing the same event. Additionally, past completed missions (audits) are never reused as context, so the system never learns from its own history. The KB capitalisation step is also opt-in, which means the loop is never automatically closed.

This feature replaces keyword search with semantic (embedding-based) search, extends the scope to include past mission audits alongside KB cards, and automatically triggers the capitalisation step at the end of every mission.

---

## Clarifications

### Session 2026-05-20
- Q: To ensure we can effectively monitor the health and performance of the new RAG system, which set of observability signals should be prioritized for implementation? → A: Core Metrics: `Search Latency (P95/avg)`, `Indexing Throughput (docs/sec)`, `Search Error Rate (%)`, and `Average Relevance Score`.
- Q: The time taken to perform the semantic search directly impacts how quickly an investigation mission can start. What is the maximum acceptable P99 latency for this search operation? → A: `< 500ms`.
- Q: Regarding the Domain & Data Model, what is the preferred chunking strategy for documents (max tokens, overlap) and which Postgres vector extension (e.g., `pgvector`) should be used for the Semantic Index? → A: Chunking Strategy: Max 512 tokens, 10% overlap. Postgres Vector Extension: `pgvector`.
- Q: What is the initial scalability requirement for the search and indexing service? → A: Single instance, manual scaling if needed.

### Session 2026-05-22
- Decision: KB context injection timing changed from **post-first-tool-call** (via `Mem0MemoryPlugin.after_tool_callback`) to **pre-prompt** (prefixed to the agent's task message in `BaseAgent.run()` before any tool-selection step). The initial `Mem0MemoryPlugin` implementation drifted from the spec's stated intent ("at mission start"); this decision realigns implementation with spec.
- Rationale: KB cards encode diagnostic methodology — decision trees, triggering heuristics, key signals, and pitfalls to avoid (e.g. "Kafka appeared healthy but metrics were stale due to K8s control-plane degradation"). Providing this context *before* the agent selects tools lets it exploit past learnings when choosing its investigation path, avoiding wasted tool calls.
- Scope: pre-injection applies to the 3 investigator agents (`kafka_strimzi_expert`, `k8s_gcp_sre`, `prom_alerts_triage`) and `evidence_consolidator`. Other agents (`post_mortem_analyst`, `intake`) are excluded — they use `run()` for generation tasks, not tool-driven investigation.
- Implementation: `BaseAgent._fetch_kb_context()` helper (reuses `RAGIndex.search` + `to_context_block`); `Mem0MemoryPlugin` removed from the codebase — the plugin chain now has 8 plugins (GuardrailsPlugin → ResiliencePlugin → OTelMetricsPlugin → AuditPlugin → ActivityPlugin → MissionIsolationPlugin → AutonomyPlugin → ErrorHandlerPlugin).
- FR-010 / SC-007 remain valid: the context block **format** is unchanged; only the injection timing changes.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Agents find relevant past knowledge even with different phrasing (Priority: P1)

An on-call engineer triggers a mission for a Kafka producer latency spike. The investigation agent, before calling any diagnostic tool, receives in its context a KB card about "producer P95 latency regression" and a chunk from a mission closed three weeks ago that described the same pattern — even though the current mission description uses different words ("slow produce", "lag upstream").

**Why this priority**: This is the core value. Without semantic matching, agents repeat the same diagnostic steps even when the platform has already solved the same problem, wasting investigation time and missing known root causes.

**Independent Test**: Ingest one KB card about "broker PVC saturation" and one audit about "disk full on kafka-data-0". Start a mission with subject "storage full on broker". Verify the KB context block injected at mission start contains at least one of the two ingested documents.

**Acceptance Scenarios**:

1. **Given** a KB card about "Kafka producer P95 latency spike" and a completed audit describing "slow produce upstream", **When** a new mission with subject "producer latency degraded" starts, **Then** the KB context block injected into the agent contains at least one relevant result with a similarity score surfaced to the reader.
2. **Given** a query in French ("lag consommateur élevé"), **When** the semantic search runs, **Then** it matches KB cards and audits written in both French and English, returning results ranked by semantic proximity.
3. **Given** the semantic search service is unavailable, **When** a mission starts, **Then** the mission proceeds without a KB context block — no error is raised and the investigation continues normally.

---

### User Story 2 — Past mission audits are automatically available to future agents (Priority: P1)

After a mission closes, its consolidated audit is automatically indexed. A mission that starts the next day on a similar topic receives a context block that includes a summary chunk from the previous audit, labelled "Audit passé".

**Why this priority**: The most valuable knowledge the system can provide is its own history. Closing this loop automatically (not opt-in) removes the dependency on a human triggering capitalisation.

**Independent Test**: Complete one mission (audit.md written). Start a second mission on the same topic. Verify the second mission's KB context block contains a chunk sourced from the first mission's audit.

**Acceptance Scenarios**:

1. **Given** a mission that closes with a consolidated audit, **When** the mission finalization runs (automatically), **Then** the audit is indexed and retrievable by future semantic searches within 60 seconds.
2. **Given** finalization runs twice for the same mission (re-trigger), **When** the second run completes, **Then** the indexed content is refreshed without creating duplicates.
3. **Given** a mission closes with status PARTIAL (insufficient evidence), **When** finalization runs, **Then** the audit is still indexed (providing partial evidence for future missions), but no KB card is created.

---

### User Story 3 — New KB cards are semantically searchable immediately after creation (Priority: P2)

After a mission creates a new KB card (automatic, when the LLM estimates the pattern is novel and worth capitalising), the next mission that starts on a matching topic receives that card in its context — no restart required.

**Why this priority**: The KB card represents curated, validated knowledge distilled from an incident. It must be available immediately to be useful on the next alert.

**Independent Test**: Run finalization on a completed mission. Verify a new KB card is created. Start a new mission on the same topic. Verify the KB context block contains the new card.

**Acceptance Scenarios**:

1. **Given** finalization creates a new KB card with slug `kafka-producer-p95-spike`, **When** a new mission with a semantically similar subject starts, **Then** the KB context block includes a chunk from `kafka-producer-p95-spike` with its severity and slug visible.
2. **Given** finalization determines the mission does not warrant a new card (pattern already covered or evidence insufficient), **When** the LLM outputs a non-parseable JSON or empty slug, **Then** no card is created and the audit is still indexed.

---

### User Story 4 — All historical KB cards and audits are available on first deployment (Priority: P3)

When the feature is deployed to an environment that already has KB cards and closed mission audits on disk, a one-shot reindex operation makes all existing content available to semantic search without rerunning past missions.

**Why this priority**: Without bootstrapping, the semantic index starts empty on deployment and takes time to accumulate knowledge. Historical data exists and should be exploited immediately.

**Independent Test**: Run the reindex script against a directory containing 17 KB cards and 5 past audits. Verify that all 22 documents are indexed and retrievable.

**Acceptance Scenarios**:

1. **Given** a directory with 17 KB cards and N past audits, **When** the reindex script runs, **Then** it completes without error and logs the count of indexed KB chunks and audit chunks.
2. **Given** the reindex script is run a second time, **When** it completes, **Then** the index contains the same content (no duplicates), matching the idempotent reindex behaviour.

---

### Edge Cases

- What happens when an audit file is empty or malformed? The indexer skips it, logs a warning, and continues with the next document.
- What happens when the embedding model is not available at boot? The platform starts normally; the first search attempt logs an error and returns an empty context block (mission proceeds without KB injection).
- What happens when a KB card is deleted from disk? The corresponding chunks remain in the index until the next explicit reindex or TTL-based cleanup (out of scope for v1.0, documented as known limitation).
- What happens when a mission's subject is very short (1-2 words) or generic? The semantic search still runs; if no result exceeds the minimum relevance threshold, the context block is empty rather than injecting irrelevant content.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST return relevant KB cards and past mission audits for a given investigation subject, ranked by semantic similarity, in a format compatible with the existing KB context block injected into agents.
- **FR-002**: The semantic search MUST support queries written in French and English, and MUST match documents written in either language.
- **FR-003**: The system MUST automatically index the consolidated audit of each mission when the mission finalises, without requiring a manual trigger.
- **FR-004**: When a KB card is created or updated during finalisation, the system MUST index its content so it is retrievable by the next mission that starts.
- **FR-005**: Indexing MUST be idempotent — running it twice for the same mission or KB card MUST NOT create duplicate entries.
- **FR-006**: The system MUST continue operating (missions run, agents investigate) when the semantic index or the embedding service is unavailable, with no KB context injected.
- **FR-007**: A one-shot reindex operation MUST be available to ingest all existing KB cards and past audits without rerunning missions.
- **FR-008**: KB card creation during finalisation MUST remain conditional — the system creates a card only when the LLM estimates the incident pattern is novel and worth capitalising. No card is created for PARTIAL missions or when the LLM output cannot be parsed.
- **FR-009**: The existing `POST /v1/missions/{id}/finalize` endpoint MUST remain available for manual re-triggers; re-triggering MUST refresh the index without creating duplicates.
- **FR-010**: The KB context block format visible to agents MUST remain unchanged — agents do not need to be updated when this feature ships. *(The injection timing changed in Session 2026-05-22 — format unchanged, only when it is injected.)*
- **FR-011**: The KB context block MUST be injected into the agent's input prompt **before the agent's first tool-selection step**, so the agent can exploit past diagnostic methodology and pitfalls when choosing which tools to call.
- **FR-012**: KB context pre-injection applies to the investigator agents (`kafka_strimzi_expert`, `k8s_gcp_sre`, `prom_alerts_triage`) and `evidence_consolidator`. When no relevant knowledge is indexed, injection is silently skipped and the mission proceeds normally (aligns with FR-006).

### Non-Functional Requirements

- **NFR-001 (Observability)**: The system MUST expose core metrics to monitor the health and performance of the semantic search and indexing components. Key metrics include: `Search Latency (P95/avg)`, `Indexing Throughput (docs/sec)`, `Search Error Rate (%)`, and `Average Relevance Score`.
- **NFR-002 (Search Performance)**: The semantic search operation, when injecting context at the start of a mission, MUST have a P99 latency of less than 500ms.

### Key Entities *(include if feature involves data)*

- **KB Chunk**: A segment of a KB card (section or paragraph), stored with its embedding and metadata (slug, severity, tags, section title). Multiple chunks per card.
- **Audit Chunk**: A segment of a consolidated mission audit, stored with its embedding and metadata (mission ID, environment, cluster, subject). Multiple chunks per audit.
- **Semantic Index**: The queryable store of KB chunks and audit chunks, supporting similarity-ranked retrieval by embedding distance.
- **KB Card**: An existing entity — curated incident pattern card written by the LLM post-mortem agent. Its content is the source for KB chunks.
- **Mission Audit**: An existing entity — consolidated investigation report written by the evidence consolidator. Its content is the source for audit chunks.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A semantic search for any subject returns at least one result from the KB or audit index when at least one semantically related document has been indexed — no false negatives on direct semantic matches.
- **SC-002**: A query in French matches a document written in English on the same topic, and vice versa — bilingual retrieval works without translation.
- **SC-003**: The audit of a closed mission is available for retrieval by the next mission within 60 seconds of finalisation completing.
- **SC-004**: When the semantic index is unavailable, missions complete without errors — the KB context block is simply absent, and no exception propagates to the investigation pipeline.
- **SC-005**: The one-shot reindex script processes all existing KB cards and audits without error and reports the count of indexed documents.
- **SC-006**: Running finalisation twice for the same mission results in the same number of indexed chunks as running it once (idempotency).
- **SC-007**: The KB context block format injected into agents is identical to the current format — no agent SKILL.md changes required.
- **SC-008**: The P99 latency for semantic search queries (at mission start) is less than 500ms.
- **SC-009**: On a mission where relevant knowledge has been indexed, the KB context block is present in the agent's input prompt before any tool call is made — zero tool calls happen before the agent has access to past diagnostic methodology.

---

## Assumptions

- The platform uses a Postgres database. No additional storage service is required for the semantic index.
- The embedding model is pre-downloaded and available offline — no external API calls are made at inference time.
- The scope of indexed content is: KB cards (`kb/incidents/*.md`) and consolidated mission audits (`audits/<MISSION_ID>/audit.md`). Raw agent reports and BRIEF.md files are not indexed.
- The existing `finalize()` workflow (BRIEF.md generation + conditional KB card creation) is preserved without functional changes; this feature adds indexing steps at the end of that workflow.
- The auto-trigger of finalisation applies to newly closed missions from this feature's deployment forward. Historical missions require the reindex script.
- Markdown remains the canonical format for KB cards and audits — the semantic index is a queryable view, not a replacement.
- No reranking (cross-encoder) is required at the target document volume (estimated ≤10,000 chunks).
- **Chunking Strategy**: Documents will be chunked with a maximum of 512 tokens and a 10% overlap.
- **Postgres Vector Extension**: The `pgvector` extension will be used for the Semantic Index.
- **Scalability**: The initial deployment will be a single instance, with manual scaling as needed. Rate limiting is deferred.