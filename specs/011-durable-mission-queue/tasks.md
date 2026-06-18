# Tasks: Durable Mission Queue with Parallel Processing

**Input**: Design documents from `/specs/011-durable-mission-queue/`
**Branch**: `011-durable-mission-queue`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Format**: `[ID] [P?] [Story?] Description — file path`
- **[P]** = parallelizable (different files, no incomplete dependencies)
- **[US#]** = user story (US1=parallel workers, US2=durable queue, US3=observability, US4=ADR)

---

## Phase 1: Setup

**Purpose**: Confirm migration tooling is operational and gather final revision ID needed for the migration file.

- [X] T001 Identify the latest migration revision ID from migrations/versions/ (run `uv run alembic current` or read the latest file header) to use as `down_revision` in T002 — no file created

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The Alembic migration that extends `triggers` must land before US2 and US3 can be tested end-to-end. US1 (parallel workers) does NOT require this migration and can start in parallel.

**⚠️ CRITICAL**: US2 and US3 depend on this phase. US1 can start immediately from Phase 1.

- [X] T002 Create Alembic migration `migrations/versions/XXXX_triggers_durable_queue.py` — additive migration adding columns `claimed_at TIMESTAMPTZ NULL`, `claimed_by TEXT NULL`, `attempts INT NOT NULL DEFAULT 0`, `last_error TEXT NULL` to `triggers` table, plus partial index `idx_triggers_pending ON triggers(received_at) WHERE matched=true AND processed_at IS NULL`; use latest revision from T001 as `down_revision`; include `upgrade()` and `downgrade()` that reverses all changes

**Checkpoint**: Run `uv run alembic upgrade head` to apply; `uv run alembic downgrade -1` to verify reversibility.

---

## Phase 3: User Story 1 — Multi-Worker Parallel Processing (Priority: P1) 🎯 MVP

**Goal**: Launch N parallel workers via `WORKER_CONCURRENCY` env var with zero other behavior change. Safe to deploy with `WORKER_CONCURRENCY=1` (default).

**Independent Test**: `WORKER_CONCURRENCY=3 uv run uvicorn api.main:app` → `curl /healthz` returns `worker_count: 3`; 3 simultaneous triggers are picked up concurrently (overlapping log timestamps).

- [X] T003 [US1] Update `api/main.py` startup (lines 86, 102–106): read `WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "1"))`, replace single `asyncio.create_task(start_mission_worker(...))` with list comprehension creating N tasks, store list in `app.state.worker_tasks`, attach `_on_task_done` callback to each, cancel all tasks on shutdown — file: `api/main.py`
- [X] T004 [US1] Update `agents/pipeline/worker.py`: add `worker_id: str` parameter to `start_mission_worker()` signature (default `"worker-0"`), prefix every `log.info/log.error/log.critical` with `[%s] worker_id`, update docstring — file: `agents/pipeline/worker.py`
- [X] T005 [P] [US1] Enrich `/healthz` response in `api/main.py`: add `worker_count` key (len of `app.state.worker_tasks` that are not done) to the dict returned by `healthz()` — file: `api/main.py`
- [X] T006 [US1] Add startup warning in `api/main.py` lifespan: if `WORKER_CONCURRENCY > 7` (floor(pool_max/4)), log `log.warning("WORKER_CONCURRENCY=%d exceeds DB pool capacity (max safe: 7) — connection exhaustion risk", concurrency)` — file: `api/main.py`

**Checkpoint**: `uv run pytest tests/unit/ -q` must still pass (158 tests). `WORKER_CONCURRENCY=3` startup log shows 3 worker tasks created.

---

## Phase 4: User Story 2 — Durable Queue Without Data Loss (Priority: P2)

**Goal**: Replace `asyncio.Queue` with PostgreSQL-backed `SELECT FOR UPDATE SKIP LOCKED` pattern. Workers survive process restart. In-flight triggers auto-recover after lease expiry.

**Independent Test**: Insert trigger in DB, kill process, restart → trigger is re-claimed and pipeline runs. `attempts` counter increments on re-claim.

**Prerequisite**: T002 migration must be applied before end-to-end testing. Code changes are independent of migration.

### Durable queue module (new file)

- [X] T007 [US2] Create `agents/pipeline/durable_queue.py` — implement 5 functions per contract in `specs/011-durable-mission-queue/contracts/durable_queue.md`:
  - `claim_next(session, worker_id, lease_seconds=900, max_attempts=3) -> dict | None` — single CTE statement: `WITH next AS (SELECT id FROM triggers WHERE matched=true AND processed_at IS NULL AND (claimed_at IS NULL OR claimed_at < now() - make_interval(secs => :lease_seconds)) AND (last_error IS NULL OR last_error NOT LIKE 'DEAD:%') ORDER BY received_at FOR UPDATE SKIP LOCKED LIMIT 1) UPDATE triggers SET claimed_at=now(), claimed_by=:worker_id, attempts=attempts+1 WHERE id=(SELECT id FROM next) RETURNING *`; commit must be done by caller; returns `result.mappings().fetchone()` as dict or None
  - `mark_processed(session, trigger_id, mission_id) -> None` — `UPDATE triggers SET processed_at=now() WHERE id=:trigger_id`
  - `mark_failed(session, trigger_id, error, max_attempts=3) -> bool` — reads current `attempts`; if `>= max_attempts` calls `mark_dead()`; otherwise sets `claimed_at=NULL, claimed_by=NULL, last_error=error[:4096]`; returns True if dead, False if reset for retry
  - `mark_dead(session, trigger_id, error) -> None` — sets `last_error='DEAD:' + error[:4000]`, `processed_at=now()`
  - `queue_stats(session) -> dict` — two COUNT queries using partial index, returns `{"depth": int, "inflight": int, "oldest_pending_age_seconds": float | None}`
  - file: `agents/pipeline/durable_queue.py`

### Worker rewrite

- [X] T008 [US2] Rewrite `agents/pipeline/worker.py` using durable queue: replace `while True: queue_item = await queue.get()` loop with DB poll loop using `claim_next()`; add adaptive backoff (`sleep_s = 2`, doubles each idle cycle to max 30, resets on claim); add heartbeat — inner `async def _heartbeat(engine, trigger_id, interval, stop_event)` that refreshes `claimed_at=now()` every `interval` seconds until `stop_event.is_set()`; start heartbeat as `asyncio.create_task(_heartbeat(...))` on claim, cancel on completion; call `mark_processed()` on success, `mark_failed()` on pipeline exception; new signature: `start_mission_worker(engine, worker_id, model)` — no `queue` parameter — file: `agents/pipeline/worker.py`

### Remove queue from trigger producers (order matters: webhook handler first)

- [X] T009 [US2] Update `triggers/alertmanager_webhook.py`: remove `mission_queue` parameter from `AlertmanagerWebhookHandler.__init__()` and all `self._queue` references; remove `await mission_queue.put(item)` call (line ~73); the DB trigger insert already present is the durable queue entry — the worker will poll it; update `process_webhook_background()` function signature accordingly — file: `triggers/alertmanager_webhook.py`
- [X] T010 [P] [US2] Update `triggers/alertmanager_poller.py`: remove `mission_queue: asyncio.Queue` from `AlertmanagerPoller.__init__()` constructor (line 29) and `self._queue` assignment; update `AlertmanagerWebhookHandler(...)` instantiation at line ~110 to remove `mission_queue=self._queue`; remove `await self._queue.put(item)` (line 64) and `items_to_enqueue` list (lines 47–64) — the handler's DB insert is sufficient; update `start_alertmanager_poller(mission_queue)` signature at line 126 to remove the `mission_queue` parameter — file: `triggers/alertmanager_poller.py`
- [X] T011 [P] [US2] Update `triggers/jira_mcp_poller.py`: remove `mission_queue: asyncio.Queue` from `JiraMcpPoller.__init__()` (lines 41, 50, 55); remove `await self._queue.put({...})` (line 145); ensure the existing `INSERT INTO triggers` (line 214) uses `ON CONFLICT (tenant, source, external_id) DO NOTHING` if not already present — file: `triggers/jira_mcp_poller.py`

### Remove asyncio.Queue from api/main.py (after T009–T011)

- [X] T012 [US2] Update `api/main.py`: remove `mission_queue: asyncio.Queue = asyncio.Queue()` (line 86) and `app.state.mission_queue = mission_queue`; update `start_mission_worker` calls (from T003) to pass `engine` and `worker_id="worker-{i}"` instead of `queue`; update `start_alertmanager_poller(mission_queue)` call at line ~117 to `start_alertmanager_poller()` (no arg); update `JiraMcpPoller(db_engine=engine, mission_queue=mission_queue)` at line ~109 to remove `mission_queue=mission_queue`; remove `asyncio.Queue` import if no longer used — file: `api/main.py`

**Checkpoint**: `uv run pytest tests/unit/ -q` still passes. Manual quickstart Scenario 2 (trigger survives restart) passes.

---

## Phase 5: User Story 3 — Queue Observability and Monitoring (Priority: P3)

**Goal**: `/metrics` Prometheus endpoint with 6 `kafkaops_*` metrics; enriched `/healthz` with queue depth and oldest pending age.

**Independent Test**: `curl http://localhost:8000/metrics | grep kafkaops_` returns all 6 metric families. `/healthz` returns `queue_depth` and `oldest_pending_age_seconds`.

**Prerequisite**: T007 (`queue_stats()` function) must be complete. T002 migration must be applied for real values.

- [X] T013 [US3] Create `api/routes/metrics.py`: define 6 `prometheus_client` metric objects at module level (`kafkaops_queue_depth = Gauge(...)`, `kafkaops_queue_inflight = Gauge(...)`, `kafkaops_queue_claims_total = Counter(..., ["worker_id"])`, `kafkaops_mission_completed_total = Counter(..., ["tenant", "env", "outcome"])`, `kafkaops_mission_duration_seconds = Histogram(..., buckets=[30,60,120,300,600])`, `kafkaops_mission_dead_total = Counter(...)`); implement `GET /metrics` route that returns `Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)` from `prometheus_client`; export metric objects for use by worker and background task — file: `api/routes/metrics.py`
- [X] T014 [US3] Add background metrics refresh task in `api/main.py`: create `async def _refresh_metrics(engine, interval)` that calls `queue_stats()` from `durable_queue` every `interval` seconds (default `int(os.getenv("METRICS_REFRESH_INTERVAL", "5"))`), updates `kafkaops_queue_depth.set(stats["depth"])` and `kafkaops_queue_inflight.set(stats["inflight"])`; start it as `asyncio.create_task(_refresh_metrics(engine, interval))` in lifespan, store in `app.state.metrics_task`, cancel on shutdown — file: `api/main.py`
- [X] T015 [US3] Instrument `agents/pipeline/worker.py` with counter and histogram calls: import metric objects from `api/routes/metrics`; after `claim_next()` success call `kafkaops_queue_claims_total.labels(worker_id=worker_id).inc()`; record `start_time = time.monotonic()` before pipeline; after `mark_processed()` call `kafkaops_mission_completed_total.labels(..., outcome="success").inc()` and `kafkaops_mission_duration_seconds.observe(time.monotonic()-start_time)`; after `mark_failed()` call `kafkaops_mission_completed_total.labels(..., outcome="failed").inc()`; after `mark_dead()` (returned True from mark_failed) call `kafkaops_mission_dead_total.inc()` — file: `agents/pipeline/worker.py`
- [X] T016 [P] [US3] Enrich `/healthz` in `api/main.py`: call `queue_stats(session)` from `durable_queue` inside the `healthz()` handler (use `async with get_session() as session`); add `queue_depth`, `oldest_pending_age_seconds` to the returned dict alongside `worker_count` from T005 — file: `api/main.py`
- [X] T017 [US3] Register metrics router in `api/main.py`: add `from api.routes import metrics` and `app.include_router(metrics.router)` in `create_app()` alongside existing routers — file: `api/main.py`

**Checkpoint**: `curl http://localhost:8000/metrics | grep kafkaops_` returns 6 metric families. `curl /healthz` includes `queue_depth` and `oldest_pending_age_seconds`.

---

## Phase 6: User Story 4 — Architectural Decision Record (Priority: P4)

**Goal**: Document the decision, rejected Kafka alternative, and migration criteria as `docs/adr/ADR-011-mission-queue.md`.

**Independent Test**: File exists, readable, and contains all 4 required sections (problem, decision, alternatives, migration criteria).

- [X] T018 [P] [US4] Create `docs/adr/ADR-011-mission-queue.md` — content must cover: (1) **Status** and date; (2) **Context** — the 3 lacunes (data loss on crash, no observability, serialized I/O-bound missions); (3) **Decision** — triggers table as durable queue via `SELECT FOR UPDATE SKIP LOCKED`, N async workers, Prometheus metrics; (4) **Rationale** — why Kafka was rejected (correlated failure risk: platform monitors the same Kafka it would depend on); (5) **Alternatives Considered** — Kafka topic + consumer group, Redis Streams, asyncio.Queue (status quo); (6) **Consequences** — at-least-once delivery, dedup via UNIQUE constraint, lease heartbeat for long missions, pool constraint (max 7 workers); (7) **Migration Criteria for Kafka** — when scale > 50 concurrent missions, when multi-replica becomes necessary, when a dedicated control-plane Kafka cluster is available separate from monitored infra — file: `docs/adr/ADR-011-mission-queue.md`

**Checkpoint**: File exists at `docs/adr/ADR-011-mission-queue.md`, contains all 7 sections.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T019 Write unit tests for `agents/pipeline/durable_queue.py` in `tests/unit/test_durable_queue.py`: mock `AsyncSession`; test `claim_next()` returns None when no rows; test `claim_next()` returns dict when row available; test `mark_failed()` returns False and resets claimed_at when attempts < max; test `mark_failed()` returns True and delegates to mark_dead when attempts >= max; test `mark_dead()` sets last_error prefix 'DEAD:'; test `queue_stats()` returns correct dict shape — file: `tests/unit/test_durable_queue.py`
- [X] T020 [P] Run full non-regression test suite: `uv run pytest tests/unit/ -q --tb=short` must report ≥ 158 passed, 0 failed — no file change, verification only
- [X] T021 [P] Validate quickstart.md Scenario 1 (parallel workers) and Scenario 5 (Prometheus metrics) manually against the running platform to confirm all contracts match implementation — no file change unless mismatches found

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (T001)
    └── Phase 2 (T002: migration)
            └── US2 end-to-end testing (T007–T012)
            └── US3 end-to-end testing (T013–T017)

Phase 1 (T001)
    └── US1 (T003–T006) ← CAN START IMMEDIATELY, no migration needed
```

### User Story Dependencies

| Story | Depends On | Can Start After |
|-------|-----------|----------------|
| US1 (T003–T006) | None | Phase 1 complete |
| US2 (T007–T012) | T002 migration for E2E test; T007 for T008, T015 | Phase 2 complete |
| US3 (T013–T017) | T007 (queue_stats), T008 (worker instrumentation) | T007 + T008 complete |
| US4 (T018) | None | Phase 1 complete |

### Within US2 — Execution Order

```
T007 (durable_queue.py — new file)
    └── T008 (worker.py rewrite — uses durable_queue)
T009 (alertmanager_webhook.py — no mission_queue)
    └── T010 (alertmanager_poller.py — uses webhook handler)
T011 (jira_mcp_poller.py — independent of T009/T010)
T009 + T010 + T011 all complete
    └── T012 (api/main.py — removes asyncio.Queue, depends on producers being updated)
```

### Within US3 — Execution Order

```
T013 (metrics.py — define metric objects)
    └── T015 (worker.py — imports metric objects from T013)
T013 + T007 complete
    └── T014 (api/main.py — background refresh task uses queue_stats from T007)
    └── T016 (api/main.py — healthz uses queue_stats from T007)
T013 complete
    └── T017 (api/main.py — register router)
```

### Parallel Opportunities

```
# US1 can run in parallel with US2 (different files):
US1: T003→T004→T005→T006  (api/main.py, worker.py)
US2: T007→T008            (durable_queue.py, worker.py — wait for US1 T004 to finish worker.py)

# US2 producer tasks can run in parallel after T007:
T009 ‖ T010 ‖ T011        (three different trigger files)

# US4 can run fully in parallel with US1/US2/US3:
T018 (docs only)
```

**Note on worker.py conflicts**: T004 (US1), T008 (US2), and T015 (US3) all touch `agents/pipeline/worker.py`. Execute in order: T004 → T008 → T015.

---

## Parallel Example: US2

```bash
# After T007 (durable_queue.py) is complete, these run in parallel:
Task T009: "Remove mission_queue from triggers/alertmanager_webhook.py"
Task T010: "Remove mission_queue from triggers/alertmanager_poller.py"
Task T011: "Remove mission_queue from triggers/jira_mcp_poller.py"

# Then sequentially:
Task T008: "Rewrite worker.py poll loop (uses durable_queue)"
Task T012: "Remove asyncio.Queue from api/main.py"
```

---

## Implementation Strategy

### MVP (US1 only — zero infrastructure change)

1. ✅ Phase 1: T001 (5 min)
2. ✅ Phase 3: T003 → T004 → T005 → T006 (api/main.py + worker.py changes only)
3. **Deploy with `WORKER_CONCURRENCY=1`** — behavior identical to before, zero risk
4. **Scale test**: bump to `WORKER_CONCURRENCY=3`, verify parallel processing
5. Stop here if parallel workers are sufficient for current load

### Incremental Delivery

1. MVP (US1) → parallel workers ✅
2. Add US2 → durable queue, no data loss ✅ (requires DB migration)
3. Add US3 → Prometheus metrics + enriched healthz ✅
4. Add US4 → ADR documentation ✅ (can be done any time)

### Sequential Minimum (1 developer, 1 PR per story)

```
T001 → T002 → T003 → T004 → T005 → T006       ← PR: "feat: parallel workers (US1)"
       ↓
T007 → T008 → T009 → T010 → T011 → T012        ← PR: "feat: durable queue (US2)"
       ↓
T013 → T014 → T015 → T016 → T017               ← PR: "feat: queue observability (US3)"
       ↓
T018                                            ← PR: "docs: ADR-011 mission queue"
       ↓
T019 → T020 → T021                              ← Polish
```

---

## Notes

- Worker.py is touched 3 times (T004, T008, T015) — execute strictly in order, no parallel
- `api/main.py` is touched 4 times (T003, T005/T006, T012, T014/T016/T017) — group within each US phase
- T002 migration is reversible (`downgrade()`) — safe to apply on staging first
- `WORKER_CONCURRENCY=1` is always safe — identical to prior behavior
- `WORKER_LEASE_SECONDS=10` for quickstart crash-recovery testing (Scenario 3)
- Dead triggers (`last_error LIKE 'DEAD:%'`) are never re-claimed — verify by checking claim_next CTE filter
