# Feature Specification: Mission Isolation (Multi-Env, Plugin-Enforced)

**Feature Branch**: `003-mission-isolation`
**Created**: 2026-05-10
**Status**: Approved
**Scope**: v0 — critical safety requirement, enforced by plugin

---

## User Scenarios & Testing

### User Story 1 — Mission Locked to Env at Creation (Priority: P1)

A mission for a preprod incident is created with `env=preprod`. The `MissionIsolationPlugin` is activated for this mission. Any subsequent tool call that would query a prod endpoint (e.g., `prom_query` with `prom_url=http://prometheus.prod/...`) is automatically blocked, logged, and surfaced in the UI — without the agent needing to check manually.

**Why this priority**: This is a safety requirement (constitution rule II). Without it, an agent investigating a preprod incident could accidentally query prod data, leading to misleading analysis or (in future versions with write tools) prod impact.

**Independent Test**: Can be tested in isolation by creating a mission with `env=preprod`, then calling `tool_call("prom_query", {"prom_url": "http://prometheus.prod..."})` via the ADK test harness. Expected: `MissionIsolationPlugin.before_tool_callback` raises `CrossEnvAccessBlocked` exception, logged to `audit.jsonl`.

**Acceptance Scenarios**:

1. **Given** a mission with `env=preprod`, **When** any tool call is made, **Then** `MissionIsolationPlugin.before_tool_callback` resolves the target endpoint from `tenant_config.envs` and verifies it belongs to `preprod`.
2. **Given** a tool call targeting a `prod` endpoint while `mission.env=preprod`, **Then** the call is blocked, an audit entry is written (`{ event: "cross_env_blocked", mission_id: ..., tool: ..., target_env: "prod", mission_env: "preprod" }`), and the UI displays a "Blocked access attempt" badge on the mission card.
3. **Given** a tool call targeting a `preprod` endpoint while `mission.env=preprod`, **Then** the call proceeds normally.
4. **Given** a mission with `env=prod`, **When** a tool call targets a preprod endpoint, **Then** the call is also blocked (isolation is bidirectional).

---

### User Story 2 — MISSION_ID Format and Traceability (Priority: P1)

Every mission has a unique ID in the format `{TENANT}-{ENV}-{TYPE}-{SUBJECT}-{YYYYMMDD}-{SEQ:03d}` (e.g., `CARREFOUR-PREPROD-INCIDENT-PVC-SATURATION-20260510-001`). The ID is used in all audit logs, file paths, and Jira comments for full traceability.

**Acceptance Scenarios**:

1. **Given** a mission creation request with `tenant=carrefour`, `env=preprod`, `type=incident`, `subject=pvc-saturation`, `date=2026-05-10`, **When** this is the first mission of the day with this pattern, **Then** the assigned ID is `CARREFOUR-PREPROD-INCIDENT-PVC-SATURATION-20260510-001`.
2. **Given** a second mission with identical parameters on the same day, **When** created, **Then** its ID is `CARREFOUR-PREPROD-INCIDENT-PVC-SATURATION-20260510-002` (sequential counter).
3. **Given** a mission ID, **When** looking for related files, **Then** `audit.jsonl` entries, `agent-outputs/` files, and `missions/` Postgres row all use the exact same `mission_id` value.

---

### User Story 3 — Multi-Env Dynamic Configuration (Priority: P2)

The operator adds a new environment `rec` to `tenants/carrefour.yaml` (with its cluster endpoints, kubeconfig, prom_url). No code change is required. On next API reload, missions for `env=rec` are correctly isolated to rec endpoints.

**Acceptance Scenarios**:

1. **Given** `tenants/carrefour.yaml` has a new entry `rec: { clusters: [...], prom_url: ..., vm_url: ..., kubeconfig: ... }`, **When** `POST /admin/reload-tenants` is called, **Then** `tenant_config.envs` in memory includes `rec` and `MissionIsolationPlugin` enforces isolation for `env=rec`.
2. **Given** a mission `env=rec` after reload, **When** a tool targets `prom_url` of `preprod`, **Then** it is blocked.
3. **Given** an invalid `tenants/carrefour.yaml` (missing required field `prom_url` for an env), **When** reload is attempted, **Then** the API returns a 400 with validation errors and the previous config stays active.

---

### Edge Cases

