# Tasks: Deletion and Audit Trail

**Feature**: Deletion and Audit Trail (005-deletion-and-audit)

## Implementation Strategy

We will start by updating the database schema to support the audit trail, then implement the backend logic for both KB cards and Missions (including file system operations), and finally integrate the UI with safety-first confirmation dialogs.

## Phase 1: Setup

- [ ] T001 Initialize implementation context and verify branch `005-deletion-and-audit`

## Phase 2: Foundational

- [ ] T002 [P] Add `SystemAudit` model in `core/models.py`
- [ ] T003 Create and run Alembic migration for `system_audit` table in `migrations/`

## Phase 3: KB Card Deletion [US1]

**Goal**: Enable secure removal of KB cards with file system cleanup.
**Test**: Use `curl -X DELETE /v1/kb/cards/slug` and verify file absence and `INDEX.md` update.

- [ ] T004 Implement `delete_card(slug)` in `core/kb_writer.py` (os.remove + regenerate_index)
- [ ] T005 Implement `DELETE /v1/kb/cards/{slug}` in `api/routes/kb.py` with `SystemAudit` logging
- [ ] T006 Add `deleteKBCard` function in `web/lib/api.ts`

## Phase 4: Mission Deletion [US2]

**Goal**: Clean up mission history with cascading database deletion.
**Test**: Verify mission and its agent_outputs/audits are gone from DB after API call.

- [ ] T007 Implement `DELETE /v1/missions/{id}` in `api/routes/missions.py` with cascading delete and `SystemAudit` logging
- [ ] T008 Add `deleteMission` function in `web/lib/api.ts`

## Phase 5: UI Integration [US1, US2]

**Goal**: Provide user-friendly deletion triggers with confirmation.
**Test**: Perform deletion from UI and confirm data disappears after modal confirmation.

- [ ] T009 [P] Create `DeleteConfirmModal` component in `web/components/DeleteConfirmModal.tsx`
- [ ] T010 [US1] Integrate deletion trigger in `web/app/kb/page.tsx` gallery
- [ ] T011 [US2] Integrate deletion trigger in `web/app/missions/page.tsx` history table

## Phase 6: Polish

- [ ] T012 Final manual end-to-end verification of the audit trail content

## Dependencies

- US1, US2 depend on Phase 2 (Foundational).
- US3 (Audit) is integrated into US1 and US2 tasks.
