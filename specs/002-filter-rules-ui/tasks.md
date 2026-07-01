# Tasks: Filter Rules UI

**Feature**: `002-filter-rules-ui`
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)
**Generated**: 2026-05-10
**Total tasks**: 52

---

## Phase 1 — Setup & Init (blocking: infrastructure wiring, no US dependency)

- [ ] T001 [P] Create `core/__init__.py` if absent — ensures `core/` is a Python package importable by API and poller
- [ ] T002 [P] Create `api/models/__init__.py` if absent — ensures ORM models sub-package is importable
- [ ] T003 [P] Create `api/models/schemas/__init__.py` if absent — ensures Pydantic schemas sub-package is importable
- [ ] T004 [P] Register `api/routes/filter_rules.py` router in `api/main.py` (or equivalent app factory) with prefix `/v1`
- [ ] T005 [P] Register `api/routes/triggers.py` router in `api/main.py` with prefix `/v1` (append to existing registrations)
- [ ] T006 [P] Confirm `migrations/env.py` includes `api.models.filter_rule` metadata target so Alembic autogenerate picks up new tables

---

## Phase 2 — Foundational BLOCKING (FilterEngine + DB schema — required by all US)

- [ ] T007 Create SQLAlchemy ORM model `FilterRule` in `api/models/filter_rule.py` — columns: id (UUID PK), tenant, scope, name, enabled, priority, poll_interval_seconds, criteria (JSONB), created_at, updated_at, created_by
- [ ] T008 Create SQLAlchemy ORM model `FilterMatchLog` in `api/models/filter_rule.py` — columns: id (UUID PK), rule_id (FK → filter_rules nullable), trigger_id (FK → triggers), matched (bool), reason, matched_at
- [ ] T009 Create Pydantic v2 request schema `FilterRuleCreate` in `api/models/schemas/filter_rule.py` — fields mirroring FilterRule; validator enforces `poll_interval_seconds >= 30`
- [ ] T010 Create Pydantic v2 response schema `FilterRuleResponse` in `api/models/schemas/filter_rule.py` — all fields including `id`, `created_at`, `updated_at`; `jql_error: bool` field (transient, UI badge only)
- [ ] T011 Create Pydantic v2 schema `FilterRulePatch` in `api/models/schemas/filter_rule.py` — all fields optional; used for PATCH; same `poll_interval_seconds >= 30` validator
- [ ] T012 Create Pydantic v2 schema `FilterRuleTestResponse` in `api/models/schemas/filter_rule.py` — fields: rule_id, matches (list of IssueMatch), total, warning (str | None)
- [ ] T013 Create Pydantic v2 schema `IgnoredTriggerResponse` in `api/models/schemas/filter_rule.py` — fields: trigger_id, source, key_summary, reason, received_at
- [ ] T014 Write Alembic migration `migrations/versions/0002_filter_rules.py` — CREATE TABLE filter_rules with correct types, constraints, and `gen_random_uuid()` default for id
- [ ] T015 Write Alembic migration `migrations/versions/0003_filter_match_log.py` — CREATE TABLE filter_match_log; FK to filter_rules ON DELETE SET NULL; FK to triggers
- [ ] T016 Implement `FilterEngine` class skeleton in `core/filter_engine.py` — `__init__(self)`, public method signature `evaluate(self, trigger, db) -> FilterRule | None`
- [ ] T017 Implement `FilterEngine._match_jira(rule, trigger)` in `core/filter_engine.py` — parses simple field=value clauses from `criteria.jql` (project, assignee, issuetype, status); returns `(bool, str)` matched + reason
- [ ] T018 Implement `FilterEngine._match_alertmanager(rule, trigger)` in `core/filter_engine.py` — checks `trigger.labels` dict against `criteria.matchers` list (equality + regex); returns `(bool, str)`
- [ ] T019 Implement `FilterEngine.evaluate()` full body in `core/filter_engine.py` — queries enabled rules ordered by `priority asc, id asc`; calls `_match` per scope; writes `FilterMatchLog` row for every evaluation (matched or not); commits and returns first matched rule or None
- [ ] T020 Enforce `poll_interval_seconds` minimum 30s in `FilterEngine` (raise `ValueError` if rule misconfigured at evaluation time, in addition to Pydantic validator)

---

## Phase 3 — US1: Bootstrap Seed + Migration

- [ ] T021 [US1] Write Alembic seed migration `migrations/versions/0004_seed_bootstrap_filter.py` — INSERT one row into `filter_rules` with name=`'Mes incidents Kafka (bootstrap)'`, scope=`'jira'`, enabled=`true`, priority=`10`, poll_interval_seconds=`60`; JQL from spec §US1; tenant sourced from `TENANT_SLUG` env var (os.environ), never hardcoded
- [ ] T022 [US1] Verify tenant env-var fallback in `migrations/versions/0004_seed_bootstrap_filter.py` — raise `RuntimeError` with clear message if `TENANT_SLUG` is not set at migration time
- [ ] T023 [US1] Write integration test `tests/integration/test_bootstrap_seed.py` — applies migration against test DB, asserts exactly 1 row in `filter_rules` where `name='Mes incidents Kafka (bootstrap)'`, `enabled=true`, `scope='jira'`
- [ ] T024 [US1] [P] Verify bootstrap rule visible in `GET /v1/filter-rules` response in `tests/integration/test_bootstrap_seed.py` — after seed migration, list endpoint returns the seeded rule

