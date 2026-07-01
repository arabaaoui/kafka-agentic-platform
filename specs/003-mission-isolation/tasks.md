# Tasks: Mission Isolation (Multi-Env, Plugin-Enforced)

**Feature Branch**: `003-mission-isolation`
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)
**Generated**: 2026-05-10
**Status**: Ready for implementation

---

## Legend

- `[P]` — Parallelizable with other tasks in the same phase (no shared write dependency)
- `[US1]` / `[US2]` / `[US3]` — User Story label (phases 3+)
- `[ ]` — Not started | `[x]` — Done

---

## Phase 1 — Setup (package scaffolding, no logic)

> Goal: ensure all Python packages are importable before any implementation task runs. These tasks are pure file creation and have no interdependencies.

- [ ] T001 [P] Create `core/__init__.py` — empty file, marks `core/` as a Python package
- [ ] T002 [P] Create `api/__init__.py` — empty file, marks `api/` as a Python package
- [ ] T003 [P] Create `api/routes/__init__.py` — empty file, marks `api/routes/` as a Python package
- [ ] T004 [P] Create `tests/__init__.py` — empty file, marks `tests/` as a Python package
- [ ] T005 [P] Create `tests/unit/__init__.py` — empty file, marks `tests/unit/` as a Python package
- [ ] T006 [P] Create `tests/integration/__init__.py` — empty file, marks `tests/integration/` as a Python package
- [ ] T007 [P] Verify `tenants/` directory exists; if not, create it — required by T019 (TenantRegistry path)

---

## Phase 2 — Foundational BLOCKING (Plugin ABC + DB sequence; all other phases depend on these)

> Goal: establish the two lowest-level foundations — the `Plugin` ABC / `PluginChain` that every plugin extends, and the Postgres DDL that `generate_mission_id()` depends on. Nothing else can be implemented without both.

- [ ] T008 Write `core/plugins.py` — define abstract base class `Plugin` with `before_tool_callback(tool_name: str, tool_params: dict, mission_context: MissionContext) -> None` and `after_tool_callback(tool_name: str, result: Any, mission_context: MissionContext) -> None`; define `PluginChain` that holds an ordered list of `Plugin` instances and iterates `before_tool_callback` / `after_tool_callback`; add stub class bodies (pass) for all 8 plugins: `GuardrailsPlugin`, `ResiliencePlugin`, `OTelMetricsPlugin`, `AuditPlugin`, `ActivityPlugin`, `Mem0MemoryPlugin`, `MissionIsolationPlugin`, `AutonomyPlugin`, `ErrorHandlerPlugin`
- [ ] T009 [P] Write `migrations/versions/0001_initial.sql` — DDL for `missions_seq` table used as atomic sequential counter: `CREATE TABLE IF NOT EXISTS missions_seq (id BIGSERIAL PRIMARY KEY, tenant VARCHAR(64) NOT NULL, env VARCHAR(64) NOT NULL, type VARCHAR(64) NOT NULL, subject VARCHAR(30) NOT NULL, mission_date DATE NOT NULL, seq INTEGER NOT NULL, UNIQUE (tenant, env, type, subject, mission_date, seq));` — this provides the per-(tenant, env, type, subject, date) sequential counter for `MISSION_ID` (FR-008)

---

## Phase 3 — US1: MissionIsolationPlugin

> Goal: implement the cross-env safety enforcement block described in US1. Depends on T008 (Plugin ABC).

