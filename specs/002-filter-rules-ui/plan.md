# Implementation Plan: Filter Rules UI

**Branch**: `002-filter-rules-ui` | **Date**: 2026-05-10 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-filter-rules-ui/spec.md`

## Summary

Implement UI-configurable incident routing filters stored in Postgres (`filter_rules` table), replacing any static/YAML filter approach. The feature covers: an Alembic migration that creates the `filter_rules` and `filter_match_log` tables and seeds a bootstrap rule on first install; a FastAPI CRUD layer at `/v1/filter-rules` with a live-test endpoint backed by MCP `c4-atlassian`; a `FilterEngine` class that evaluates incoming triggers against active rules and logs every decision to `filter_match_log`; and a Next.js settings page (`/settings/filters`) with a `FilterRuleEditor` component supporting both form mode (project/assignee/issuetype/status/priority/labels/component selects → auto-generated JQL) and raw JQL mode. Rule changes take effect on the next poller cycle without restart (constitution VIII).

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript 5.3+ / Next.js 14 (frontend)
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, MCP `c4-atlassian` (jira_search), React, Next.js App Router
**Storage**: PostgreSQL 17 — `filter_rules` (JSONB criteria) + `filter_match_log` (matched/reason per evaluation)
**Testing**: pytest (unit + integration), React Testing Library (component tests)
**Target Platform**: Linux server (backend API + poller), browser (Next.js frontend)
**Project Type**: web-service (FastAPI) + web-application (Next.js)
**Performance Goals**: rule evaluation <5ms per trigger, rule-test endpoint response <5s (Jira round-trip), `/triggers/ignored` page load <500ms
**Constraints**: `poll_interval_seconds` minimum 30s enforced server-side; rule toggle reflected in poller within 60s; no Enterprise hardcode in `core/` or `api/` (constitution VII); all filter rules in Postgres, never YAML (constitution VIII)
**Scale/Scope**: ~10 active rules per tenant, ~1k trigger evaluations/day, single-tenant v0

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Read-only v0 | PASS | FilterEngine is read-only on infrastructure. CRUD on filter_rules is UI/operator action, not autonomous agent mutation. |
| II. Mission isolation enforced by plugin | PASS | Not impacted — this feature does not introduce new tool calls that cross mission boundaries. |
| III. Post Jira/Care = explicit opt-in | PASS | The rule-test endpoint reads from Jira (jira_search) but writes nothing. No external write action. |
| IV. Eval suite CI blocking | PASS | At least 1 new eval case required for FilterEngine (jira scope matching). Tracked in tasks. |
| V. Zero secret leakage in audit logs | PASS | `filter_match_log` stores only rule_id, trigger_id, matched bool, reason string. No credentials logged. |
| VI. Skills = SKILL.md filesystem | PASS | Not impacted — no new agent skill file needed for this feature. |
| VII. No Enterprise hardcode in core | PASS | `filter_engine.py` and `api/routes/filter_rules.py` receive tenant from `TenantConfig`. Bootstrap seed references ops-user via a seeded YAML value resolved at install time, not hardcoded in core code. |
| VIII. Filter rules = Postgres runtime | PASS | This spec IS the implementation of constitution VIII. The bootstrap seed is the defined exception (overridable via UI immediately after install). |

## Project Structure

### Documentation (this feature)

```text
specs/002-filter-rules-ui/
├── plan.md              # This file
├── spec.md              # Feature specification (approved)
├── data-model.md        # Phase 1 output — FilterRule + FilterMatchLog DDL, JSONB criteria schema
├── quickstart.md        # Phase 1 output — local dev setup, seed verification, test commands
├── contracts/           # Phase 1 output — OpenAPI fragments for /v1/filter-rules endpoints
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
api/
├── routes/
│   ├── filter_rules.py          # GET/POST/PATCH/DELETE /v1/filter-rules, POST /v1/filter-rules/{id}/test
│   └── triggers.py              # GET /v1/triggers/ignored  (append to existing file)
├── models/
│   ├── filter_rule.py           # SQLAlchemy ORM: FilterRule, FilterMatchLog
│   └── schemas/
│       └── filter_rule.py       # Pydantic v2 request/response schemas
└── deps.py                      # TenantConfig dependency (existing — no Enterprise hardcode)

