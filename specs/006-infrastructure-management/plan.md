# Implementation Plan: Dynamic Infrastructure & GKE SA Key

**Branch**: `006-infrastructure-management` | **Date**: 2026-05-13 | **Spec**: /specs/006-infrastructure-management/spec.md
**Input**: Feature specification from `/specs/006-infrastructure-management/spec.md`

## Summary

Implement dynamic environment management with GCP Service Account support. The backend will use a hybrid approach: loading from YAML at startup and overlaying database-stored overrides. Service Account keys provided as JSON will be managed by the platform and injected into agent tool execution.

## Technical Context

**Language/Version**: Python 3.11, Next.js 14.2  
**Primary Dependencies**: FastAPI, SQLAlchemy, Alembic, Tailwind, Lucide-react  
**Storage**: PostgreSQL (InfrastructureEnv table)  
**Testing**: Manual E2E (Simulated alerts)

## Project Structure

### Documentation (this feature)

```text
specs/006-infrastructure-management/
├── spec.md              # Requirement specification
├── plan.md              # This file
├── tasks.md             # Detailed implementation steps
```

### Source Code Impact

```text
backend/
├── api/
│   ├── routes/infrastructure.py # NEW: CRUD endpoints
│   ├── schemas.py               # Updated: Infra schemas
├── core/
│   ├── models.py                # Updated: InfrastructureEnv table
│   ├── tenant.py                # Updated: registry with DB overrides
│   ├── mission_isolation.py     # Potential update for SA key injection

frontend/
├── components/
│   ├── EnvModal.tsx             # NEW: Form for environment settings
├── app/settings/tenants/
│   ├── page.tsx                 # Updated: real CRUD operations
```

## Phase 1: Database & Core Logic
1.  **Add `InfrastructureEnv` model** in `core/models.py`.
2.  **Generate Alembic migration** and apply to DB.
3.  **Enhance `TenantRegistry`** in `core/tenant.py` to allow dynamic overrides via `add_env_override` and `remove_env_override`.
4.  **Update startup lifespan** in `api/main.py` to load DB overrides into the registry.

## Phase 2: API Endpoints
1.  **Create `api/routes/infrastructure.py`** with GET, POST (upsert), and DELETE.
2.  **Ensure `SystemAudit`** is updated on every infra modification.
3.  **Implement SA Key File persistence**: When a `gcp_sa_key` is saved, write it to `/app/kube_conf/{tenant}_{slug}_sa.json`.

## Phase 3: Agent Auth Injection
1.  **Update `BaseAgent.run`** or tool wrappers: if `mission.env` has a `gcp_sa_key` file, set `GOOGLE_APPLICATION_CREDENTIALS` for that environment before running tools. *Challenge: Parallel execution task-safety*.
2.  **Recommended approach**: Tools in `kafka-agent-toolkit` (like `cluster_health_check`) should be called with an explicit `gcp_sa_key_path`.

## Phase 4: UI Development
1.  **Develop `EnvModal.tsx`** with fields for Clusters, Kubeconfig, and a Textarea for the GCP SA JSON.
2.  **Update `web/app/settings/tenants/page.tsx`** to connect with real API endpoints and use the new modal.
