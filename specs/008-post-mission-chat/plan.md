# Implementation Plan: Post-Mission Chat

**Branch**: `008-post-mission-chat` | **Date**: 2026-05-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/008-post-mission-chat/spec.md`

## Summary

Enable interactive dialogue with the agent team after the automated triage is complete. This involves creating a persistence layer for messages, updating the Mission status FSM, and extending the Orchestrator to handle turn-based chat while maintaining strict environment isolation.

## Technical Context

**Language/Version**: Python 3.11+, TypeScript 5.3+
**Primary Dependencies**: FastAPI, SQLAlchemy, Next.js, Google ADK
**Storage**: PostgreSQL (new `mission_messages` table), Redis (SSE broadcast — ADR-006 prerequisite; in-process asyncio.Queue acceptable for v0.6 single-instance)
**Testing**: pytest (backend chat flow), Playwright (frontend interaction)
**Target Platform**: Docker Compose / GKE
**Project Type**: Full-stack feature extension

## Phase 1: Persistence & Core (Backend)

1.  **Database Schema**: Add `MissionMessage` model in `core/models.py` with `id`, `mission_id` (FK → `missions.id`), `role` (user/assistant), `agent_name`, `content`, `created_at`.
2.  **Migration**: Create Alembic migration for `mission_messages` with:
    - `FK mission_id REFERENCES missions(id) ON DELETE CASCADE` (covers spec 005 FR-005 gap for this table)
    - Composite index on `(mission_id, created_at)` for paginated fetch performance
3.  **Status FSM**: Add `CLARIFYING` to `MissionStatus` enum in `core/mission.py`. Create a `validate_transition(current: MissionStatus, target: MissionStatus)` function (does not exist today) enforcing the table:
    - `OPEN → CLOSED` ✓ | `OPEN → PARTIAL` ✓
    - `CLOSED → CLARIFYING` ✓ | `PARTIAL → CLARIFYING` ✓
    - `CLARIFYING → CLOSED` ✓
    - All other transitions raise `ValueError`
    - `closed_at` policy: preserved on `CLARIFYING` transition, updated to `now()` on re-`CLOSED`.
4.  **MissionContext unfreeze**: `MissionContext` is currently `frozen=True` (core/mission.py:90). Add a `with_status(new_status)` helper that returns a new instance — no direct mutation.

## Phase 2: Orchestrator Extension

1.  **Token Refresh Helper**: Extract `agents/pipeline/orchestrator.py:112-134` (kubeconfig patching block) into a reusable `_patch_kubeconfig_for_mission(mission_ctx) -> Path` helper. The materialized kubeconfig at `{AUDIT_DIR}/{mission_id}/kubeconfig.yaml` contains a 1h-lived token baked in at mission creation — `chat()` MUST call this helper before any turn that may invoke tools.
2.  **Chat Loop**: Implement `PipelineOrchestrator.chat(mission_ctx, user_message, db) -> str`:
    *   Call `_patch_kubeconfig_for_mission(mission_ctx)` to refresh token.
    *   Load conversation context: read `agent_outputs` rows + last N `mission_messages` + `trigger` data.
    *   **Expert routing via LLM function-calling**: define a virtual `delegate_to_expert(agent_name: str, sub_question: str)` tool. The orchestrator LLM decides whether to answer directly or emit this tool call; if emitted, the named expert agent is invoked with the sub-question as its task.
    *   Invoke tool calls wrapped in the canonical `PluginChain` (Guardrails → Resilience → OTelMetrics → Audit → Activity → Mem0Memory → MissionIsolation → Autonomy → ErrorHandler).
    *   Return assistant response string.
3.  **Plugin & Mem0 Policy**: Rebuild `PluginChain` per message (consistent with current per-agent-per-mission pattern). `Mem0MemoryPlugin` is idempotent per `mission_id` (001 FR-013) — on second and subsequent messages it will skip re-injection automatically.
4.  **Jira gate**: Confirm that no `c4-atlassian` write-tool (`jira_add_comment`, etc.) is registered in the chat plugin chain unless the Jira opt-in toggle is active (Constitution Principle III).

## Phase 3: API Endpoints

1.  **Auth guard**: Add `Depends(get_current_user)` dependency to all 4 chat endpoints. Check `current_user.tenant == mission.tenant`; raise HTTP 403 otherwise. (First use of auth in the platform — no RBAC spec yet, simple tenant match is sufficient for v0.6.)
2.  **Chat Send**: `POST /v1/missions/{id}/chat`
    *   Accepts `{ content: str }`.
    *   Acquires Postgres advisory lock (`pg_try_advisory_lock(mission_id_int)`) to serialize concurrent messages for the same mission — release after background task is enqueued.
    *   Transitions mission to `CLARIFYING` via `validate_transition()`.
    *   Persists user `MissionMessage`, fires background task for orchestrator response.
3.  **Chat Fetch**: `GET /v1/missions/{id}/messages` — paginated (`limit`/`offset`) list of messages ordered by `created_at`.
4.  **SSE Integration**: Broadcast `chat.message` and `chat.typing` events via existing `sse_manager` (in-process asyncio.Queue). Note: horizontal scaling requires ADR-006 Redis migration first.
5.  **Re-close**: `POST /v1/missions/{id}/close` — sets status to `CLOSED` via `validate_transition()`, updates `closed_at = now()`.

## Phase 4: Frontend Development

1.  **Chat Component**: Create `PostMissionChat.tsx` (sidebar or collapsible panel).
2.  **Mission View Integration**: Embed chat in `/missions/[id]` page.
3.  **Status Handling**: Disable/enable actions based on `CLARIFYING` status.
4.  **Real-time**: Listen to `chat.message` SSE events to update the thread.

## Phase 5: Tests & Validation

1.  **Unit Tests**: Test `MissionIsolationPlugin` during a chat session (mocking prod access attempt). Test `validate_transition()` for all valid and invalid FSM paths. Test `_patch_kubeconfig_for_mission()` standalone (mocked `GCPTokenProvider`).
2.  **Integration Tests**: Mock LLM response and verify message persistence, status transition, and Postgres advisory lock serialization.
3.  **Eval Cases (CI-blocking — Constitution Principle IV)**: Add to `evals/cases/`:
    - `chat_routing_kafka_expert.yaml` — verify orchestrator delegates to KafkaExpert when user asks about topic lag.
    - `chat_isolation_blocked.yaml` — verify `MissionIsolationPlugin` blocks cross-env tool call initiated from chat and returns a clear explanation.
    At least one scorer must verify `audit.jsonl` contains the `cross_env_blocked` entry (no secret leakage).
4.  **E2E (Playwright)**: Simulate a full user journey: Complete Mission → Start Chat → Ask Question → Receive Response → Click "Approve & Close".
