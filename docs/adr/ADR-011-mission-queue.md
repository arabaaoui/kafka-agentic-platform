# ADR-011 — Mission Queue: Durable Triggers Table vs Kafka Topic

**Status**: Accepted  
**Date**: 2026-06-12  
**Deciders**: Kafka InfraOps team  

---

## Context

The `kafka-agentic-platform` processes investigation missions triggered by Jira issues and Alertmanager alerts. Before this ADR, missions were dispatched via an `asyncio.Queue()` held in the FastAPI process memory. This design had three critical gaps:

1. **Data loss on crash** — any trigger in-flight when the process restarted was silently lost; the `triggers` row existed in DB but no worker would ever pick it up.
2. **No observability** — there was no way to know how deep the queue was, how long triggers waited, or which worker was processing what.
3. **Serialized I/O-bound work** — missions are almost entirely I/O-bound (Gemini LLM calls, kubectl, PromQL). A single worker serialized work that could run concurrently.

The question was: replace `asyncio.Queue` with a **Kafka topic** or with a **PostgreSQL-backed durable queue**?

---

## Decision

Use the existing `triggers` PostgreSQL table as the durable queue, extended with `claimed_at`, `claimed_by`, `attempts`, and `last_error` columns. Workers claim rows atomically via `SELECT FOR UPDATE SKIP LOCKED` (PostgreSQL advisory locking), running N workers concurrently controlled by `WORKER_CONCURRENCY`.

Expose queue health via Prometheus metrics (`/metrics`) and enrich `/healthz` with live queue depth.

---

## Rationale

### Why not Kafka?

The `kafka-agentic-platform` **monitors Kafka clusters**. If the platform itself depends on a Kafka topic for its own mission queue, a Kafka outage simultaneously:

1. Fires Alertmanager alerts → produces investigation triggers.
2. Disables the platform's ability to process those triggers (its queue is down).

This is a **correlated failure anti-pattern**: the system that must respond to Kafka outages is crippled by the same outage. A dedicated control-plane Kafka cluster (separate from monitored infra) would remove this coupling, but none exists today.

### Why PostgreSQL triggers table?

- **Already there**: `triggers` has `UNIQUE(tenant, source, external_id)` for dedup and `matched`/`processed_at` for lifecycle tracking — a natural queue.
- **Atomic claim**: `SELECT FOR UPDATE SKIP LOCKED` provides exactly the same worker-isolation guarantee as a Kafka consumer group, without an extra dependency.
- **At-least-once**: `claimed_at` lease expiry means a crashed worker's row is automatically re-claimed by the next available worker after the lease window.
- **No new infrastructure**: one less moving part to operate, monitor, and secure.

---

## Guarantees Provided

| Property | Mechanism |
|---|---|
| At-least-once delivery | `claimed_at` lease; worker crash → row re-claimed after `LEASE_SECONDS` |
| No duplication (business) | `UNIQUE(tenant, source, external_id)` prevents duplicate trigger rows; `mission_id` uniqueness on the mission table |
| No data loss | Row stays in `triggers` with `processed_at IS NULL` until a worker successfully completes it |
| Crash recovery | Heartbeat task refreshes `claimed_at` every 5 min for long missions; lease is configurable |
| Dead-letter | After `MAX_ATTEMPTS` (default 3), `last_error = 'DEAD:...'` and `processed_at = now()` — row excluded from future claims, visible in DB for manual inspection |

---

## Alternatives Considered

### Option B — Kafka topic + consumer group

**Pros**: standard tooling for lag monitoring (kafka-consumer-groups), horizontal scale across replicas, retention/replay built-in.  
**Cons**: correlated failure risk (platform monitors the same Kafka); requires a dedicated control-plane cluster to be safe; adds operational complexity (topic creation, ACLs, offset management); schema/serialization overhead for what is already a PostgreSQL row.

### Option C — Redis Streams

**Pros**: lower latency than PostgreSQL, built-in consumer groups.  
**Cons**: another stateful dependency to operate; data can be lost without persistence configuration; no ACID; current stack has no Redis.

### Option D — asyncio.Queue (status quo)

**Pros**: zero infrastructure.  
**Cons**: lost on process restart; no observability; single-process only.

---

## Consequences

- **Pool constraint**: each mission uses ~4 DB connections at peak (intake + 3 parallel expert agents). With `pool_size=10, max_overflow=20` (30 total), the safe worker ceiling is `floor(30/4) = 7`. `WORKER_CONCURRENCY > 7` logs a warning.
- **Single-replica only**: `SELECT FOR UPDATE SKIP LOCKED` works correctly across multiple processes connected to the same PostgreSQL instance. Multi-replica FastAPI is therefore already supported by the design — but not deployed today.
- **Lease heartbeat**: missions longer than `LEASE_SECONDS` (default 900s) need the heartbeat coroutine; it refreshes `claimed_at` every 300s.

---

## Migration Criteria for Kafka Topic (Option B)

Revisit this decision if **all** of the following are true:

1. **Concurrency demand** exceeds 50 concurrent missions sustained over time (requires a dedicated control-plane Kafka cluster to avoid correlated failure).
2. **Multi-replica FastAPI** deployment is required AND connection-pool scaling with PgBouncer is insufficient.
3. **A dedicated Kafka cluster** is available and isolated from all monitored infra (control-plane separation).
4. **Cross-process observability** via standard Kafka tooling (lag dashboards, consumer group CLI) is preferred over the current Prometheus `/metrics` endpoint.

### Migration path (when criteria are met)

The `durable_queue.py` module exposes a stable interface (`claim_next`, `mark_processed`, `mark_failed`). A drop-in `kafka_queue.py` implementing the same interface can replace it behind a feature flag without touching `worker.py` or `api/main.py`.