- [ ] T010 [US1] Write `core/mission_isolation.py` — define `CrossEnvAccessBlocked` exception with fields `mission_id: str`, `tool_name: str`, `tool_params: dict`, `mission_env: str`, `target_env: str`
- [ ] T011 [US1] In `core/mission_isolation.py` — implement `_resolve_target_env(tool_name: str, tool_params: dict, tenant_config: TenantConfig) -> str | None`: iterates `tenant_config.envs`, matches tool parameter values (prom_url, vm_url, kubeconfig prefix) against each `EnvConfig`; returns matched env name or `None` if no env-specific endpoint is targeted (env-agnostic tools such as `c4-atlassian` and `gitlab` return `None`)
- [ ] T012 [US1] In `core/mission_isolation.py` — implement `MissionIsolationPlugin.before_tool_callback`: calls `_resolve_target_env()`; if resolved env is not None and does not match `mission_context.env`, raises `CrossEnvAccessBlocked`; also blocks cross-tenant access when `mission_context.tenant` does not match the resolved tenant
- [ ] T013 [US1] In `core/mission_isolation.py` — implement audit write inside `MissionIsolationPlugin.before_tool_callback`: on `CrossEnvAccessBlocked`, appends JSON line `{"event": "cross_env_blocked", "mission_id": "...", "tool": "...", "target_env": "...", "mission_env": "...", "ts": "<ISO8601>"}` to `audit.jsonl` before raising
- [ ] T014 [US1] In `core/plugins.py` — register `MissionIsolationPlugin` in the default `PluginChain` order between `AuditPlugin` and `AutonomyPlugin` (replace stub with import + instantiation)
- [ ] T015 [US1] [P] Write `tests/unit/test_mission_isolation.py` — test: cross-env block preprod->prod raises `CrossEnvAccessBlocked`
- [ ] T016 [US1] [P] In `tests/unit/test_mission_isolation.py` — test: cross-env block prod->preprod raises `CrossEnvAccessBlocked` (bidirectional, per spec US1 scenario 4)
- [ ] T017 [US1] [P] In `tests/unit/test_mission_isolation.py` — test: same-env tool call (preprod->preprod prom_url) proceeds without exception
- [ ] T018 [US1] [P] In `tests/unit/test_mission_isolation.py` — test: env-agnostic tool call (`c4-atlassian`, `gitlab` MCP) is never blocked regardless of `mission.env` (FR-003)
- [ ] T019 [US1] [P] In `tests/unit/test_mission_isolation.py` — test: cross-tenant block — mission with `tenant=enterprise` blocked from calling tool targeting `tenant=acme` endpoint
- [ ] T020 [US1] [P] In `tests/unit/test_mission_isolation.py` — test: audit.jsonl entry format after cross-env block — assert JSON keys `event`, `mission_id`, `tool`, `target_env`, `mission_env`, `ts` all present with correct values
- [ ] T021 [US1] [P] In `tests/unit/test_mission_isolation.py` — benchmark test: `MissionIsolationPlugin.before_tool_callback` completes in <50ms over 1000 iterations (SC-004, `time.perf_counter()`)
- [ ] T022 [US1] [P] In `tests/unit/test_plugins.py` — test: `PluginChain` calls `before_tool_callback` on all registered plugins in order; assert `MissionIsolationPlugin` is invoked between `AuditPlugin` and `AutonomyPlugin`
- [ ] T023 [US1] [P] In `tests/unit/test_plugins.py` — test: `PluginChain` calls `after_tool_callback` on all registered plugins in reverse order (or defined order per implementation)

---

## Phase 4 — US2: MissionContext + MISSION_ID

> Goal: implement the deterministic, Postgres-backed mission identity described in US2. Depends on T008 (Plugin ABC for type hints) and T009 (DB schema for sequence).

- [ ] T024 [US2] Write `core/mission.py` — define `MissionType` enum: `INCIDENT`, `MAINTENANCE`, `INVESTIGATION`, `REVIEW`
- [ ] T025 [US2] In `core/mission.py` — define `MissionStatus` enum: `OPEN`, `CLOSED`, `PARTIAL`
- [ ] T026 [US2] In `core/mission.py` — define `MissionContext` Pydantic v2 model with all FR-001 fields: `mission_id: str`, `tenant: str`, `env: str`, `cluster: str`, `type: MissionType`, `subject: str`, `status: MissionStatus`, `trigger_id: UUID | None`, `autonomy_level: str`, `created_at: datetime`; add `@field_validator('subject')` enforcing regex `^[a-z0-9]+(-[a-z0-9]+)*$` and max 30 chars (FR-002, SC-005)
- [ ] T027 [US2] In `core/mission.py` — implement `generate_mission_id(tenant: str, env: str, type: MissionType, subject: str, date: date, db_conn) -> str`: issues `INSERT INTO missions_seq (...) VALUES (...) ON CONFLICT DO UPDATE ... RETURNING seq` (or equivalent `SELECT ... FOR UPDATE` pattern) for atomic counter; formats result as `{TENANT}-{ENV}-{TYPE}-{SUBJECT}-{YYYYMMDD}-{SEQ:03d}` (FR-002, FR-008)
- [ ] T028 [US2] [P] Write `tests/unit/test_mission.py` — test: `generate_mission_id` returns correctly formatted string `ENTERPRISE-PREPROD-INCIDENT-PVC-SATURATION-20260510-001` for first call
- [ ] T029 [US2] [P] In `tests/unit/test_mission.py` — test: second call with identical parameters on same date returns `...-002` (sequential counter increments, SC-003 single-thread)
- [ ] T030 [US2] [P] In `tests/unit/test_mission.py` — test: SEQ zero-padding — counter 1 → `001`, counter 9 → `009`, counter 10 → `010` (format `{SEQ:03d}`)
- [ ] T031 [US2] [P] In `tests/unit/test_mission.py` — test: `MissionContext` rejects subject `"PVC Saturation"` (space → uppercase violation) with `ValidationError` (SC-005)
- [ ] T032 [US2] [P] In `tests/unit/test_mission.py` — test: `MissionContext` rejects subject `"pvc_saturation"` (underscore not allowed by regex) with `ValidationError` (SC-005)
- [ ] T033 [US2] [P] In `tests/unit/test_mission.py` — test: `MissionContext` rejects subject `"a" * 31` (exceeds 30 chars) with `ValidationError` (SC-005)
- [ ] T034 [US2] [P] In `tests/unit/test_mission.py` — test: `MissionContext` rejects subject `"-pvc"` (leading hyphen fails regex) with `ValidationError` (SC-005)
- [ ] T035 [US2] [P] In `tests/unit/test_mission.py` — test: `MissionContext` rejects subject `""` (empty string fails regex) with `ValidationError` (SC-005)
- [ ] T036 [US2] [P] In `tests/unit/test_mission.py` — test: concurrent MISSION_ID generation — `concurrent.futures.ThreadPoolExecutor(max_workers=10)` creates 10 missions with identical params; assert all 10 IDs are unique (SC-003)
- [ ] T037 [US2] [P] In `tests/unit/test_mission.py` — test: `MissionType` and `MissionStatus` enum coverage — all declared values are accessible and serializable via Pydantic