---

## Phase 4 — US2: Form Mode CRUD (API + UI)

- [ ] T025 [US2] Implement `GET /v1/filter-rules` in `api/routes/filter_rules.py` — returns all rules for current tenant, ordered by priority asc; uses `TenantConfig` dep from `api/deps.py`
- [ ] T026 [US2] Implement `POST /v1/filter-rules` in `api/routes/filter_rules.py` — validates `FilterRuleCreate`, persists to DB, returns 201 `FilterRuleResponse`; generates `criteria.jql` from form fields if `form_mode=true` in request body
- [ ] T027 [US2] Implement JQL generation helper `build_jql_from_form(fields: dict) -> str` in `api/routes/filter_rules.py` or `core/filter_engine.py` — produces valid JQL from project/assignee/issuetype/status/priority/labels/component; handles multi-value fields with `IN (...)` syntax
- [ ] T028 [US2] Implement `DELETE /v1/filter-rules/{id}` in `api/routes/filter_rules.py` — hard delete, returns 204; validates rule belongs to current tenant
- [ ] T029 [US2] Add `GET /v1/filter-rules/meta` endpoint in `api/routes/filter_rules.py` — returns static Jira metadata lists (projects, issuetypes, statuses, priorities) used by frontend form selects; values defined as constants in the route file for v0
- [ ] T030 [US2] Create Next.js page `web/app/settings/filters/page.tsx` — server component fetching `GET /v1/filter-rules`; renders list of `FilterRuleCard` components; "Add rule" button opens `FilterRuleEditor` in a modal/drawer; handles empty state
- [ ] T031 [US2] Create `web/components/FilterRuleEditor.tsx` — form mode (default for new rules): scope select, project select, assignee text input, issuetype select, status select, priority select, labels multi-select, component text; live JQL preview panel (read-only); "Switch to JQL mode" button; Save/Cancel actions
- [ ] T032 [US2] Implement JQL preview generation in `web/components/FilterRuleEditor.tsx` — client-side mirror of `build_jql_from_form` producing live preview as user updates selects; no API call needed for preview
- [ ] T033 [US2] Implement "Switch to JQL mode" in `web/components/FilterRuleEditor.tsx` — copies generated JQL into editable `<textarea>`; disables form selects; "Switch to form mode" button appears but is disabled with tooltip if JQL is too complex to parse back
- [ ] T034 [US2] Load `/v1/filter-rules/meta` at page mount in `web/app/settings/filters/page.tsx` and pass metadata lists as props to `FilterRuleEditor` for populating selects
- [ ] T035 [US2] Write integration tests in `tests/integration/test_filter_rules_api.py` — full CRUD lifecycle: POST creates rule, GET lists it, PATCH updates name, DELETE removes it; assert 404 on double-delete; assert form-mode JQL generation round-trip

---

## Phase 5 — US3: Rule Test Endpoint (API + UI)

- [ ] T036 [US3] Implement `POST /v1/filter-rules/{id}/test` in `api/routes/filter_rules.py` — loads rule from DB; calls MCP `c4-atlassian` `jira_search` with `criteria.jql`; returns `FilterRuleTestResponse` with up to 10 matches (key, summary, assignee, status); timeout 5s
- [ ] T037 [US3] Handle Jira API error in `POST /v1/filter-rules/{id}/test` — on JQL syntax error or MCP failure, return `FilterRuleTestResponse` with `matches=[]`, `total=0`, `warning="<Jira error message>"`; HTTP 200 (not 500) so UI can render the warning badge
- [ ] T038 [US3] Handle `currentUser()` in JQL at test time — detect `currentUser()` token in JQL and replace with `created_by` username from the rule record; add note to `warning` field
- [ ] T039 [US3] Add "Test rule" button to `web/components/FilterRuleEditor.tsx` — calls `POST /v1/filter-rules/{id}/test`; shows loading spinner; renders match list (key, summary, assignee, status) in a results panel below the editor; shows "No matching tickets found. Consider broadening the rule." on empty matches
- [ ] T040 [US3] Render warning badge in `web/components/FilterRuleEditor.tsx` — when `FilterRuleTestResponse.warning` is non-null, display a yellow badge on the rule card; badge cleared on next successful test (warning=null)
- [ ] T041 [US3] [P] Write integration test in `tests/integration/test_filter_rules_api.py` — mock MCP `jira_search` returning 3 issues; assert test endpoint returns exactly those 3 issues in response; assert `total=3`, `warning=null`
- [ ] T042 [US3] [P] Write integration test for JQL error path in `tests/integration/test_filter_rules_api.py` — mock MCP raising `JiraAPIError`; assert response has `matches=[]`, `warning` non-null, HTTP 200

---

## Phase 6 — US4: Enable/Disable Toggle (PATCH + Poller Integration)

