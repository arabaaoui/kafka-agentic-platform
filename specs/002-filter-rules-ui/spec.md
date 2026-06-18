# Feature Specification: Filter Rules UI

**Feature Branch**: `002-filter-rules-ui`
**Created**: 2026-05-10
**Status**: Approved
**Scope**: v0 — UI-configurable incident routing filters

---

## User Scenarios & Testing

### User Story 1 — Bootstrap & Personal Filter Active at Install (Priority: P1)

At first install, a bootstrap filter rule is automatically inserted for the current user (assignee=arabaaoui, projects PKH+PHX, issuetype Incident/Bug, status Open). The user immediately sees it in `/settings/filters` without any manual configuration.

**Why this priority**: Enables dogfooding from minute 0. No config friction.

**Independent Test**: Run `POST /api/install` (or DB migration seed) and verify `SELECT * FROM filter_rules WHERE name='Mes incidents Kafka (bootstrap)'` returns 1 enabled row.

**Acceptance Scenarios**:

1. **Given** a fresh install, **When** the Postgres migration runs, **Then** table `filter_rules` contains exactly 1 row: `{ scope: "jira", name: "Mes incidents Kafka (bootstrap)", enabled: true, criteria: { jql: "project IN (PKH, PHX) AND assignee = arabaaoui AND issuetype IN ('Incident','Bug') AND status NOT IN ('Closed','Resolved') AND created >= -7d" } }`.
2. **Given** the bootstrap rule, **When** the user opens `/settings/filters`, **Then** the rule is visible, enabled, with JQL displayed in read mode.

---

### User Story 2 — Add a New Filter Rule via Formulaire Mode (Priority: P1)

The user wants to add a rule to also track incidents assigned to a colleague (Taoufiq Bahalla) on the KAFKAOPS project. They use the form mode (no JQL knowledge required): select project=KAFKAOPS, assignee=taoufiq.bahalla, issuetype=Incident.

**Why this priority**: Key to the "start personal, then generalize to team" progression. The form mode makes it accessible to non-JQL users on the team.

**Independent Test**: Can be tested independently via `POST /v1/filter-rules` with a JSON body containing `criteria.project`, `criteria.assignee`, `criteria.issuetype` fields. The system translates this to a valid JQL and stores it.

**Acceptance Scenarios**:

1. **Given** the filter settings page, **When** the user clicks "Add rule", selects scope=Jira, fills project=KAFKAOPS, assignee=taoufiq.bahalla, issuetype=Incident, and saves, **Then** a new enabled rule is created with `criteria: { jql: "project = KAFKAOPS AND assignee = taoufiq.bahalla AND issuetype = Incident" }`.
2. **Given** a newly created rule, **When** the Jira poller next runs, **Then** it polls using the new rule's JQL in addition to all other active rules.
3. **Given** a form-mode rule, **When** the user switches to "JQL mode" on the same rule, **Then** the generated JQL is displayed and editable.

---

### User Story 3 — Test a Filter Rule (Priority: P2)

Before activating a new rule, the user clicks "Test rule". The system executes the JQL against Jira via MCP `c4-atlassian` and displays the last 10 matching tickets with their key, summary, assignee, status.

**Why this priority**: Prevents misconfigured rules from generating spurious missions or missing real incidents.

**Independent Test**: Testable via `POST /v1/filter-rules/{id}/test`. Returns a list of matching Jira issues (or empty list). Requires MCP `c4-atlassian` connection.

**Acceptance Scenarios**:

1. **Given** a filter rule with valid JQL, **When** the user clicks "Test rule", **Then** the UI displays up to 10 matching Jira issues (key, summary, assignee, status) within 5 seconds.
2. **Given** a filter rule with JQL that matches 0 tickets, **When** tested, **Then** the UI displays "No matching tickets found. Consider broadening the rule."
3. **Given** a filter rule with invalid JQL syntax, **When** tested, **Then** the UI displays the Jira API error message and marks the rule with a warning badge.

---

### User Story 4 — Enable/Disable a Rule Without Restart (Priority: P2)

The user toggles a filter rule off (e.g., during a maintenance window to avoid spurious missions). The change takes effect on the next poller cycle without any server restart.

**Acceptance Scenarios**:

