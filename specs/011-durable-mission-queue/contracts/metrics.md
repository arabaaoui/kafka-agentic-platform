# Contract: GET /metrics (Prometheus)

**Endpoint**: `GET /metrics`
**Content-Type**: `text/plain; version=0.0.4; charset=utf-8`
**Auth**: None (internal scraping)

---

## Metric Definitions

### kafkaops_queue_depth (Gauge)

```
# HELP kafkaops_queue_depth Number of triggers pending + in-flight (processed_at IS NULL)
# TYPE kafkaops_queue_depth gauge
kafkaops_queue_depth 5.0
```

- **Source**: `SELECT count(*) FROM triggers WHERE matched=true AND processed_at IS NULL`
- **Refresh**: background task, every `METRICS_REFRESH_INTERVAL` seconds (default 5)
- **Alert threshold**: > 20 for > 5 minutes → possible worker stall

---

### kafkaops_queue_inflight (Gauge)

```
# HELP kafkaops_queue_inflight Number of triggers currently claimed by a worker
# TYPE kafkaops_queue_inflight gauge
kafkaops_queue_inflight 2.0
```

- **Source**: `SELECT count(*) FROM triggers WHERE claimed_at IS NOT NULL AND processed_at IS NULL`
- **Refresh**: same background task as `queue_depth`

---

### kafkaops_queue_claims_total (Counter)

```
# HELP kafkaops_queue_claims_total Total trigger claims, labeled by worker
# TYPE kafkaops_queue_claims_total counter
kafkaops_queue_claims_total{worker_id="worker-12345-0"} 42.0
kafkaops_queue_claims_total{worker_id="worker-12345-1"} 41.0
```

- **Labels**: `worker_id` — the `"worker-{pid}-{index}"` string
- **Increment**: on each successful `claim_next()` call

---

### kafkaops_mission_completed_total (Counter)

```
# HELP kafkaops_mission_completed_total Missions completed by outcome
# TYPE kafkaops_mission_completed_total counter
kafkaops_mission_completed_total{tenant="carrefour",env="prod",outcome="success"} 38.0
kafkaops_mission_completed_total{tenant="carrefour",env="prod",outcome="failed"} 3.0
kafkaops_mission_completed_total{tenant="carrefour",env="prod",outcome="ignored"} 1.0
```

- **Labels**: `tenant`, `env`, `outcome` (`success` | `failed` | `ignored`)
- **Increment**: on `mark_processed()` (success) or `mark_failed()` (failed). `ignored` = classification returned ignored.

---

### kafkaops_mission_duration_seconds (Histogram)

```
# HELP kafkaops_mission_duration_seconds End-to-end pipeline duration in seconds
# TYPE kafkaops_mission_duration_seconds histogram
kafkaops_mission_duration_seconds_bucket{le="30.0"} 2.0
kafkaops_mission_duration_seconds_bucket{le="60.0"} 8.0
kafkaops_mission_duration_seconds_bucket{le="120.0"} 15.0
kafkaops_mission_duration_seconds_bucket{le="300.0"} 38.0
kafkaops_mission_duration_seconds_bucket{le="+Inf"} 42.0
kafkaops_mission_duration_seconds_sum 4823.4
kafkaops_mission_duration_seconds_count 42.0
```

- **Buckets**: [30, 60, 120, 300, 600, +Inf] seconds
- **Measured**: from `claim_next()` to `mark_processed()` / `mark_failed()`

---

### kafkaops_mission_dead_total (Counter)

```
# HELP kafkaops_mission_dead_total Triggers marked dead (exhausted max retries)
# TYPE kafkaops_mission_dead_total counter
kafkaops_mission_dead_total 1.0
```

- **Increment**: on `mark_dead()` call
- **Alert threshold**: any increment → page oncall (dead missions = unrecoverable without manual intervention)

---

## Example Full Response

```text
# HELP kafkaops_queue_depth Number of triggers pending + in-flight
# TYPE kafkaops_queue_depth gauge
kafkaops_queue_depth 3.0
# HELP kafkaops_queue_inflight Number of triggers currently claimed
# TYPE kafkaops_queue_inflight gauge
kafkaops_queue_inflight 2.0
# HELP kafkaops_queue_claims_total Total trigger claims by worker
# TYPE kafkaops_queue_claims_total counter
kafkaops_queue_claims_total{worker_id="worker-42-0"} 7.0
kafkaops_queue_claims_total{worker_id="worker-42-1"} 7.0
kafkaops_queue_claims_total{worker_id="worker-42-2"} 6.0
# HELP kafkaops_mission_completed_total Missions completed by outcome
# TYPE kafkaops_mission_completed_total counter
kafkaops_mission_completed_total{tenant="carrefour",env="prod",outcome="success"} 18.0
kafkaops_mission_completed_total{tenant="carrefour",env="prod",outcome="failed"} 2.0
# HELP kafkaops_mission_duration_seconds End-to-end pipeline duration
# TYPE kafkaops_mission_duration_seconds histogram
kafkaops_mission_duration_seconds_bucket{le="60.0"} 4.0
kafkaops_mission_duration_seconds_bucket{le="120.0"} 10.0
kafkaops_mission_duration_seconds_bucket{le="300.0"} 18.0
kafkaops_mission_duration_seconds_bucket{le="+Inf"} 20.0
kafkaops_mission_duration_seconds_sum 2341.2
kafkaops_mission_duration_seconds_count 20.0
# HELP kafkaops_mission_dead_total Triggers exhausted max retries
# TYPE kafkaops_mission_dead_total counter
kafkaops_mission_dead_total 0.0
```
