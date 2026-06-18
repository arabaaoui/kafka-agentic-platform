# Tasks: Post-Mission Chat

**Branch**: `008-post-mission-chat` | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)
**Generated**: 2026-05-18 | **Revised**: 2026-05-19 (post-review) | **Total tasks**: 26

---

## Phase 1 — Persistence & Foundational

- [ ] T001 [P] Add `MissionMessage` model in `core/models.py`: `id`, `mission_id` (FK), `role` (user/assistant), `agent_name`, `content`, `created_at`.
- [ ] T002 Generate and apply Alembic migration for `mission_messages`: FK `mission_id REFERENCES missions(id) ON DELETE CASCADE` + composite index on `(mission_id, created_at)`.
- [ ] T003 Add `CLARIFYING` to `MissionStatus` enum in `core/mission.py` and add `with_status(new_status) -> MissionContext` helper (frozen dataclass — no in-place mutation).
- [ ] T004 Create `validate_transition(current: MissionStatus, target: MissionStatus)` function (does not exist today): allow `OPEN→CLOSED`, `OPEN→PARTIAL`, `{CLOSED,PARTIAL}→CLARIFYING`, `CLARIFYING→CLOSED`; raise `ValueError` for all others.

---

## Phase 2 — Backend Orchestrator & API

- [ ] T005 [P] Implement `GET /v1/missions/{id}/messages` endpoint: paginated (`limit`/`offset`), ordered by `created_at`, auth-guarded.
- [ ] T006 Implement `POST /v1/missions/{id}/chat` endpoint: auth guard, Postgres advisory lock per `mission_id`, user message insertion, `validate_transition(→CLARIFYING)`, background task trigger.
- [ ] T007a Extract `_patch_kubeconfig_for_mission(mission_ctx) -> Path` helper from `agents/pipeline/orchestrator.py:112-134` (re-mints GCP token + rewrites kubeconfig file; must be called at start of each chat turn).
- [ ] T007b Implement `PipelineOrchestrator.chat()` context loader: fetch `agent_outputs` rows + last N `mission_messages` + original trigger; build prompt prefix.
- [ ] T007c Implement `PipelineOrchestrator.chat()` LLM call + routing: define `delegate_to_expert` virtual tool, invoke orchestrator LLM, execute tool call if emitted, persist assistant `MissionMessage`.
- [ ] T008 [P] Implement `_invoke_expert_for_chat(agent_name, sub_question, mission_ctx, plugin_chain)` — invokes the named expert agent (KafkaExpert, SREExpert, etc.) with isolated context and canonical plugin chain; returns str output to be included in orchestrator response.
- [ ] T009 Implement `POST /v1/missions/{id}/close`: auth guard, `validate_transition(CLARIFYING→CLOSED)`, `closed_at = now()` update.
- [ ] T010 Wire SSE broadcast for `chat.message` events in the chat loop.

---

## Phase 3 — Frontend Development

- [ ] T011 [P] Create `ChatBox` UI component in `web/components/PostMissionChat.tsx` (ADK-style).
- [ ] T012 Integrate `ChatBox` into `web/app/missions/[id]/page.tsx`.
- [ ] T013 [P] Implement real-time message updates using existing SSE infrastructure.
- [ ] T014 Add "Approve & Close" button to the mission header when status is `CLARIFYING`.
- [ ] T015 Handle UI loading states (IA typing...) and error toasts.

---

## Phase 4 — Security & Cross-Spec

- [ ] T019 [P] Add `evals/cases/chat_routing_kafka_expert.yaml` + `evals/cases/chat_isolation_blocked.yaml` (≥1 scorer verifies `audit.jsonl` `cross_env_blocked` entry) — **CI-blocking per Constitution Principle IV**.
- [ ] T020 Add `Depends(get_current_user)` auth dependency to all 4 chat endpoints (`POST /chat`, `GET /messages`, `POST /close`, `GET /events`); tenant-match check (HTTP 403 on mismatch).
- [ ] T021 Open companion PR on `specs/005-deletion-and-audit/spec.md` to list `mission_messages` in FR-005 cascade delete enumeration.
- [ ] T022 Postgres advisory lock (`pg_try_advisory_lock` / `pg_advisory_unlock`) helper — wrap in `async with advisory_lock(conn, mission_id)` context manager used in T006.

---

## Phase 5 — Validation & Tests

- [ ] T023 Unit tests: `validate_transition()` all valid+invalid FSM paths; `_patch_kubeconfig_for_mission()` (mock `GCPTokenProvider`); `MissionIsolationPlugin` blocking cross-env tool call in chat context.
- [ ] T024 Integration test: full chat API flow (Send → LLM mock → Response persisted → DB check → `CLARIFYING` status), Postgres advisory lock serialization under concurrent requests.
- [ ] T025 Unit test: confirm no `c4-atlassian` write-tool (`jira_add_comment`) is callable from chat plugin chain without Jira opt-in toggle (Constitution Principle III).
- [ ] T026 [P] E2E test with Playwright: Complete Mission → Start Chat → Ask Question → Receive Response → Click "Approve & Close" → verify status `CLOSED`.
