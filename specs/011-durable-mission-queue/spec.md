# Feature Specification: Durable Mission Queue with Parallel Processing

**Feature Branch**: `011-durable-mission-queue`
**Created**: 2026-06-12
**Status**: Draft
**Input**: User description: "Parallélisation des missions + file de traitement durable et observable (sans Kafka)"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Multi-Worker Parallel Processing (Priority: P1)

As a platform operator, I want multiple missions to be processed concurrently so that the pipeline throughput matches the I/O-bound nature of the workload (LLM calls, kubectl, Prometheus queries) and mission wait times are reduced.

**Why this priority**: Highest immediate impact. Missions are I/O-bound and spend most of their time waiting on external systems. A single worker artificially serializes independent work. This improvement requires minimal code change and zero new infrastructure.

**Independent Test**: Start the platform with `WORKER_CONCURRENCY=3`, submit 3 simultaneous triggers, and verify all 3 pipelines progress concurrently (overlapping timestamps in logs) rather than sequentially.

**Acceptance Scenarios**:

1. **Given** `WORKER_CONCURRENCY=1` (default), **When** the platform starts, **Then** exactly 1 mission worker is running and behavior is identical to the prior implementation.
2. **Given** `WORKER_CONCURRENCY=3`, **When** the platform starts, **Then** 3 concurrent workers are active and the `/healthz` endpoint reports `worker_count: 3`.
3. **Given** 3 triggers arrive simultaneously with `WORKER_CONCURRENCY=3`, **When** workers pick them up, **Then** all 3 pipelines begin processing within 2 seconds of each other (no forced sequencing).
4. **Given** one worker encounters a fatal pipeline error, **When** the exception is caught, **Then** the other 2 workers continue operating unaffected.

---

### User Story 2 — Durable Queue Without Data Loss (Priority: P2)

As a platform operator, I want mission triggers persisted durably so that no trigger is permanently lost when the platform process restarts or crashes, and any trigger that was in-flight during a crash is automatically retried after recovery.

**Why this priority**: Second highest impact. Currently, any trigger in `asyncio.Queue()` at crash time is silently lost. Alertmanager webhooks are fire-and-forget — there is no replay mechanism. This is a data-loss risk in production.

**Independent Test**: Insert a trigger into the database, simulate a worker crash mid-pipeline (kill the process), restart the platform, and verify the trigger is picked up and processed to completion on the second attempt.

**Acceptance Scenarios**:

1. **Given** a matched trigger in the database with `processed_at IS NULL`, **When** the platform starts (fresh or after crash), **Then** the worker claims and processes the trigger within the next poll cycle.
2. **Given** a worker claims a trigger and crashes before completing, **When** the lease period expires (configurable, default 15 minutes), **Then** another worker re-claims the same trigger and processes it.
3. **Given** a trigger is re-claimed after a crash, **When** the pipeline runs again, **Then** the `attempts` counter on the trigger row is incremented and the `claimed_by` field identifies the new worker.
4. **Given** a trigger fails repeatedly and exceeds the maximum retry limit, **When** the last attempt fails, **Then** the trigger is marked as dead (`last_error` set, no further re-claiming) and a dead-letter counter metric is incremented.
5. **Given** two identical triggers are submitted simultaneously (same `tenant`, `source`, `external_id`), **When** the database receives both inserts, **Then** only one row is created (deduplication) and only one pipeline runs.

---

### User Story 3 — Queue Observability and Monitoring (Priority: P3)

As a platform operator, I want real-time visibility into the mission queue so that I can detect backlogs, slow missions, and dead-letter accumulation without manual database queries.

**Why this priority**: Third priority. The durable queue (P2) creates the data; this story exposes it as standard Prometheus metrics that can feed dashboards and alerts.

**Independent Test**: Start the platform, submit a trigger, and verify that `kafkaops_queue_depth` decreases from 1 to 0 on the `/metrics` endpoint after the mission completes. Verify `/healthz` includes `queue_depth` and `oldest_pending_age_seconds` fields.

**Acceptance Scenarios**:

