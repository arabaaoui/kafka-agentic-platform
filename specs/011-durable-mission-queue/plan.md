# Implementation Plan: Durable Mission Queue with Parallel Processing

**Branch**: `011-durable-mission-queue` | **Date**: 2026-06-12 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/011-durable-mission-queue/spec.md`

## Summary

Replace the in-memory `asyncio.Queue()` mission dispatch with a PostgreSQL-backed durable queue (`SELECT FOR UPDATE SKIP LOCKED` on the `triggers` table), launch N parallel async workers via `WORKER_CONCURRENCY` env var, and expose Prometheus metrics for queue depth, in-flight count, and mission lifecycle. Add an ADR documenting the Kafka-exclusion decision and migration criteria.

## Technical Context

**Language/Version**: Python 3.11+ (uv workspace)
**Primary Dependencies**: FastAPI 0.115+, SQLAlchemy 2.0 async, asyncpg 0.29+, prometheus-client 0.20+ (already in pyproject.toml), alembic 1.13+ (migrations in `migrations/versions/`)
**Storage**: PostgreSQL 17 — `triggers` table (existing, additive migration)
**Testing**: pytest + pytest-asyncio, existing test suite in `tests/unit/` (158 tests baseline)
**Target Platform**: Linux container (GKE pod), single FastAPI replica
**Project Type**: web-service (FastAPI + background workers)
**Performance Goals**: queue-depth queries < 10ms at 10k rows (partial index); all N workers claim distinct triggers within 2s of arrival
**Constraints**: DB pool_size=10, max_overflow=20 → WORKER_CONCURRENCY ≤ 7; no Kafka dependency; GKE token-patch block (`orchestrator.py:158-193`) untouched
**Scale/Scope**: 1 replica, WORKER_CONCURRENCY 1–7, expected ~1–20 missions/hour

## Constitution Check

| Principle | Status | Notes |
|---|---|---|
| I. Read-Only v0 | ✅ PASS | Workers execute pipelines (existing behavior) — no new mutating agent tools added |
| II. Mission Isolation Plugin | ✅ PASS | Orchestrator unchanged; plugin chain untouched |
| III. Post Jira/Care opt-in | ✅ PASS | No new external write actions |
| IV. Eval Suite ≥80% | ✅ PASS | No agent/tool behavior change; eval cases not affected |
| V. Zero Secret Leakage | ✅ PASS | No new audit artifacts; `last_error` field must redact kubeconfig/token content |
| VI. Skills = SKILL.md | ✅ PASS | No SKILL.md changes |
| VII. Agnostic by Design | ✅ PASS | No Carrefour-specific values in core/api/agents |
| VIII. Filter rules = Postgres | ✅ PASS | `filter_rules` table untouched |

**Gate result: ALL PASS** — proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/011-durable-mission-queue/
├── plan.md              ← this file
├── research.md          ← Phase 0 output
├── data-model.md        ← Phase 1 output
├── quickstart.md        ← Phase 1 output
├── contracts/           ← Phase 1 output
│   ├── healthz.json
│   ├── metrics.md
│   └── durable_queue.md
└── tasks.md             ← /speckit.tasks (not created here)
```

### Source Code (repository root)

```text
agents/pipeline/
├── worker.py            # rewrite: DB poll loop, worker_id, adaptive sleep
├── durable_queue.py     # NEW: claim_next, mark_processed, mark_failed, mark_dead
└── orchestrator.py      # untouched (GKE token-patch block preserved)

api/
├── main.py              # multi-worker startup, remove asyncio.Queue
└── routes/
    └── metrics.py       # NEW: /metrics Prometheus endpoint

migrations/versions/
└── XXXX_triggers_durable_queue.py  # NEW: additive migration

triggers/
├── jira_mcp_poller.py   # remove mission_queue.put(), persist direct to DB
├── alertmanager_poller.py
└── alertmanager_webhook.py

docs/adr/
└── ADR-011-mission-queue.md  # NEW

tests/
├── unit/
│   └── test_durable_queue.py  # NEW: unit tests (mock DB)
└── integration/
    └── test_durable_queue_integration.py  # NEW: real DB tests
```

**Structure Decision**: Single project layout, extending existing `agents/pipeline/` and `api/routes/` directories. No new packages. The `durable_queue.py` module is co-located with `worker.py` for discoverability.

## Complexity Tracking

No constitution violations — no complexity tracking required.