- [ ] T043 [US4] Implement `PATCH /v1/filter-rules/{id}` in `api/routes/filter_rules.py` — accepts `FilterRulePatch`; partial update (only provided fields); updates `updated_at` timestamp; returns `FilterRuleResponse`; validates tenant ownership
- [ ] T044 [US4] Integrate `FilterEngine` into `triggers/jira_mcp_poller.py` — at start of each poll cycle, instantiate `FilterEngine` and call `evaluate(trigger, db)` for each incoming trigger; skip mission creation if `evaluate` returns `None`; log matched rule name at DEBUG level
- [ ] T045 [US4] Implement per-rule `poll_interval_seconds` scheduling in `triggers/jira_mcp_poller.py` — poller reads `poll_interval_seconds` per rule from DB each cycle; tracks `last_polled_at` per rule_id in-memory; skips rule if `now - last_polled_at < poll_interval_seconds`
- [ ] T046 [US4] Verify toggle cycle time in `triggers/jira_mcp_poller.py` — add comment + test assertion that a rule toggled `enabled=false` via PATCH is not evaluated on the next cycle (DB re-read at cycle start guarantees ≤60s reflection)
- [ ] T047 [US4] Add toggle switch UI in `web/app/settings/filters/page.tsx` — renders an enable/disable toggle per rule card; calls `PATCH /v1/filter-rules/{id}` with `{ enabled: <bool> }` on toggle; optimistic update with rollback on API error
- [ ] T048 [US4] Write integration test for PATCH toggle in `tests/integration/test_filter_rules_api.py` — POST rule, PATCH `enabled=false`, GET list, assert rule has `enabled=false`; PATCH `enabled=true`, assert restored

---

## Phase 7 — US5: Ignored Triggers View + Convert Action

- [ ] T049 [US5] Implement `GET /v1/triggers/ignored` in `api/routes/triggers.py` — queries `filter_match_log` for rows where `matched=false`; joins `triggers` table for source, key/payload summary, received_at; returns list of `IgnoredTriggerResponse`; tenant-scoped; ordered by `matched_at` desc; limit 100
- [ ] T050 [US5] Implement `POST /v1/triggers/{trigger_id}/convert` in `api/routes/triggers.py` — validates trigger exists and belongs to tenant; creates a mission record bypassing `FilterEngine`; requires `{ confirmed: true }` in request body (explicit confirmation guard per FR-008); returns `MissionResponse`
- [ ] T051 [US5] Create `web/components/IgnoredTriggerCard.tsx` — displays: source badge (jira/alertmanager), key/payload summary, reason text, received_at (relative time); "Convert to mission" button opens a confirmation dialog; on confirm calls `POST /v1/triggers/{id}/convert` with `{ confirmed: true }`; on success navigates to new mission
- [ ] T052 [US5] Add `/triggers/ignored` route to `web/app/settings/filters/page.tsx` or as a sibling page `web/app/triggers/ignored/page.tsx` — renders list of `IgnoredTriggerCard` components; shows empty state "No ignored triggers in the last 24h"; auto-refreshes every 30s

---

## Phase 8 — Polish & Test Coverage

- [ ] T053 [P] Write unit tests in `tests/unit/test_filter_engine.py` — jira scope: field match (project, assignee, issuetype, status), partial match, no match; priority tie-break (two rules same priority, id asc wins); `poll_interval_seconds` < 30 raises `ValueError`
- [ ] T054 [P] Write unit test for alertmanager matcher in `tests/unit/test_filter_engine.py` — label equality match, regex match, no match; ensure `FilterMatchLog` rows written for all evaluated rules
- [ ] T055 [P] Write unit test for `build_jql_from_form` in `tests/unit/test_filter_engine.py` (or `tests/unit/test_filter_rules_api.py`) — single-value fields, multi-value `IN (...)`, empty optional fields omitted, all-fields case
- [ ] T056 [P] Add `FR-006` coverage assertion in `tests/unit/test_filter_engine.py` — after `evaluate()` call with 3 rules (2 non-matching, 1 matching), assert exactly 3 `FilterMatchLog` rows written (one per evaluated rule)
- [ ] T057 [P] Verify edge case: two rules same priority in `tests/unit/test_filter_engine.py` — rule with lower UUID (lexicographically earlier) wins; both rules have `FilterMatchLog` rows written regardless
- [ ] T058 [P] Add Postgres unavailability circuit-breaker stub in `triggers/jira_mcp_poller.py` — catch `OperationalError` on DB connect; log error; back off with exponential retry (max 5 attempts, base 2s); emit a structured alert event surfaced in UI header (future hook, log only for v0)
- [ ] T059 [P] Ensure no Enterprise-specific hardcode in `core/filter_engine.py` — code review pass: grep for `ops-user`, `PKH`, `PHX`; all tenant/rule values must come from DB or env at runtime
- [ ] T060 [P] Ensure no Enterprise-specific hardcode in `api/routes/filter_rules.py` — same grep pass; static metadata lists (`PROJECTS`, `ISSUETYPES`, etc.) must be defined as overridable constants, not literals embedded in logic
