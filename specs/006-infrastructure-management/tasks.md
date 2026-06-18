# Tasks: Dynamic Infrastructure & GKE SA Key

Feature branch: `006-infrastructure-management`

## Phase 1: Persistence & Core (Database)

- [ ] **DB-001**: Add `InfrastructureEnv` model in `core/models.py`.
- [ ] **DB-002**: Generate Alembic migration: `uv run alembic revision --autogenerate -m "add infrastructure_envs and gcp_sa_key"`.
- [ ] **DB-003**: Apply migration: `uv run alembic upgrade head`.
- [ ] **CORE-001**: Update `EnvConfig` in `core/tenant.py` with `gcp_sa_key`.
- [ ] **CORE-002**: Implement `TenantRegistry.add_env_override` and `remove_env_override`.
- [ ] **CORE-003**: Update `api/main.py` lifespan to load `InfrastructureEnv` records into `TenantRegistry` on startup.

## Phase 2: API & Logic

- [ ] **API-001**: Define `InfrastructureEnvCreate` and `InfrastructureEnvResponse` in `api/schemas.py`.
- [ ] **API-002**: Implement `GET /v1/infrastructure/tenants` (merging YAML + DB).
- [ ] **API-003**: Implement `POST /v1/infrastructure/tenants/{tenant}/envs/{slug}` (Upsert).
- [ ] **API-004**: Implement `DELETE /v1/infrastructure/tenants/{tenant}/envs/{slug}`.
- [ ] **API-005**: Add logic to write `gcp_sa_key` content to `/app/kube_conf/{tenant}_{slug}_sa.json` when saved.
- [ ] **API-006**: Ensure all CRUD actions are logged via `SystemAudit`.

## Phase 3: Infrastructure Auth Integration

- [ ] **AUTH-001**: Update `MissionIsolationPlugin` or `BaseAgent` to detect `gcp_sa_key` file.
- [ ] **AUTH-002**: Inject `GOOGLE_APPLICATION_CREDENTIALS` for that file during tool execution (task-scoped).

## Phase 4: Frontend (UI)

- [ ] **UI-001**: Implement `EnvModal.tsx` for environment creation/editing.
- [ ] **UI-002**: Integrate real API calls in `web/app/settings/tenants/page.tsx`.
- [ ] **UI-003**: Add "Add Environment", "Edit", and "Delete" actions.
- [ ] **UI-004**: Handle SA Key JSON input (textarea with validation).
