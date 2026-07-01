# Implementation Plan: Mission Isolation (Multi-Env, Plugin-Enforced)

**Branch**: `003-mission-isolation` | **Date**: 2026-05-10 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-mission-isolation/spec.md`

## Summary

Every agent mission is bound at creation to a single environment (`preprod`, `prod`, `rec`, …). The `MissionIsolationPlugin` enforces this contract on every tool call by resolving the target endpoint against `TenantConfig.envs` and raising `CrossEnvAccessBlocked` when a mismatch is detected. Isolation is bidirectional and tenant-scoped. Mission identities follow a deterministic format (`{TENANT}-{ENV}-{TYPE}-{SUBJECT}-{YYYYMMDD}-{SEQ:03d}`) backed by a Postgres sequential counter to guarantee uniqueness under concurrency. Tenant environment configs are hot-reloadable at runtime via `POST /admin/reload-tenants` without server restart.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Pydantic v2, pyyaml, FastAPI, Google ADK (plugin callback hooks), asyncpg / psycopg2 (Postgres sequence)
**Storage**: PostgreSQL — `missions_seq` table for atomic sequential counter; `missions` table for mission rows; YAML files in `tenants/` for env config
**Testing**: pytest — unit tests for model validation and plugin logic, integration test for live API reload
**Target Platform**: Linux server (GKE-hosted agentic backend)
**Project Type**: Library + web-service (plugin integrated into existing ADK agent pipeline + FastAPI admin route)
**Performance Goals**: `MissionIsolationPlugin.before_tool_callback` adds <50ms overhead per tool call (SC-004); tenant reload completes within 5 seconds of `POST /admin/reload-tenants` (SC-002)
**Constraints**: MISSION_ID sequential counter must produce zero duplicates under 10 concurrent mission creations (SC-003); invalid tenant YAML must be rejected without disrupting the active in-memory config (FR-006)
**Scale/Scope**: ≤20 envs per tenant for v0 (O(n) endpoint lookup acceptable); multi-tenant support in plugin (cross-tenant access blocked)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Rule | Status | Notes |
|------|--------|-------|
| **II — Safety enforcement by plugin, not convention** | PASS | `MissionIsolationPlugin` is the core deliverable of this spec. Cross-env access is blocked at the plugin layer, not left to agent discretion. |
| **VII — Tenant data stays in `tenants/`, nothing tenant-specific in `core/`** | PASS | `tenants/enterprise.yaml` lives in `tenants/`. All logic in `core/` is tenant-agnostic (keyed by `tenant` string, not hardcoded). |
| **I — Single responsibility per module** | PASS | `core/mission.py` owns MissionContext only; `core/tenant.py` owns config loading only; `core/mission_isolation.py` owns the plugin only. |
| **III — No restart required for config changes** | PASS | `POST /admin/reload-tenants` hot-swaps in-memory `TenantConfig` under a `threading.Lock`. |
| **V — Validation at boundary** | PASS | Pydantic v2 validates `TenantConfig`/`EnvConfig` on every reload. Invalid YAML is rejected with 400 before touching active config. |

No violations requiring complexity justification.

## Project Structure

### Documentation (this feature)

```text
specs/003-mission-isolation/
├── plan.md              # This file
├── spec.md              # Approved feature specification
├── data-model.md        # Phase 1 output — MissionContext, TenantConfig, EnvConfig field details
├── contracts/           # Phase 1 output — CrossEnvAccessBlocked contract, reload API contract
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
core/
├── mission.py               # MissionContext (Pydantic), MissionType enum, MissionStatus enum,
│                            #   generate_mission_id(tenant, env, type, subject, date, seq) -> str
├── tenant.py                # TenantConfig, EnvConfig (Pydantic v2), load_tenant(yaml_path),
│                            #   load_tenants_dir(dir), TenantRegistry (threading.Lock + swap)
├── mission_isolation.py     # MissionIsolationPlugin, CrossEnvAccessBlocked exception
└── plugins.py               # Plugin base class, PluginChain, all 8 plugin registrations
                             #   (GuardrailsPlugin, ResiliencePlugin, OTelMetricsPlugin,
                             #    AuditPlugin, ActivityPlugin, Mem0MemoryPlugin,
                             #    MissionIsolationPlugin, AutonomyPlugin, ErrorHandlerPlugin)

api/
└── routes/
    └── admin.py             # POST /admin/reload-tenants → reload TenantRegistry, return 200/400

tenants/
└── enterprise.yaml           # Enterprise tenant config (preprod env pre-configured)

db/
└── migrations/
    └── 001_missions_seq.sql # CREATE TABLE missions_seq (id SERIAL PRIMARY KEY, ...);
                             #   used by generate_mission_id() via SELECT FOR UPDATE

tests/
├── unit/
│   ├── test_mission.py             # MISSION_ID format, slug regex validation, SEQ zero-padding,
│   │                               #   MissionStatus/MissionType enum coverage
│   ├── test_tenant.py              # TenantConfig load from valid YAML, Pydantic rejection of
│   │                               #   invalid YAML, multi-env dict parsing, optional vault_path
│   └── test_mission_isolation.py   # cross-env block (preprod->prod, prod->preprod),
│                                   #   same-env allow, env-agnostic tool allow (Jira/GitLab MCP),
│                                   #   cross-tenant block, audit.jsonl entry format
└── integration/
    └── test_tenant_reload.py       # POST /admin/reload-tenants with valid YAML → 200 + effect,
                                    #   with invalid YAML → 400 + previous config untouched,
                                    #   new env added → isolation enforced after reload
