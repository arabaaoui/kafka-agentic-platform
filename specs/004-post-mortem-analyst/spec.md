# Feature Specification: Post-Mortem Analyst & KB Auto-Learning (v0.5)

**Feature Branch**: `004-post-mortem-analyst`
**Created**: 2026-05-11
**Status**: Approved
**Scope**: v0.5 — closes the KB learning loop; triggered manually or via API

---

## Context

In v0, the KB cards are static (17 seed cards copied from the extension). The post-mortem-analyst closes the loop: after each completed mission, it reads the generated audit and produces a new KB card, so future missions benefit from accumulated knowledge.

The extension does this with `kb.sh brief/card/index` shell scripts. The platform replaces this with a Python ADK agent + `core/kb_writer.py`.

---

## User Scenarios & Testing

### User Story 1 — Auto-Capitalise Completed Mission (Priority: P1)

After a PVC saturation mission is completed (audit.md generated), the team member clicks "Capitalise" in the UI (or calls `POST /v1/missions/{id}/finalize`). The post-mortem-analyst reads the audit, produces a `BRIEF.md`, creates `kb/incidents/pvc-saturation-<date>.md` with full YAML frontmatter and "Logique d'analyse appliquée ★" section, and regenerates `kb/INDEX.md`. Future missions on the same pattern will get this new card injected by `Mem0MemoryPlugin`.

**Why this priority**: This is the core value of the feature. Without it, the KB never grows beyond the 17 seed cards.

**Acceptance Scenarios**:

1. **Given** a completed mission with `audit.md`, **When** `POST /v1/missions/{id}/finalize` is called, **Then** `BRIEF.md` is written to `audits/{mission_id}/BRIEF.md` within 30s.
2. **Given** a generated BRIEF, **When** the agent determines the pattern is novel (no existing card with same slug), **Then** a new card is created in `kb/incidents/{slug}.md` with valid YAML frontmatter (slug, title, theme, tags, severity, symptoms, root_cause).
3. **Given** an existing card with the same slug, **When** the agent runs, **Then** the card's `occurrences`, `last_seen`, and `related_missions` are updated — no duplicate card created.
4. **Given** a new or updated card, **When** the agent finishes, **Then** `kb/INDEX.md` is regenerated with the updated card count.
5. **Given** a mission with `status=PARTIAL`, **When** finalize is called, **Then** the agent creates a BRIEF but skips KB card creation (insufficient evidence).
6. **Given** a mission with `status=OPEN` (still running), **When** finalize is called, **Then** the API returns 409 with `{"error": "mission_not_completed"}`.

---

### User Story 2 — KB Card Visible After Creation (Priority: P2)

After a new card is created, the next mission with a matching subject gets the card injected by `Mem0MemoryPlugin` — without any restart.

**Acceptance Scenarios**:

1. **Given** a new card `pvc-saturation-v2` added to `kb/incidents/`, **When** a new mission with `subject=pvc-saturation` starts and calls its first tool, **Then** `Mem0MemoryPlugin` scores and injects the new card.
2. This requires `KBIndex` to reload when the filesystem changes (watchfiles or TTL-based cache invalidation of 60s max).

---

## Requirements

### Functional Requirements

- **FR-001**: `POST /v1/missions/{id}/finalize` MUST return 409 if `mission.status != CLOSED`.
- **FR-002**: The agent MUST produce `audits/{mission_id}/BRIEF.md` with all sections: executive summary, root cause, impact, actions taken, lessons learned.
- **FR-003**: The agent MUST create `kb/incidents/{slug}.md` if no card with that slug exists, or update `occurrences/last_seen/related_missions` if it does.
- **FR-004**: The agent MUST regenerate `kb/INDEX.md` after any card create/update.
- **FR-005**: The slug MUST be validated (kebab-case, max 30 chars, no YAML comments) — uses `kafka_agent_toolkit.kb.schemas.SLUG_PATTERN`.
- **FR-006**: `Mem0MemoryPlugin.KBIndex` MUST reload cards within 60s of a filesystem change (TTL cache or watchfiles).
- **FR-007**: A finalize on a `status=PARTIAL` mission MUST generate BRIEF but MUST NOT create a KB card.
- **FR-008**: All file writes are local filesystem only (v0.5). S3 migration is post-v1.
- **FR-009**: The `POST /v1/missions/{id}/finalize` endpoint is opt-in (never called automatically in v0.5).

### Key Entities (additions to existing schema)

- **`audits.brief_path`** (new column): TEXT nullable — path to `BRIEF.md` once generated.
- **`audits.finalized_at`** (new column): TIMESTAMPTZ nullable — set when finalize completes.
- **`kb_cards`** (new table, optional v0.5): for tracking card creation history; or rely on filesystem only in v0.5.

---

## Success Criteria

- **SC-001**: `BRIEF.md` generated within 30s of finalize call on a completed mission.
- **SC-002**: `kb/incidents/{slug}.md` contains `root_cause`, `symptoms` (≥2), `Logique d'analyse appliquée ★` section.
- **SC-003**: `kb/INDEX.md` card count increments after finalize (grep `_Cartes : N`).
- **SC-004**: After finalize, next `KBIndex.search("pvc saturation")` returns the new card (verify in unit test, no restart required).
- **SC-005**: Slug created by the agent passes `SLUG_PATTERN.match(slug)` (regression guard from extension bug SC-005).
- **SC-006**: Finalize on a PARTIAL mission produces BRIEF.md but NOT a new card in `kb/incidents/`.

---

## Assumptions

- `audit.md` format is stable (sections: `## Summary`, ranked hypotheses table with `| Rank | Hypothesis | Confidence |` columns).
- The LLM model used for post-mortem-analyst is Gemini 1.5 Pro or Claude Sonnet (generation tier — see SKILL.md `scope`).
- `kb/incidents/` is writable from within the backend container (mounted volume).
- No concurrent finalize calls for the same mission (first caller wins; DB lock via `finalized_at` column).