- What if `intake_agent` assigns `env=unknown` because the ticket had no clear env marker? → Mission creation is aborted. Trigger logged as "rejected: env_ambiguous". The user can manually create a mission from `/triggers/ignored` with explicit env selection.
- What if the kubeconfig for the target env is expired or unreachable? → Tool call fails with a user-visible error in the UI. Mission continues (partial audit is acceptable). `cluster_health` returns "UNREACHABLE" status for that cluster.
- What if `tenants/carrefour.yaml` grows to 10+ envs? → The plugin does O(n) lookup through envs dict — acceptable for ≤20 envs. Beyond that, a Postgres-backed env registry will be considered (v1).
- What if two tenants are deployed (future multi-tenant) and a mission of tenant A tries to reach a cluster of tenant B? → `MissionIsolationPlugin` also checks `tenant` on every tool call. Cross-tenant access is blocked.

---

## Requirements

### Functional Requirements

- **FR-001**: `MissionContext` Pydantic model MUST include: `mission_id: str`, `tenant: str`, `env: str`, `cluster: str`, `type: MissionType`, `subject: str`, `status: MissionStatus`, `trigger_id: UUID | None`, `autonomy_level: str`, `created_at: datetime`.
- **FR-002**: `MISSION_ID` MUST follow the pattern `{TENANT}-{ENV}-{TYPE}-{SUBJECT}-{YYYYMMDD}-{SEQ:03d}` where `SUBJECT` is kebab-case (validated by regex `^[a-z0-9]+(-[a-z0-9]+)*$`, max 30 chars).
- **FR-003**: `MissionIsolationPlugin.before_tool_callback` MUST resolve the target env of every tool call by matching tool parameters against `tenant_config.envs[env].endpoints`. Calls not targeting any configured endpoint are allowed by default (e.g., MCP `c4-atlassian` is not env-specific).
- **FR-004**: Cross-env tool calls MUST raise `CrossEnvAccessBlocked` exception (caught by `ErrorHandlerPlugin`), logged to `audit.jsonl`, and surfaced as a mission event in SSE stream.
- **FR-005**: `tenant_config.yaml` MUST be reloadable at runtime via `POST /admin/reload-tenants` without server restart.
- **FR-006**: `tenant_config.yaml` schema MUST be validated (Pydantic) on every reload. Invalid config MUST be rejected without affecting the running config.
- **FR-007**: `tenant_config.yaml` MUST support dynamic env list (N envs, added without code change). Required per-env fields: `clusters: list[str]`, `kubeconfig: str`, `prom_url: str`, `vm_url: str`, `vault_path: str` (optional for v0 lab).
- **FR-008**: The sequential counter in `MISSION_ID` MUST be sourced from Postgres (atomic `SELECT ... FOR UPDATE`) to prevent duplicates under concurrent mission creation.

### Key Entities

- **MissionContext**: Python Pydantic model (in `core/mission.py`), primary runtime object passed to all agents and plugins.
- **TenantConfig**: Python Pydantic model loaded from `tenants/{tenant}.yaml` (in `core/tenant.py`). Contains `tenant: str`, `envs: dict[str, EnvConfig]`.
- **EnvConfig**: `clusters: list[str]`, `kubeconfig: str`, `prom_url: str`, `vm_url: str`, `vault_path: str | None`.

---

## Success Criteria

- **SC-001**: 100% of cross-env tool call attempts are blocked and logged (verified by E2E test covering all 5 tools).
- **SC-002**: Adding a new env to `tenants/carrefour.yaml` + calling `POST /admin/reload-tenants` takes effect within 5 seconds, no restart.
- **SC-003**: `MISSION_ID` sequential counter produces no duplicates under 10 concurrent mission creations (load test).
- **SC-004**: `MissionIsolationPlugin` adds <50ms overhead per tool call (benchmark in CI).
- **SC-005**: `MISSION_ID` subject field rejects invalid slugs: `re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$', subject)` — regression test for bug observed in `gemini-kafka-ops-extension` (slug leaked YAML comment).

---

## Assumptions

- Each Kafka environment (preprod, prod, rec, dev) has distinct, non-overlapping Prometheus URLs, Vault paths, and kubeconfig files. The plugin relies on URL prefix matching to determine target env.
- `k_exec` (kubectl wrapper tool) derives env from `mission.env`-specific kubeconfig, not from a parameter. No explicit env parameter in tool signature.
- MCP `c4-atlassian` (Jira) and MCP GitLab are considered "env-agnostic" — they are not blocked by `MissionIsolationPlugin` since they don't target cluster-specific endpoints.
- `care.sh` calls (post-v0) will have an explicit `env` parameter (`prod` or `preprod`) derived from `mission.env` by the wrapper.