1. **Given** the platform is running, **When** `/metrics` is scraped, **Then** it returns all `kafkaops_*` metrics in Prometheus exposition format.
2. **Given** 5 triggers are pending and 2 are in-flight, **When** `/metrics` is scraped, **Then** `kafkaops_queue_depth=5` and `kafkaops_queue_inflight=2`.
3. **Given** a mission completes successfully, **When** `/metrics` is scraped, **Then** `kafkaops_mission_completed_total{outcome="success"}` is incremented by 1.
4. **Given** a trigger has been waiting for 30 minutes, **When** `/healthz` is called, **Then** `oldest_pending_age_seconds` is at least 1800.
5. **Given** a trigger has been retried 3 times and exhausted max attempts, **When** it is marked dead, **Then** `kafkaops_mission_dead_total` is incremented and no further processing occurs.

---

### User Story 4 — Architectural Decision Record (Priority: P4)

As a future platform contributor, I want a documented ADR explaining why the in-memory queue was replaced with a database-backed queue (and why Kafka was not chosen), with explicit criteria for when a Kafka topic migration would become appropriate.

**Why this priority**: Lowest priority, no runtime behavior. Prevents future contributors from re-questioning the same decision without context.

**Independent Test**: Read `docs/adr/ADR-011-mission-queue.md` and confirm it answers: (1) what problem was solved, (2) what alternatives were considered, (3) why Kafka was rejected, (4) what conditions would trigger a Kafka migration.

**Acceptance Scenarios**:

1. **Given** the ADR is written, **When** a new contributor reads it, **Then** they can identify the 3 technical reasons for the current design choice without reading code.
2. **Given** the ADR is written, **When** the team evaluates scaling beyond 50 concurrent missions, **Then** the document provides ready-to-use migration criteria and a path forward.

---

### Edge Cases

- What happens when the platform starts and there are triggers with `claimed_at` set but `processed_at IS NULL` (orphaned from a previous crash)? → They must be eligible for re-claim after lease expiration.
- What if a very long mission (duration > lease timeout) is still running when the lease expires? → A periodic heartbeat mechanism must refresh `claimed_at` to prevent false re-claims by other workers.
- What if all database connections are consumed by concurrent workers? → `WORKER_CONCURRENCY` must not exceed `floor(pool_max_connections / 4)`. This constraint must be validated at startup with a logged warning if violated.
- What if `/metrics` is scraped very frequently (every 15s)? → The queue depth query must use the partial index on `triggers` to remain fast at scale.
- What if an Alertmanager webhook arrives but the database is temporarily unreachable? → The webhook handler must return HTTP 503 and NOT return HTTP 200 before confirming the trigger was persisted.
- What happens to a dead-letter trigger in the UI? → It remains visible in the triggers table but no pipeline is associated. The metric counter provides operational alerting.

## Requirements *(mandatory)*

### Functional Requirements

**WS-1: Parallel Workers**

- **FR-001**: The platform MUST support configurable worker concurrency via the `WORKER_CONCURRENCY` environment variable (integer ≥ 1, default: 1).
- **FR-002**: Each worker MUST include a unique `worker_id` in all log entries to enable per-worker tracing.
- **FR-003**: The `/healthz` endpoint MUST report the number of active workers.
- **FR-004**: Worker failures MUST be isolated — one worker crashing MUST NOT terminate other workers.

**WS-2: Durable Queue**

- **FR-005**: The `triggers` table MUST be extended with `claimed_at` (timestamp, nullable), `claimed_by` (text, nullable), `attempts` (integer, default 0), and `last_error` (text, nullable) via a backward-compatible additive database migration.
- **FR-006**: Workers MUST claim triggers using a database-level exclusive lock with skip-locked semantics to guarantee at-most-one concurrent owner per trigger row.
- **FR-007**: A trigger MUST be eligible for re-claim if its `claimed_at` is older than the configurable lease duration (default: 900 seconds) and `processed_at` is still NULL.
- **FR-008**: The `attempts` counter MUST be incremented each time a trigger is claimed.
- **FR-009**: Triggers exceeding the maximum attempt count (default: 3) MUST be marked dead and MUST NOT be re-claimed by any worker.
- **FR-010**: Workers MUST use an adaptive poll strategy when no triggers are available (starting at 2 seconds, increasing to a maximum of 30 seconds, resetting on successful claim).
- **FR-011**: Trigger producers (Jira poller, Alertmanager poller, Alertmanager webhook) MUST persist trigger data directly to the database with deduplication semantics, without passing items to an in-memory queue.
- **FR-012**: All references to `asyncio.Queue` for mission dispatch MUST be removed from `api/main.py` after WS-2 is complete.

