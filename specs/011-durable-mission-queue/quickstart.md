# Quickstart: Durable Mission Queue (011)

End-to-end testing guide for the durable mission queue feature.

---

## Prerequisites

- PostgreSQL running (`DATABASE_URL` set)
- `uv run alembic upgrade head` (migration applied)
- Platform started: `uv run uvicorn api.main:app`

---

## Scenario 1: Verify parallel workers start correctly

```bash
# Start with 3 workers
WORKER_CONCURRENCY=3 uv run uvicorn api.main:app --port 8000

# Check healthz
curl -s http://localhost:8000/healthz | python -m json.tool
# Expected: "worker_count": 3, "queue_depth": 0
```

---

## Scenario 2: Trigger survives a process restart (durability)

```bash
# 1. Insert a matched trigger directly into DB
psql $DATABASE_URL -c "
INSERT INTO triggers (id, tenant, source, external_id, payload, matched, received_at)
VALUES (gen_random_uuid(), 'enterprise', 'test', 'test-restart-001',
        '{\"labels\":{\"alertname\":\"KafkaBrokerDown\"}}'::jsonb, true, now())
ON CONFLICT DO NOTHING;
"

# 2. Verify it appears in queue depth
curl -s http://localhost:8000/healthz | python -m json.tool
# Expected: "queue_depth": 1

# 3. Kill the platform process (Ctrl+C or kill -9)

# 4. Verify trigger is still pending in DB
psql $DATABASE_URL -c "SELECT id, attempts, claimed_at, processed_at FROM triggers WHERE external_id='test-restart-001';"
# Expected: processed_at IS NULL (trigger not lost)

# 5. Restart the platform
WORKER_CONCURRENCY=1 uv run uvicorn api.main:app --port 8000

# 6. Within ~30 seconds, verify the trigger was picked up
psql $DATABASE_URL -c "SELECT attempts, claimed_by, processed_at FROM triggers WHERE external_id='test-restart-001';"
# Expected: attempts=1, claimed_by='worker-<pid>-0', processed_at set (or in progress)
```

---

## Scenario 3: Crash recovery with lease expiration (short lease for testing)

```bash
# Start with a very short lease (10 seconds) for testing
WORKER_CONCURRENCY=1 WORKER_LEASE_SECONDS=10 uv run uvicorn api.main:app --port 8000 &
PID=$!

# Insert a trigger
psql $DATABASE_URL -c "
INSERT INTO triggers (id, tenant, source, external_id, payload, matched, received_at)
VALUES (gen_random_uuid(), 'enterprise', 'test', 'test-lease-001',
        '{\"labels\":{\"alertname\":\"KafkaBrokerDown\"}}'::jsonb, true, now())
ON CONFLICT DO NOTHING;
"

# Wait for claim (2-3 seconds), then kill the worker mid-pipeline
sleep 3 && kill -9 $PID

# Verify trigger is claimed but not processed
psql $DATABASE_URL -c "SELECT attempts, claimed_at, processed_at FROM triggers WHERE external_id='test-lease-001';"

# Wait for lease to expire (10 seconds)
sleep 12

# Restart the platform
WORKER_CONCURRENCY=1 WORKER_LEASE_SECONDS=10 uv run uvicorn api.main:app --port 8000

# Verify trigger was re-claimed (attempts incremented)
sleep 5
psql $DATABASE_URL -c "SELECT attempts, claimed_by FROM triggers WHERE external_id='test-lease-001';"
# Expected: attempts=2
```

---

## Scenario 4: Dead-letter after max retries

```bash
# Start with low max attempts for testing
WORKER_CONCURRENCY=1 WORKER_MAX_ATTEMPTS=2 uv run uvicorn api.main:app --port 8000

# Insert a trigger with a payload that will cause the pipeline to fail
# (Use a tenant/env that doesn't exist → classification failure)
psql $DATABASE_URL -c "
INSERT INTO triggers (id, tenant, source, external_id, payload, matched, received_at)
VALUES (gen_random_uuid(), 'nonexistent-tenant', 'alertmanager', 'test-dead-001',
        '{\"labels\":{\"alertname\":\"TestAlert\"}}'::jsonb, true, now())
ON CONFLICT DO NOTHING;
"

# After 2 attempts, check dead status
sleep 60  # Wait for 2 pipeline attempts
psql $DATABASE_URL -c "SELECT attempts, last_error, processed_at FROM triggers WHERE external_id='test-dead-001';"
# Expected: attempts=2, last_error LIKE 'DEAD:%', processed_at IS NOT NULL

# Check dead metric
curl -s http://localhost:8000/metrics | grep kafkaops_mission_dead_total
# Expected: kafkaops_mission_dead_total 1.0
```

---

## Scenario 5: Prometheus metrics

```bash
# Start platform, process one trigger, then check metrics
curl -s http://localhost:8000/metrics | grep kafkaops_
# Expected output includes:
# kafkaops_queue_depth 0.0
# kafkaops_queue_inflight 0.0
# kafkaops_queue_claims_total{worker_id="worker-...-0"} 1.0
# kafkaops_mission_completed_total{...outcome="success"} 1.0
# kafkaops_mission_duration_seconds_count 1.0
# kafkaops_mission_dead_total 0.0
```

---

## Running the test suite

```bash
# Unit tests (no DB required)
uv run pytest tests/unit/test_durable_queue.py -v

# Integration tests (requires DB)
uv run pytest tests/integration/test_durable_queue_integration.py -v

# Full non-regression
uv run pytest tests/unit/ -q --tb=short
# Expected: 158+ tests passed
```
