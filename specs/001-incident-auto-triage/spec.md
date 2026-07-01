# Feature Specification: Incident Auto-Triage (v0 Core)

**Feature Branch**: `001-incident-auto-triage`
**Created**: 2026-05-10
**Status**: Approved
**Scope**: v0 — read-only, autonomy L2

---

## User Scenarios & Testing

### User Story 1 — Automatic Incident Detection & Audit (Priority: P1)

A Kafka incident occurs in the preprod environment (PVC saturation on broker-2). The OS detects it via the Jira poller (ticket assigned to the user matches the active filter rules), automatically creates an isolated mission locked to the preprod environment, dispatches 3 expert agents in parallel (kafka_strimzi_expert, k8s_gcp_sre, prom_alerts_triage), synthesizes contradictions via `evidence_consolidator`, and delivers a ranked-hypotheses audit Markdown in the UI within 5 minutes. No action is taken on the infrastructure.

**Why this priority**: This is the single killer feature of v0. Every other user story depends on this flow working correctly.

**Independent Test**: Can be fully tested using a mocked Jira webhook payload (PHX-99999 incident PVC saturation, assignee=ops-user, env=preprod) against the lab Docker stack (Strimzi 0.45.1 KRaft). Delivers value as a standalone feature: the user sees the full ranked audit without manual investigation.

**Acceptance Scenarios**:

1. **Given** a Jira ticket PHX-99999 (issuetype=Incident, assignee=ops-user, project=PHX, status=Open), **When** the Jira poller runs against the active filter rule, **Then** a mission `ENTERPRISE-PREPROD-INCIDENT-PVC-SATURATION-20260510-001` is created within 60 seconds.
2. **Given** a created mission, **When** `intake_agent` parses the ticket, **Then** it correctly identifies env=preprod, cluster=kafka-preprod, pattern=PVC_SATURATION and locks the mission to preprod endpoints only.
3. **Given** a locked mission, **When** `ParallelAgent` runs the 3 experts, **Then** all 3 complete within 4 minutes and their outputs appear in `agent-outputs/`.
4. **Given** 3 expert outputs, **When** `evidence_consolidator` runs in thinking mode, **Then** it produces `audit.md` with at least 2 ranked hypotheses, evidence sections, and recommended actions.
5. **Given** a generated `audit.md`, **When** the user opens `/missions/{id}` in the UI, **Then** the audit is fully visible with ENV badge=PREPROD and toggle "Post to Jira" in OFF state.
6. **Given** a completed mission, **When** a tool call targets a prod endpoint while `mission.env=preprod`, **Then** `MissionIsolationPlugin` blocks the call, logs to audit JSONL, and the UI shows the blocked attempt.

---

### User Story 2 — Alertmanager Webhook Trigger (Priority: P2)

The alertmanager fires a `KafkaBrokerDown` alert for cluster `kafkahub-preprod`, severity=critical. The webhook endpoint receives the payload, the filter engine matches it against the alertmanager rule, and a mission is created for the correct env.

**Why this priority**: Provides real-time trigger without waiting for Jira ticket creation. Faster TTR for PROD/PREPROD incidents.

**Independent Test**: Testable with `curl -X POST localhost:8000/v1/triggers/alertmanager -d @tests/fixtures/alert-broker-down-preprod.json`. No Jira dependency.

**Acceptance Scenarios**:

1. **Given** a webhook payload `{ "alertname": "KafkaBrokerDown", "cluster": "kafkahub-preprod", "severity": "critical" }`, **When** it hits `POST /v1/triggers/alertmanager`, **Then** the filter engine matches it against an active alertmanager rule and creates a mission within 10 seconds.
2. **Given** a webhook payload for cluster `kafkahub-prod` without an active alertmanager rule for prod, **When** received, **Then** it is logged to `filter_match_log` as "rejected: no matching rule" and visible in `/triggers/ignored`.

---

### User Story 3 — Explicit Post to Jira (Priority: P3)

After reviewing the audit in the UI, the team member explicitly clicks "Post to Jira" on a completed mission. The audit summary (3-line executive summary + ranked hypotheses table) is posted as a comment on the originating Jira ticket via MCP `c4-atlassian`.

**Why this priority**: Closes the loop with Jira without automating it. Team retains control over what gets posted.

**Independent Test**: Testable via `POST /v1/missions/{id}/post-to-jira` with mocked MCP `c4-atlassian`. Verifiable by checking mock MCP call log for `jira_add_comment`.

**Acceptance Scenarios**:

1. **Given** a completed mission with `audit.md`, **When** `POST /v1/missions/{id}/post-to-jira` is called (UI toggle), **Then** MCP `c4-atlassian` `jira_add_comment` is invoked with the formatted audit summary.
2. **Given** a mission where "Post to Jira" was NOT toggled, **When** the mission is completed, **Then** no `jira_add_comment` call is made (verified via audit JSONL).

---

### Edge Cases

- What happens when `intake_agent` cannot determine the environment from the ticket? → Mission creation is aborted, trigger logged as "rejected: env_ambiguous", visible in `/triggers/ignored`.
- What happens when all 3 parallel expert agents fail? → `evidence_consolidator` receives empty inputs and produces a "Partial audit — all experts failed" report; mission is flagged `status=partial`.
- What happens when `evidence_consolidator` produces contradictory ranked hypotheses with equal confidence? → Both are listed in the audit with a "Conflict detected" banner.
- What happens when MCP `c4-atlassian` is unavailable during "Post to Jira"? → Action fails with a user-visible error in the UI; retry is available; no silent failure.
- What happens when a trigger matches multiple active filter rules? → First matching rule (by priority asc) wins; all match results logged to `filter_match_log`.

---