core/
└── filter_engine.py             # FilterEngine.evaluate(trigger) → matched FilterRule | None
                                 # JQL matcher (jira scope), label matchers (alertmanager scope)
                                 # Logs every evaluation to filter_match_log

migrations/
├── versions/
│   ├── xxxx_create_filter_rules.py       # Alembic: CREATE TABLE filter_rules
│   ├── xxxx_create_filter_match_log.py   # Alembic: CREATE TABLE filter_match_log
│   └── xxxx_seed_bootstrap_rule.py       # Alembic: INSERT bootstrap rule (ops-user, PKH+PHX)
└── env.py                                # existing

web/
├── app/
│   └── settings/
│       └── filters/
│           └── page.tsx         # Filter rules list page: add/edit/delete/toggle/test
└── components/
    └── FilterRuleEditor.tsx     # Form mode (selects → JQL preview) + JQL mode switch
                                 # Warning badge on invalid JQL (from test response)

tests/
├── unit/
│   └── test_filter_engine.py    # FilterEngine: jira scope matching, alertmanager matchers,
│                                #   priority tie-break (id asc), poll_interval min enforcement
└── integration/
    └── test_filter_rules_api.py # CRUD lifecycle, test endpoint (mocked MCP), ignored triggers
```

**Structure Decision**: Web application layout (FastAPI backend + Next.js frontend). Backend code lives under `api/` and `core/` per existing platform structure. No new top-level project directory — this feature extends the existing monorepo layout. Alembic migrations extend the existing `migrations/` directory. Tests extend the existing `tests/unit/` and `tests/integration/` directories.

## Design Decisions

### Data Model

**FilterRule** (table: `filter_rules`):

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | gen_random_uuid() |
| tenant | TEXT NOT NULL | from TenantConfig — never hardcoded |
| scope | TEXT NOT NULL | `jira` \| `alertmanager` \| `care` |
| name | TEXT NOT NULL | human label |
| enabled | BOOL NOT NULL DEFAULT true | toggled via PATCH without restart |
| priority | INT NOT NULL DEFAULT 100 | lower = evaluated first |
| poll_interval_seconds | INT NOT NULL DEFAULT 60 | min 30s enforced in Pydantic validator |
| criteria | JSONB NOT NULL | `{ "jql": "..." }` for jira; `{ "matchers": [...] }` for alertmanager |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() | |
| updated_at | TIMESTAMPTZ NOT NULL DEFAULT now() | updated by trigger on PATCH |
| created_by | TEXT NOT NULL | username of creator |

**FilterMatchLog** (table: `filter_match_log`):

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | gen_random_uuid() |
| rule_id | UUID FK → filter_rules(id) ON DELETE SET NULL | nullable after rule deletion |
| trigger_id | UUID FK → triggers(id) | |
| matched | BOOL NOT NULL | true = rule matched and trigger accepted |
| reason | TEXT | e.g. "assignee mismatch", "project not in rule scope" |
| matched_at | TIMESTAMPTZ NOT NULL DEFAULT now() | |

**Bootstrap seed** (Alembic data migration, scope=jira):
```json
{
  "jql": "project IN (PKH, PHX) AND assignee = ops-user AND issuetype IN ('Incident','Bug') AND status NOT IN ('Closed','Resolved') AND created >= -7d"
}
```
Tenant value sourced from `TENANT_SLUG` env var at migration time — not hardcoded in the migration file.

### API Contracts

```
GET    /v1/filter-rules                  → list[FilterRuleResponse]  (tenant-scoped)
POST   /v1/filter-rules                  → FilterRuleResponse         (201)
PATCH  /v1/filter-rules/{id}             → FilterRuleResponse         (enabled toggle + any field)
DELETE /v1/filter-rules/{id}             → 204
POST   /v1/filter-rules/{id}/test        → FilterRuleTestResponse     (up to 10 sample matches)
GET    /v1/triggers/ignored              → list[IgnoredTriggerResponse] (matched=false in filter_match_log)
POST   /v1/triggers/{trigger_id}/convert → MissionResponse            (bypass filters, explicit confirmation required)
```

`FilterRuleTestResponse`:
```json
{
  "rule_id": "uuid",
  "matches": [
    { "key": "PKH-1234", "summary": "Kafka broker OOM", "assignee": "ops-user", "status": "Open" }
  ],
  "total": 1,
  "warning": null
}
```
On JQL error: `matches: []`, `warning: "Jira API error: Field 'asignee' does not exist"`, rule flagged `jql_error=true` in response (not persisted — UI badge only until next test passes).

### FilterEngine Logic

```python
class FilterEngine:
    def evaluate(self, trigger: Trigger, db: Session) -> FilterRule | None:
        rules = db.query(FilterRule).filter_by(
            tenant=trigger.tenant, scope=trigger.source, enabled=True
        ).order_by(FilterRule.priority.asc(), FilterRule.id.asc()).all()

        for rule in rules:
            matched, reason = self._match(rule, trigger)
            db.add(FilterMatchLog(rule_id=rule.id, trigger_id=trigger.id,
                                  matched=matched, reason=reason))
            if matched:
                db.commit()
                return rule

        db.add(FilterMatchLog(rule_id=None, trigger_id=trigger.id,
                              matched=False, reason="no matching rule"))
        db.commit()
        return None