**WS-3: Observability**

- **FR-013**: The platform MUST expose a `/metrics` endpoint in Prometheus exposition format.
- **FR-014**: The following metrics MUST be available: `kafkaops_queue_depth` (Gauge), `kafkaops_queue_inflight` (Gauge), `kafkaops_queue_claims_total` (Counter labeled by `worker_id`), `kafkaops_mission_completed_total` (Counter labeled by `tenant`, `env`, `outcome`), `kafkaops_mission_duration_seconds` (Histogram), `kafkaops_mission_dead_total` (Counter).
- **FR-015**: The `/healthz` endpoint MUST include `queue_depth` (integer), `worker_count` (integer), and `oldest_pending_age_seconds` (float, null if queue is empty).

**WS-4: Documentation**

- **FR-016**: An ADR MUST be created at `docs/adr/ADR-011-mission-queue.md` documenting the design decision, rationale, rejected alternatives (Kafka, Redis Streams), and explicit criteria for future migration.

### Key Entities

- **Trigger** (existing, extended): An incoming event from Jira, Alertmanager, or webhook. Extended with queue management fields (`claimed_at`, `claimed_by`, `attempts`, `last_error`). Uniquely identified by `(tenant, source, external_id)`.
- **Worker**: A long-running async coroutine that polls for claimable triggers, executes the investigation pipeline, and marks triggers as processed, failed, or dead. Identified by `worker_id = "worker-{pid}-{index}"`.
- **Lease**: A time-bounded ownership of a trigger row by one worker. Expires after a configurable duration. Refreshed periodically by a heartbeat task for long-running missions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With `WORKER_CONCURRENCY=3` and 3 simultaneous triggers, all 3 pipelines begin execution within 2 seconds of each other (not serialized, as in the prior single-worker design).
- **SC-002**: Zero triggers are permanently lost after a process restart — all triggers with `processed_at IS NULL` at restart time are processed to completion on the next run without operator intervention.
- **SC-003**: A trigger that was in-flight during a crash is automatically retried within one lease expiration period (≤ 15 minutes by default) without operator intervention.
- **SC-004**: The `/metrics` endpoint accurately reflects real-time queue state; `kafkaops_queue_depth` updates within 15 seconds of any trigger state change.
- **SC-005**: Queue depth and in-flight count remain accurate under concurrent processing by multiple workers (no over-counting, no under-counting).
- **SC-006**: All 158 existing unit tests continue to pass after full implementation (non-regression).
- **SC-007**: Queue-depth queries on the `triggers` table complete in under 10ms at up to 10,000 trigger rows (verified by the partial index).

## Assumptions

- The platform runs as a single FastAPI replica (one process). Multi-replica support is explicitly out of scope for this feature and documented in ADR-011 as a future migration path.
- The `prometheus_client` Python library is available or can be added to project dependencies without conflict.
- The existing database connection pool (`pool_size=10, max_overflow=20`) supports a maximum of `floor(30 / 4) = 7` concurrent workers. `WORKER_CONCURRENCY` values above 7 must produce a startup warning and be capped or documented as operator responsibility.
- Kafka is explicitly excluded as a queue backend due to the risk of correlated failure: the platform monitors the same Kafka infrastructure it would depend on. ADR-011 documents this decision and the migration path.
- The Alertmanager webhook is fire-and-forget from the sender's perspective. The webhook handler must synchronously confirm database persistence before returning HTTP 200.
- The GKE token-patch block at `orchestrator.py:158-193` MUST NOT be modified as part of this feature.
- Long-running missions (duration > lease timeout) require a periodic heartbeat to refresh `claimed_at` and prevent false re-claims. Heartbeat implementation is in scope for WS-2.
- Dead-letter triggers are retained in the `triggers` table indefinitely for audit purposes. No automated purge policy is implemented in this feature.
- The existing `UNIQUE(tenant, source, external_id)` constraint on `triggers` provides the deduplication guarantee for concurrent or duplicate trigger submissions.