## Requirements

### Functional Requirements

- **FR-001**: System MUST detect new Jira tickets matching active filter rules within `poll_interval_seconds` (default: 60s).
- **FR-002**: System MUST detect alertmanager webhook payloads and match them against active alertmanager filter rules within 10 seconds.
- **FR-003**: `intake_agent` MUST determine `env` and `cluster` from trigger payload before creating a mission. Mission MUST NOT be created if env is ambiguous.
- **FR-004**: `MissionIsolationPlugin` MUST block any tool call targeting an endpoint outside `mission.env`, log the attempt to audit JSONL, and surface it in the UI.
- **FR-005**: `ParallelAgent` MUST run `kafka_strimzi_expert`, `k8s_gcp_sre`, and `prom_alerts_triage` concurrently (not sequentially).
- **FR-006**: `evidence_consolidator` MUST produce `audit.md` with ranked hypotheses, evidence references, and ≥3 recommended actions within 4 minutes of expert completion.
- **FR-007**: `audit.md` MUST be accessible in the UI at `/missions/{id}` with ENV badge, agent status, and toggle "Post to Jira" (default OFF).
- **FR-008**: "Post to Jira" action MUST call MCP `c4-atlassian` `jira_add_comment` only on explicit user action (UI toggle or API call). Never automatic.
- **FR-009**: All tool calls MUST be logged to `audit.jsonl`. Zero secret/password/token in audit log (grep test automated in CI).
- **FR-010**: All agent traces MUST appear in Langfuse (costs, tokens, latencies per agent per mission).
- **FR-011**: System MUST handle MCP `c4-atlassian` unavailability gracefully (circuit breaker + retry + user-visible error, no silent failure).
- **FR-012**: Trigger payloads that match no active rule MUST be logged to `filter_match_log` as "rejected" with reason, visible in `/triggers/ignored`.
- **FR-013**: `Mem0MemoryPlugin` MUST search `kb/incidents/` for the top-3 cards most relevant to the current mission (scored by token overlap on `mission.subject + mission.type`) and inject them as a KB context block prepended to the first tool result of each mission. If no card scores > 0, no injection occurs. Injection is idempotent per mission (once per `mission_id`).
- **FR-014**: Agent SKILL.md files for `kafka_strimzi_expert` and `k8s_gcp_sre` MUST include the full PromQL library used in the Gemini extension (≥10 queries each), the PromQL critical rule (`container!=""` on `container_*` metrics), a severity matrix with explicit thresholds, and a cross-reference section listing escalation paths to sibling agents.

### Key Entities

- **Mission**: Isolated unit of work, env-locked. Fields: `id (MISSION_ID)`, `tenant`, `env`, `cluster`, `type`, `subject`, `status`, `trigger_id`, `created_at`, `closed_at`.
- **Trigger**: Incoming event from Jira/alertmanager/Care. Fields: `id`, `source`, `raw_payload`, `matched_rule_id`, `mission_id`, `status (matched|rejected)`, `received_at`.
- **FilterRule**: Routing rule (Postgres). Fields: `id`, `tenant`, `scope`, `name`, `enabled`, `priority`, `poll_interval_seconds`, `criteria (JSONB)`.
- **Audit**: Generated report per mission. Fields: `id`, `mission_id`, `file_path`, `posted_to_jira`, `posted_at`, `created_at`.
- **AgentOutput**: Individual expert report. Fields: `id`, `mission_id`, `agent_name`, `file_path`, `status`, `created_at`.

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: Mission created within 60s of Jira poll cycle finding a matching ticket.
- **SC-002**: `audit.md` generated and visible in UI within 5 minutes of mission creation (for PVC saturation / Prometheus false positive patterns).
- **SC-003**: Zero automatic Jira comments posted without explicit user action (verified by audit JSONL grep for `jira_add_comment` without corresponding user action).
- **SC-004**: Zero cross-env tool calls succeed when `MissionIsolationPlugin` is active (verified by E2E test).
- **SC-005**: Eval suite ≥80% on 15 calibrated cases (5 lag, 3 promrule, 4 pvc, 3 consolidation).
- **SC-006**: Langfuse trace present for every mission (100% coverage, verified by Langfuse API query).
- **SC-007**: Zero secret/password/token in `audit.jsonl` (grep CI test).
- **SC-008**: On a PVC saturation mission (`subject=pvc-saturation`), `Mem0MemoryPlugin` injects at least one card from `{pvc-config-drift, zookeeper-orphaned-pvc-post-kraft, fragmentation-saturation-promotions}` (verified by checking `_kb_context` key in first tool result); `evidence_consolidator` output references the injected card slug in the audit (grep test).
- **SC-009**: `kafka_strimzi_expert` output MUST include a filled severity matrix table (Lag / URP / ISR / Election Rate rows with numeric thresholds) and a cross-reference section — verified by grep in generated `audit.md`.

---

## Assumptions

- MCP `c4-atlassian` is available and configured with the same credentials as `gemini-kafka-ops-extension`. No new Jira auth setup required.
- The lab Docker stack (Strimzi 0.45.1 KRaft + Prometheus) is sufficient to validate 80% of tools. The remaining 20% (MM2, Connect, SCRAM, ACL) require preprod access.
- `intake_agent` can determine `env` from Jira ticket metadata (custom fields, labels, or ticket summary) for Enterprise tickets. A fallback regex on summary text is acceptable for v0.
- `kafka-agent-toolkit` is published to the internal GitLab pip registry before this spec's tools are used in platform agents.
- Langfuse self-hosted is accessible at `localhost:3001` in local dev and at a stable internal URL in preprod/prod.
- User (ops-user) has read-only kubeconfig for preprod clusters during dogfooding phase.