---

## Phase 5 — US3: TenantConfig + Hot Reload

> Goal: implement dynamic multi-env configuration and the admin reload route described in US3. Depends on T008 (Plugin ABC types), T012 (MissionIsolationPlugin reads TenantRegistry).

- [ ] T038 [US3] Write `core/tenant.py` — define `EnvConfig` Pydantic v2 model: `clusters: list[str]`, `kubeconfig: str`, `prom_url: str`, `vm_url: str`, `vault_path: str | None = None` (FR-007)
- [ ] T039 [US3] In `core/tenant.py` — define `TenantConfig` Pydantic v2 model: `tenant: str`, `envs: dict[str, EnvConfig]`; all fields required; Pydantic rejects YAML missing `prom_url` or `clusters` for any env (FR-006)
- [ ] T040 [US3] In `core/tenant.py` — implement `load_tenant(yaml_path: Path) -> TenantConfig`: reads YAML via `pyyaml`, instantiates `TenantConfig` — Pydantic raises `ValidationError` on invalid schema
- [ ] T041 [US3] In `core/tenant.py` — implement `load_tenants_dir(dir: Path) -> dict[str, TenantConfig]`: globs `*.yaml` in `dir`, calls `load_tenant()` for each, returns dict keyed by tenant name
- [ ] T042 [US3] In `core/tenant.py` — implement `TenantRegistry` singleton: holds `_configs: dict[str, TenantConfig]` under `threading.Lock`; exposes `get(tenant: str) -> TenantConfig`, `reload(dir: Path) -> dict[str, list[str]]` (atomically swaps configs under lock, returns `{tenant: [env_names]}` summary); raises `ValueError` on validation failure without modifying active config (FR-005, FR-006)
- [ ] T043 [US3] Write `api/routes/admin.py` — FastAPI router; implement `POST /admin/reload-tenants` endpoint: calls `TenantRegistry.reload(dir)`; on success returns HTTP 200 with `{"loaded": [...], "envs": {...}}`; on `ValidationError` or `ValueError` returns HTTP 400 with `{"errors": [...]}` without touching active config (FR-005, FR-006)
- [ ] T044 [US3] [P] Write `tests/unit/test_tenant.py` — test: `load_tenant()` from valid `enterprise.yaml` returns `TenantConfig` with `tenant="enterprise"` and `envs` containing `preprod`
- [ ] T045 [US3] [P] In `tests/unit/test_tenant.py` — test: `load_tenant()` from YAML missing required `prom_url` raises Pydantic `ValidationError`
- [ ] T046 [US3] [P] In `tests/unit/test_tenant.py` — test: `load_tenant()` from YAML missing required `clusters` raises Pydantic `ValidationError`
- [ ] T047 [US3] [P] In `tests/unit/test_tenant.py` — test: `TenantConfig` with `vault_path=None` (optional field) is valid — no `ValidationError`
- [ ] T048 [US3] [P] In `tests/unit/test_tenant.py` — test: multi-env YAML with 3 envs (`preprod`, `prod`, `rec`) parses all 3 `EnvConfig` entries correctly
- [ ] T049 [US3] Write `tests/integration/test_tenant_reload.py` — test: `POST /admin/reload-tenants` with valid YAML containing new env `rec` returns HTTP 200; assert `TenantRegistry.get("enterprise").envs` contains `rec` immediately after (SC-002)
- [ ] T050 [US3] [P] In `tests/integration/test_tenant_reload.py` — test: `POST /admin/reload-tenants` with invalid YAML (missing `prom_url`) returns HTTP 400; assert previous config is unchanged (FR-006)
- [ ] T051 [US3] [P] In `tests/integration/test_tenant_reload.py` — test: after reload adding env `rec`, a mission with `env=rec` calling a preprod `prom_url` is blocked by `MissionIsolationPlugin` (end-to-end US3 scenario 2)

