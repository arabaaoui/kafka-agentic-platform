# Feature Specification: Dynamic Infrastructure & GKE GSA Impersonation

**Feature Branch**: `006-infrastructure-management`  
**Created**: 2026-05-13  
**Status**: Implemented  
**Amended**: 2026-05-18 — Aligned with spec-007 (GKE auth impersonation). Static JSON key storage removed; replaced by `target_gsa_email` + `GCPTokenProvider` impersonation. See `docs/architecture/GKE_AUTH_GUIDE.html` for the full auth flow.  
**Input**: User description: "Add support for configuring GKE Service Account credentials in the infrastructure environment configuration. Connection to GKE must be done via an account configured in the env, then the platform manages this directly or via a Kubeconfig."

## User Scenarios & Testing

### User Story 1 - Dynamic Environment Configuration (Priority: P1)

An SRE needs to add a new lab environment without access to the backend source code or redeploying. They use the "Infrastructure" menu to add an environment with its name, clusters, and Prometheus URL.

**Why this priority**: Core requirement for platform scalability and ease of use.

**Independent Test**: Can be fully tested by creating a new environment in the UI and verifying it appears in the active mission intake selection.

**Acceptance Scenarios**:

1. **Given** an authenticated admin, **When** they fill the "Add Environment" form with valid data, **Then** a new entry is created in the `infrastructure_envs` table and immediately available in the UI.
2. **Given** a YAML-defined environment, **When** a user creates a DB override with the same slug, **Then** the DB configuration takes precedence in the mission worker.

---

### User Story 2 - GKE Service Account Authentication via Impersonation (Priority: P2)

An engineer wants to connect the platform to a new GKE cluster using a dedicated Google Service Account (GSA). They enter the GSA email in the environment configuration. The platform uses `GCPTokenProvider` to impersonate this GSA and inject an ephemeral token per tool call. No static JSON key is stored anywhere (DB, disk, or code) — see spec-007 and `docs/architecture/GKE_AUTH_GUIDE.html`.

**Why this priority**: Security best practice (zero static secrets, isolated credentials per env) and constitution principle V (Zero Secret Leakage).

**Independent Test**: Configure `target_gsa_email` for a test environment, run `cluster_health_check` via a mission, confirm successful connectivity without any JSON key.

**Acceptance Scenarios**:

1. **Given** an environment with a `target_gsa_email` configured, **When** an agent runs a tool (e.g., `cluster_health_check`), **Then** `GCPTokenProvider.get_token(target_gsa_email)` is called and an ephemeral Bearer token is injected into a temporary kubeconfig.
2. **Given** an empty `target_gsa_email`, **When** an agent runs a tool, **Then** it falls back to ADC (Application Default Credentials — `gcloud auth application-default login` for local dev; Workload Identity in GKE).
3. **Given** any environment, **When** a tool call completes, **Then** no token, key, or credential persists on disk beyond the scope of the call.

---

### User Story 3 - Infrastructure Audit Trail (Priority: P3)

The platform lead wants to know who changed an environment configuration.

**Why this priority**: Governance and traceability (Carrefour engineering standards).

**Independent Test**: Modify an environment and check the "Admin Audit" menu for the corresponding `UPDATE_INFRA_ENV` entry.

**Acceptance Scenarios**:

1. **Given** a change to an environment, **When** saved, **Then** a `SystemAudit` entry is created with the old and new values.

## Requirements

### Functional Requirements

- **FR-001**: System MUST allow CRUD operations on infrastructure environments via the UI.
- **FR-002**: System MUST store `target_gsa_email` (GSA email string) per environment. No static JSON key is stored anywhere. *(Amended 2026-05-18: replaced gcp_sa_key with target_gsa_email per spec-007)*
- **FR-003**: System MUST persist dynamic configurations in a new `infrastructure_envs` table.
- **FR-004**: System MUST allow deleting dynamic overrides to restore original YAML configurations.
- **FR-005**: System MUST log all infrastructure changes to `system_audit`.
- **FR-006**: Mission worker MUST use `GCPTokenProvider.get_token(target_gsa_email)` (if configured) to inject an ephemeral token per tool execution. Falls back to ADC if empty.

### Key Entities

- **InfrastructureEnv**: Represents a dynamic environment configuration. Attributes: `tenant`, `slug`, `display_name`, `badge_color`, `clusters`, `kubeconfig`, `kubeconfig_content`, `kube_context`, `target_gsa_email`, `kafka_namespace`, `prom_url`, `alertmanager_url`, `proxy_url`, `vm_url`. No `gcp_sa_key` field.
- **SystemAudit**: Traces actions on infrastructure resources.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Users can add a new environment in under 30 seconds via the UI.
- **SC-002**: 100% of infrastructure changes are visible in the Admin Audit trail.
- **SC-003**: Agents can connect to GKE using `target_gsa_email` impersonation without any static credential stored in the system.

## Assumptions

- In production (GKE): the Platform Master GSA must have `roles/iam.serviceAccountTokenCreator` on each environment's GSA.
- In local dev: `gcloud auth application-default login` provides ADC — no JSON key required.
- Kubeconfig content (if provided) is stored encrypted in `kubeconfig_content` and materialized as a temp file at startup; tokens are always refreshed per call via `GCPTokenProvider`.
