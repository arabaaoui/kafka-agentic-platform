# Feature Specification: GKE Auth & GSA Impersonation

**Feature Branch**: `007-gke-auth-impersonation`
**Created**: 2026-05-14
**Status**: Implemented
**Scope**: Multi-cluster connectivity, Identity-based access

---

## Executive Summary
This specification defines the cross-cluster authentication mechanism used by the platform to allow agents (running in a central "Lab" project) to securely investigate Kubernetes clusters in remote environments (Dev, Rec, Preprod, Prod) without VPC peering or shared secrets.

The core solution relies on **Google Service Account (GSA) Impersonation**. A central "Master" identity (the Platform GSA) is granted rights to act as environment-specific identities (Environment GSAs) which possess the required RBAC roles on their respective GKE clusters.

---

## Architecture

### Components
1.  **Platform Master GSA**: The identity under which the backend container runs (Workload Identity in GKE, User ADC locally).
2.  **Environment GSA**: A dedicated GSA per environment (e.g., `phenix-dev-reader@...`) with `view` or `edit` RBAC roles on the target cluster.
3.  **Token Provider (`core/gcp.py`)**: A centralized module responsible for fetching short-lived access tokens for a target Environment GSA by impersonating it using the Master GSA.

### Data Flow
1.  Backend receives an alert for a specific environment (e.g., `dev`).
2.  Agents are spawned with the `EnvironmentConfig` for `dev`.
3.  When an agent calls a tool (e.g., `kubectl`), `BaseAgent` uses `GCPTokenProvider.get_token(target_gsa_email)` to get a token for the `dev` GSA.
4.  The token is injected into a temporary `kubeconfig` used for that specific tool call.

---

## Prerequisites (GCP IAM)

### 1. Master Identity
*   **Project**: `phenix-lab`
*   **GSA**: `kafka-agentic-platform@phenix-lab.iam.gserviceaccount.com`

### 2. Environment Identities (Example for DEV)
*   **Project**: `phenix-dev`
*   **GSA**: `phenix-dev-reader@phenix-dev.iam.gserviceaccount.com`
*   **Permissions**: `roles/container.viewer` (at project level) or specific RBAC `ClusterRole`.

### 3. Trust Link (Impersonation)
In the target project (DEV), grant the Master GSA the following role on the Environment GSA:
*   **Role**: `roles/iam.serviceAccountTokenCreator`
*   **Member**: `serviceAccount:kafka-agentic-platform@phenix-lab.iam.gserviceaccount.com`

---

## Commands Reference

### GCP Configuration (Admin)
```bash
# Grant impersonation right
gcloud iam service-accounts add-iam-policy-binding \
    phenix-dev-reader@phenix-dev.iam.gserviceaccount.com \
    --member="serviceAccount:kafka-agentic-platform@phenix-lab.iam.gserviceaccount.com" \
    --role="roles/iam.serviceAccountTokenCreator"
```

### Local Development Setup
Since developers run the platform on their local PC, their personal identity acts as the "Master GSA".
1.  **Login**: `gcloud auth application-default login`
2.  **Volume Mount**: The `.env` and `docker-compose.yml` must mount the ADC file:
    ```yaml
    volumes:
      - ~/.config/gcloud:/root/.config/gcloud-host:ro
    environment:
      - GOOGLE_APPLICATION_CREDENTIALS=/root/.config/gcloud-host/application_default_credentials.json
    ```
3.  **Permissions**: The developer's Enterprise email must be granted `roles/iam.serviceAccountTokenCreator` on the Environment GSAs.

---

## Security Guardrails
*   **Short-lived Tokens**: Tokens generated via impersonation expire after 1 hour by default (requested for 3600s in code).
*   **No JSON Keys**: No static service account keys are stored in the codebase or database.
*   **Mission Isolation**: The `MissionIsolationPlugin` ensures an agent only impersonates the GSA corresponding to the mission's environment.
