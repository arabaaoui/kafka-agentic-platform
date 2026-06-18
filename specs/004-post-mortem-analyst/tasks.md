# Tasks: Post-Mortem Analyst & KB Auto-Learning (v0.5)

**Branch**: `004-post-mortem-analyst` | **Spec**: [spec.md](./spec.md)
**Created**: 2026-05-11 | **Total tasks**: 14

---

## Phase 1 — Foundation

- [x] T001 [P] Create `agents/post_mortem_analyst/SKILL.md` — platform-adapted post-mortem workflow with KB card format, BRIEF.md template, INDEX.md regeneration steps [DONE ✅]
- [ ] T002 Write `core/kb_writer.py`: `KBCardWriter` class — `create_card(slug, title, theme, tags, severity, symptoms, root_cause, body, mission_id, env) -> Path`; `update_card(slug, mission_id) -> Path` (increments `occurrences`, updates `last_seen`, appends to `related_missions`); `card_exists(slug) -> bool`; `regenerate_index(kb_dir) -> int` (returns card count); validates slug via `SLUG_PATTERN`; all writes are atomic (write to `.tmp` then rename)
- [ ] T003 [P] Add Alembic migration `migrations/versions/0002_audit_finalize_columns.py`: ALTER TABLE audits ADD COLUMN brief_path TEXT, ADD COLUMN finalized_at TIMESTAMPTZ; UPDATE `core/models.py` to add `brief_path` and `finalized_at` columns to `Audit`
- [ ] T004 [P] Update `core/mem0_bridge.py` `KBIndex`: add TTL cache (60s) so `_ensure_loaded()` reloads when `time.time() - _loaded_at > 60`; add `invalidate()` method called after `KBCardWriter` writes a card

---

## Phase 2 — Agent

- [ ] T005 Write `agents/post_mortem_analyst/agent.py`: `PostMortemAgent` class using `google.adk.LlmAgent`; loads `SKILL.md` via skill loader; input: `MissionContext` + `audit_md_path`; workflow: (1) read `audit.md` + all `agent-outputs/{mission_id}/*.md`; (2) call LLM to produce BRIEF sections; (3) call LLM to extract KB card fields (slug, title, theme, tags, severity, symptoms, root_cause); (4) call `KBCardWriter.create_card()` or `update_card()`; (5) call `KBCardWriter.regenerate_index()`; (6) update `audits.brief_path` and `audits.finalized_at` in DB; returns `FinalizeResult`
- [ ] T006 [P] Define `FinalizeResult` Pydantic model in `api/schemas.py`: `mission_id`, `brief_path`, `kb_card_slug`, `kb_card_action` (`created|updated|skipped`), `kb_index_card_count`, `finalized_at`

---

## Phase 3 — API

- [ ] T007 Implement `POST /v1/missions/{id}/finalize` in `api/routes/missions.py`: check `mission.status == CLOSED` (409 if not); check `audit.finalized_at is None` (409 if already finalized); instantiate `PostMortemAgent`; `await agent.run(ctx, audit_md_path)`; return `FinalizeResult`; write audit trail to `audit.jsonl` via `AuditPlugin`
- [ ] T008 [P] Add `GET /v1/kb/cards` endpoint in new `api/routes/kb.py`: list all cards from `kb/INDEX.md` (parse frontmatter); optional `?theme=` and `?tag=` filters; returns list of card slugs + titles + themes + severities
- [ ] T009 [P] Add `GET /v1/kb/cards/{slug}` endpoint: return full card content as `text/markdown`; 404 if not found

---

## Phase 4 — UI

- [ ] T010 Add "Finalise" button to `web/app/missions/[id]/page.tsx`: shown only when `mission.status === "CLOSED"` and `audit.finalized_at === null`; on click: `POST /v1/missions/{id}/finalize`; show spinner while loading; on success: display `FinalizeResult` — brief path, KB card created/updated slug, card count; on error: show error message
- [ ] T011 [P] Add `web/app/kb/page.tsx`: KB card browser — list cards from `GET /v1/kb/cards` in a table (slug, theme, severity, occurrences); click row to view full card markdown via `GET /v1/kb/cards/{slug}`; filter by theme/tag

---

## Phase 5 — Tests

- [ ] T012 [P] Write `tests/unit/test_kb_writer.py`: test `create_card()` writes valid YAML frontmatter + markdown body; test `update_card()` increments `occurrences` and appends mission to `related_missions`; test `card_exists()` returns True/False; test `regenerate_index()` returns correct count and includes new card; test slug validation raises `ValueError` on invalid slug
- [ ] T013 [P] Write `tests/unit/test_mem0_bridge_ttl.py`: test `KBIndex` reloads after TTL expires; create a card file after initial load, advance time mock > 60s, assert `search()` finds the new card
- [ ] T014 [P] Write `tests/integration/test_finalize_mission.py`: mock LLM + `PostMortemAgent`; call `POST /v1/missions/{id}/finalize` on a CLOSED mission; assert BRIEF.md written; assert new card in `kb/incidents/`; assert `kb/INDEX.md` updated; assert 409 on OPEN mission; assert 409 on already-finalized mission