1. **Given** an enabled rule, **When** the user toggles it off via the UI switch, **Then** `PATCH /v1/filter-rules/{id}` sets `enabled=false` and the poller stops evaluating it within 60s.
2. **Given** a disabled rule, **When** the user toggles it on, **Then** the poller includes it in the next cycle.

---

### User Story 5 — View Ignored Triggers (Priority: P3)

The user checks `/triggers/ignored` to see which incoming Jira tickets or alerts were received but did not match any active rule, with the rejection reason.

**Acceptance Scenarios**:

1. **Given** a Jira ticket PHX-88888 (assignee=other.user) received by the poller, **When** no rule matches, **Then** it appears in `/triggers/ignored` with reason "no matching rule: assignee mismatch".
2. **Given** an ignored trigger, **When** the user clicks "Convert to mission (bypass filters)", **Then** a mission is created manually for that trigger after confirmation.

---

### Edge Cases

- What if two rules have the same priority and both match? → First one (by `id` asc) wins. Both are logged in `filter_match_log`.
- What if the JQL references `currentUser()` but no user context is set? → Rule test fails with helpful error; poller uses hardcoded username from rule config instead.
- What if a rule's `poll_interval_seconds` is set to 0? → Minimum enforced to 30s.
- What if Postgres is unavailable when the poller runs? → Circuit breaker activates, poller backs off with exponential retry, alert surfaced in UI header.

---

## Requirements

### Functional Requirements

- **FR-001**: System MUST auto-insert bootstrap Jira rule on first install (via Alembic seed migration).
- **FR-002**: UI MUST provide 2 modes for rule criteria editing: JQL free text and form (project, assignee, status, issuetype, priority, labels, component, text selects).
- **FR-003**: Form mode MUST generate valid JQL from selected values and display it for transparency.
- **FR-004**: `PUT /v1/filter-rules/{id}` changes MUST take effect on the next poller cycle without server restart.
- **FR-005**: `POST /v1/filter-rules/{id}/test` MUST execute the rule's JQL/matchers against the live source (Jira via MCP, alertmanager) and return ≤10 sample matches.
- **FR-006**: All trigger evaluations MUST be logged to `filter_match_log` (matched=true/false, reason).
- **FR-007**: UI `/triggers/ignored` MUST display rejected triggers with: source, key/payload summary, reason, received_at.
- **FR-008**: A "Convert to mission" action on ignored triggers MUST create a mission bypassing filters (requires explicit user confirmation).
- **FR-009**: Rules with invalid JQL (detected at test-time) MUST be marked with a warning badge in the UI. They are still saved but flagged.
- **FR-010**: `poll_interval_seconds` per rule MUST be configurable, with minimum 30s enforced server-side.

### Key Entities (see spec 001 for full entity definitions)

- **FilterRule**: `id`, `tenant`, `scope` (jira|alertmanager|care), `name`, `enabled`, `priority`, `poll_interval_seconds`, `criteria` (JSONB).
- **FilterMatchLog**: `id`, `rule_id`, `trigger_id`, `matched` (bool), `reason`, `matched_at`.

---

## Success Criteria

- **SC-001**: Bootstrap rule present and active after fresh install (0 manual steps).
- **SC-002**: A new team-member filter rule can be added via form mode in <2 minutes with no JQL knowledge.
- **SC-003**: Rule toggle change is reflected in poller behavior within 60 seconds.
- **SC-004**: 100% of trigger evaluations (match or reject) appear in `filter_match_log`.
- **SC-005**: `/triggers/ignored` shows all rejected triggers with reasons within 24h of receiving them.

---

## Assumptions

- MCP `c4-atlassian` supports JQL search via `jira_search` tool. The Carrefour instance uses standard Jira Cloud JQL syntax.
- Jira assignee values are email-format usernames (e.g., `arabaaoui`, not full email) — to be confirmed during dogfooding.
- The UI form selects for `project`, `assignee`, `status`, `issuetype`, `priority` use static lists loaded from Jira metadata API at page load (not real-time search). For v0, static values are acceptable.
- Alertmanager matcher fields (`alertname`, `severity`, `cluster`, `namespace`) are sufficient for v0 alertmanager rules. Label cardinality is manageable.