```

**Structure Decision**: Single-project layout. No frontend changes in this feature. All new code is in `core/` (domain logic), `api/routes/` (admin endpoint), `tenants/` (config), `db/migrations/` (Postgres DDL), and `tests/`. This extends the existing project structure without introducing new top-level directories.

## Complexity Tracking

> No Constitution Check violations. This section is intentionally left blank.

---

## Implementation Phases

### Phase 0 — Research (pre-coding, no files written)

| Task | Goal |
|------|------|
| Audit existing `core/plugins.py` Plugin base class | Confirm `before_tool_callback(tool_name, tool_params, mission_context)` signature and hook registration mechanism |
| Audit existing `audit.jsonl` write path | Confirm format used by `AuditPlugin` so `MissionIsolationPlugin` emits consistent entries |
| Audit existing FastAPI app entrypoint | Confirm how `api/routes/` are registered, confirm admin blueprint exists or needs creating |
| Audit Postgres connection pool | Confirm which library (asyncpg vs psycopg2) is in use, confirm pool is accessible from `core/mission.py` |
| Verify `tenants/` directory exists and `enterprise.yaml` schema | Confirm YAML structure already matches `TenantConfig`/`EnvConfig` field names or document delta |

### Phase 1 — Design Artifacts

Deliverables: `data-model.md`, `contracts/cross_env_blocked.md`, `contracts/reload_api.md`

**data-model.md** covers:
- `MissionContext` full field table (name, type, required, default, validation rule)
- `TenantConfig` + `EnvConfig` full field table
- `MissionType` enum values: `INCIDENT`, `MAINTENANCE`, `INVESTIGATION`, `REVIEW`
- `MissionStatus` enum values: `OPEN`, `CLOSED`, `PARTIAL`
- `MISSION_ID` BNF: `TENANT "-" ENV "-" TYPE "-" SUBJECT "-" YYYYMMDD "-" SEQ`
- SUBJECT regex: `^[a-z0-9]+(-[a-z0-9]+)*$`, max 30 chars
- SEQ source: Postgres `SELECT nextval('missions_id_seq')` scoped per `(tenant, env, type, subject, date)` or global per day (decision to finalize in data-model.md)

**contracts/cross_env_blocked.md** covers:
- `CrossEnvAccessBlocked` exception fields: `mission_id`, `tool_name`, `tool_params`, `mission_env`, `target_env`
- Audit log entry schema: `{ "event": "cross_env_blocked", "mission_id": "...", "tool": "...", "target_env": "...", "mission_env": "...", "ts": "..." }`
- SSE event schema: `{ "type": "mission_event", "payload": { "kind": "access_blocked", ... } }`
- Plugin allow-list for env-agnostic tools: `c4-atlassian`, `gitlab` (Jira/GitLab MCP are never blocked)

**contracts/reload_api.md** covers:
- `POST /admin/reload-tenants` request body (none required; optional `?dir=` param)
- Success response `200`: `{ "loaded": ["enterprise"], "envs": { "enterprise": ["preprod", "prod"] } }`
- Error response `400`: `{ "errors": [{ "tenant": "enterprise", "detail": "EnvConfig.prom_url missing" }] }`
- Threading contract: `threading.Lock` acquired for atomic swap; readers always see a consistent `TenantConfig`

### Phase 2 — Implementation Order

Dependencies are strictly respected: models first, then loading, then plugin, then API route, then tests.

1. **`db/migrations/001_missions_seq.sql`** — DDL for `missions_seq` table (no Python deps)
2. **`core/mission.py`** — `MissionType`, `MissionStatus`, `MissionContext`, `generate_mission_id()` with Postgres sequence call
3. **`core/tenant.py`** — `EnvConfig`, `TenantConfig`, `TenantRegistry`, `load_tenant()`, `load_tenants_dir()`
4. **`core/mission_isolation.py`** — `CrossEnvAccessBlocked`, `MissionIsolationPlugin.before_tool_callback()`
5. **`core/plugins.py`** — register `MissionIsolationPlugin` in `PluginChain` (between `AuditPlugin` and `AutonomyPlugin`)
6. **`api/routes/admin.py`** — `POST /admin/reload-tenants` endpoint
7. **`tenants/enterprise.yaml`** — validate/update schema to match `TenantConfig`/`EnvConfig`
8. **`tests/unit/test_mission.py`** — MISSION_ID, slug validation, SEQ zero-padding
9. **`tests/unit/test_tenant.py`** — config load, Pydantic rejection, multi-env
10. **`tests/unit/test_mission_isolation.py`** — cross-env block, same-env allow, env-agnostic allow, cross-tenant block, audit entry
11. **`tests/integration/test_tenant_reload.py`** — live reload via TestClient

### Phase 3 — Validation Against Success Criteria

| Criterion | How Verified |
|-----------|-------------|
| SC-001: 100% cross-env tool calls blocked | `test_mission_isolation.py` covers all 5 tools (`prom_query`, `vm_query`, `k_exec`, `vault_read`, `cluster_health`) |
| SC-002: Reload takes effect within 5 seconds | `test_tenant_reload.py` asserts new env present immediately after 200 response |
| SC-003: No duplicate MISSION_IDs under 10 concurrent creations | Load test in `test_mission.py` using `concurrent.futures.ThreadPoolExecutor(max_workers=10)` |
| SC-004: <50ms overhead per tool call | Benchmark test in `test_mission_isolation.py` using `time.perf_counter()` over 1000 iterations |
| SC-005: Invalid slugs rejected | `test_mission.py` parametrized with: `"PVC Saturation"`, `"pvc_saturation"`, `"a"*31`, `"-pvc"`, `""` — all must raise `ValidationError` |