```

Jira matcher: compares trigger fields (project, assignee, issuetype, status) against JQL parsed fields (v0: simple field extraction, not full JQL parse). Priority tie-break: `id` asc (first created wins).

Alertmanager matcher: checks `trigger.labels` dict against `criteria.matchers` list (equality + regex).

### Frontend: FilterRuleEditor Modes

**Form mode** (default for new rules):
- Selects: scope, project (static list loaded at page mount from `/v1/filter-rules/meta`), assignee (text input for v0), issuetype, status, priority, labels (multi), component (text).
- JQL preview panel (read-only, live-generated from selections).
- "Switch to JQL mode" button: copies generated JQL to editable textarea, disables form selects.

**JQL mode** (for power users):
- Single editable textarea.
- "Switch to form mode" button: only available if JQL is parseable back to simple field=value clauses; otherwise button is disabled with tooltip "JQL too complex for form mode".

Warning badge: rendered in the rule list card if the last test returned a `warning` field. Cleared on next successful test.

### Poller Integration

The Jira poller reads active rules from Postgres at the start of each poll cycle (no in-memory cache beyond the current cycle). `poll_interval_seconds` per rule controls how frequently the poller checks that specific rule's JQL. Enable/disable toggle (PATCH `enabled=false`) is reflected within one poll cycle (≤60s for a 60s interval rule, ≤30s for minimum-interval rules).

## Complexity Tracking

> No constitution violations. This feature is the direct implementation of constitution VIII and operates within all stack constraints.

| Item | Decision |
|------|----------|
| JSONB for criteria | Avoids schema churn as new scope types (care) are added. Validated at write time by Pydantic. Simple enough for v0 — no separate criteria tables needed. |
| No in-memory rule cache | Rules loaded from Postgres per poll cycle. Eliminates cache invalidation problem. Acceptable at v0 scale (~10 rules). Revisit at v1 if poller frequency increases significantly. |
| Static Jira metadata selects | Form selects use a static list loaded once at page mount (not real-time Jira search). Acceptable for v0 team size. Simplifies MCP dependency surface. |