---

## Phase 6 — Polish (AuditPlugin, AutonomyPlugin, full chain integration)

> Goal: complete the remaining plugin implementations referenced in `core/plugins.py` stubs, and add regression/integration coverage that crosses multiple components.

- [ ] T052 [P] In `core/audit.py` — implement `AuditPlugin`: `before_tool_callback` does nothing; `after_tool_callback` appends a JSON line to `audit.jsonl` with fields `mission_id`, `tool`, `result_summary`, `ts`; implement redaction list — any key in `tool_params` or `result` matching names in `REDACT_KEYS` (e.g. `password`, `token`, `secret`) is replaced with `"[REDACTED]"` before writing
- [ ] T053 [P] In `core/autonomy.py` — implement `AutonomyPlugin`: `before_tool_callback` checks `mission_context.autonomy_level`; if level is `L2`, block mutating tools (configurable list, default: `kubectl_apply`, `kubectl_delete`, `vault_write`, `care_sh`) by raising `AutonomyLevelExceeded` exception
- [ ] T054 [P] Write `tests/unit/test_plugins.py` — test: `AuditPlugin` writes correct JSON line to `audit.jsonl` after a tool call; assert all required keys present
- [ ] T055 [P] In `tests/unit/test_plugins.py` — test: `AuditPlugin` redacts `password` key in `tool_params` — output JSON contains `"[REDACTED]"` not the original value
- [ ] T056 [P] In `tests/unit/test_plugins.py` — test: `AuditPlugin` redacts `token` and `secret` keys in `tool_params`
- [ ] T057 [P] In `tests/unit/test_plugins.py` — test: `AutonomyPlugin` at `L2` blocks `kubectl_apply` with `AutonomyLevelExceeded`
- [ ] T058 [P] In `tests/unit/test_plugins.py` — test: `AutonomyPlugin` at `L2` blocks `kubectl_delete`, `vault_write`, `care_sh`
- [ ] T059 [P] In `tests/unit/test_plugins.py` — test: `AutonomyPlugin` at `L1` (read-only mission) does NOT block any tool call
- [ ] T060 [P] In `tests/integration/test_tenant_reload.py` — full plugin chain integration test: `PluginChain` with all 8 plugins processes a valid same-env tool call end-to-end without exception; assert `audit.jsonl` has one entry with correct `mission_id`

---

## Summary

| Phase | Tasks | Parallelizable | Blocking |
|-------|-------|----------------|---------|
| 1 — Setup | T001–T007 | All 7 | None |
| 2 — Foundational | T008–T009 | T009 only | T008 blocks all phases 3–6 |
| 3 — US1 MissionIsolationPlugin | T010–T023 | T015–T023 | T010–T014 sequential |
| 4 — US2 MissionContext + MISSION_ID | T024–T037 | T028–T037 | T024–T027 sequential |
| 5 — US3 TenantConfig + Hot Reload | T038–T051 | T044–T048, T050–T051 | T038–T043 sequential |
| 6 — Polish | T052–T060 | All 9 | None (stubs already exist) |
| **Total** | **60** | **38** | **22** |

### Critical Path

```
T008 (Plugin ABC)
  └── T010–T014 (MissionIsolationPlugin)
        └── T015–T023 (US1 tests)
T009 (DB DDL)
  └── T027 (generate_mission_id Postgres counter)
        └── T028–T036 (US2 tests)
T038–T042 (TenantConfig + TenantRegistry)
  └── T043 (POST /admin/reload-tenants)
        └── T049–T051 (US3 integration tests)
```

### Success Criteria Coverage

| SC | Covered by |
|----|-----------|
| SC-001: 100% cross-env tool calls blocked | T015, T016, T051 |
| SC-002: Reload <5s, no restart | T049 |
| SC-003: No duplicate MISSION_IDs under 10 concurrent creations | T036 |
| SC-004: <50ms overhead per tool call | T021 |
| SC-005: Invalid subject slugs rejected | T031–T035 |
