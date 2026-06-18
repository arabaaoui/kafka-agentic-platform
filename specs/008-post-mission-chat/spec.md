# Feature Specification: Post-Mission Chat

**Feature Branch**: `008-post-mission-chat`  
**Created**: 2026-05-18  
**Status**: Draft  
**Scope**: v0.6 — Interactive refinement of mission analysis

---

## User Scenarios & Testing

### User Story 1 — Refine Analysis via Chat (Priority: P1)

After a mission is completed (e.g. `CLOSED` or `PARTIAL`), the user wants to ask follow-up questions to the agents (e.g., "Why did you think the PVC was the root cause?" or "Can you show me the logs for pod X again?"). The user opens the mission in the UI, types a message in the chat box, and the orchestrator (or a specific expert) responds based on the mission's history and live data.

**Why this priority**: Transition from static reports to a collaborative "team of agents" experience. Crucial for trust and deep-dive investigations.

**Independent Test**: Start a chat on a `CLOSED` mission, send a message, verify the mission status changes to `CLARIFYING`, and receive a response that mentions data from the original audit.

**Acceptance Scenarios**:

1. **Given** a mission in `CLOSED` status, **When** the user sends the first chat message, **Then** the mission status changes to `CLARIFYING`.
2. **Given** a chat message, **When** the IA responds, **Then** the response is persisted in the database and visible in the UI chat thread.
3. **Given** multiple expert agents, **When** the user asks a specific question (e.g., "Kafka Expert, check topic X"), **Then** the orchestrator routes the request to the correct expert agent.

---

### User Story 2 — Preservation of Mission Context (Priority: P1)

The chat must remain strictly isolated to the mission's environment. If a mission was created for `dev`, the agents in the chat must NOT be able to query `prod`, even if the user explicitly asks for it in the chat.

**Why this priority**: Security and consistency. The `MissionIsolationPlugin` must remain the hard boundary.

**Acceptance Scenarios**:

1. **Given** a chat session for a `dev` mission, **When** the user asks "Check status in prod", **Then** the `MissionIsolationPlugin` blocks the tool call and the agent explains the restriction.
2. **Given** an ongoing chat, **When** an agent uses a tool, **Then** it uses the same GSA impersonation target (`mission.gsa_email`) as the original mission — tokens are re-minted per call by `GCPTokenProvider` (not cached from mission creation).

---

### User Story 3 — Manual Mission Re-Closure (Priority: P2)

Once the user is satisfied with the follow-up exchange, they can manually close the mission again. This figes the analysis and might trigger an update to the final `audit.md`.

**Acceptance Scenarios**:

1. **Given** a mission in `CLARIFYING` status, **When** the user clicks "Approve & Close", **Then** the mission returns to `CLOSED` status.
2. **Given** a re-closed mission, **When** the final `audit.md` is viewed, **Then** it includes (or links to) the relevant insights from the chat.

---

### Edge Cases

- **Concurrent Messages**: How does the system handle two users typing in the same mission chat? (Default: First-come first-served — serialized via Postgres advisory lock per `mission_id`; second message is queued until first LLM response is written).
- **Agent Failure**: What if an expert agent crashes during the chat? (Default: User sees an error message in the chat, same as in the initial pipeline).
- **Empty Context**: What if the chat is started on a mission where initial experts failed? (Default: Agents start with whatever data is available in the trigger).
- **Stale Kubeconfig**: The kubeconfig file materialized at mission creation contains a 1-hour token. On missions older than 1h, `chat()` MUST re-mint the GCP token and re-patch the kubeconfig before invoking any tool (see FR-008).
- **Mission Deleted Mid-Chat**: If the mission is deleted while a chat background task is running, the task MUST detect the missing row and abort cleanly — no orphaned `mission_messages` rows (FK cascade handles DB cleanup).
- **Already-Finalized Mission**: If spec 004 `POST /missions/{id}/finalize` was already called (BRIEF.md exists), opening a chat transitions to `CLARIFYING`. On re-close, the brief is **not** automatically regenerated — user must explicitly trigger finalize again if needed.

## Requirements

### Functional Requirements

- **FR-001**: System MUST provide a new table `mission_messages` to persist user and agent messages.
- **FR-002**: System MUST transition mission status to `CLARIFYING` upon the first user message after initial completion.
- **FR-003**: The Orchestrator MUST act as the entry point for chat, dispatching to experts based on user intent.
- **FR-004**: `MissionIsolationPlugin` MUST be active for all tool calls initiated from the chat.
- **FR-005**: Agents in chat MUST have read access to the mission's `agent_outputs` and `audit.md`.
- **FR-006**: UI MUST implement a chat interface (ADK-style) in the mission detail page.
- **FR-007**: System MUST provide an API endpoint `POST /v1/missions/{id}/chat` to send messages.
- **FR-008**: Before each chat turn that may invoke tools, `chat()` MUST re-mint the GCP token via `GCPTokenProvider` and re-patch the mission's kubeconfig file (tokens expire after 1h; missions may be reopened days after closure).
- **FR-009**: `POST /v1/missions/{id}/chat`, `GET /v1/missions/{id}/messages`, and `GET /v1/missions/{id}/events` MUST require an authenticated user whose tenant matches `mission.tenant`.
- **FR-010**: `mission_messages` MUST be deleted in cascade when its parent mission is deleted (`FK REFERENCES missions(id) ON DELETE CASCADE`). Spec 005 FR-005 must be updated in a companion PR.
- **FR-011**: Agents during chat MUST NOT post to Jira, Care, or GoogleChat automatically. All `c4-atlassian` write-tool calls MUST remain gated by the existing Jira opt-in toggle (Constitution Principle III). Read-only Jira tools (`jira_get_issue`, `jira_search`) are permitted.

### Key Entities

- **MissionMessage**: `id`, `mission_id`, `role` (user/assistant), `agent_name` (if assistant), `content`, `created_at`.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Chat responses are delivered in under 30 seconds on average (v0.6 baseline; target <5s streaming for v1).
- **SC-002**: 100% of chat-initiated tool calls are logged in the `audit.jsonl` of the mission.
- **SC-003**: Zero data leakage between environments during chat (verified by security tests).
- **SC-004**: Promptfoo eval suite includes ≥2 `chat_*` cases and maintains ≥80% pass rate (Constitution Principle IV — CI-blocking).
- **SC-005**: Average LLM token cost per chat session ≤ $0.10 (measured via Langfuse traces).

## Assumptions

- We reuse the existing `GCPTokenProvider` and `MissionIsolationPlugin`.
- The frontend uses SSE for real-time chat updates. The current SSE implementation (`api/sse.py`) is in-process (asyncio.Queue). Migration to Redis pub/sub (ADR-006) is treated as a **prerequisite** for multi-instance deployments; for v0.6 single-instance is acceptable.
- Users are authenticated. Auth implementation (`Depends(get_current_user)`) is added by this feature as a first gate — a prerequisite for the RBAC work tracked in a separate auth spec.
- Agents in chat are **read-only** (L2 — no mutating tools registered), consistent with Constitution Principle I.
- `Mem0MemoryPlugin` injects knowledge cards once per chat session (idempotent by `mission_id`) — not re-injected on every message turn.
