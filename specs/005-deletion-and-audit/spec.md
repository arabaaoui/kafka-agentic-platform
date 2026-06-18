# Feature Specification: Deletion and Audit Trail

**Feature Branch**: `005-deletion-and-audit`  
**Created**: 2026-05-11  
**Status**: Draft  
**Input**: User description: "Implement deletion for Missions and KB cards with audit tracing"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - KB Card Deletion (Priority: P1)

As an operator, I want to delete obsolete or incorrect Knowledge Base cards so that the platform's automated diagnostics remain based on accurate information.

**Why this priority**: Accuracy of the Knowledge Base is critical for the "Agentic" nature of the platform. Stale information can lead to incorrect automated remediations.

**Independent Test**: Can be fully tested by deleting a specific KB card through the UI/API and verifying that the `.md` file is gone and the `INDEX.md` no longer lists it.

**Acceptance Scenarios**:

1. **Given** a KB card exists in `kb/incidents/leak.md` and is listed in `kb/INDEX.md`, **When** the user clicks "Delete" and confirms, **Then** the file `leak.md` is deleted, `INDEX.md` is regenerated, and the card disappears from the KB gallery.
2. **Given** a KB card is deleted, **When** searching the Knowledge Base, **Then** the deleted card is no longer found.

---

### User Story 2 - Mission Deletion (Priority: P1)

As an administrator, I want to delete old, test, or failed investigation missions to maintain a clean and relevant mission history.

**Why this priority**: High volume of missions (especially failed or test ones) can clutter the UI and database, making it harder to find real production incidents.

**Independent Test**: Can be fully tested by deleting a mission from the Mission History page and verifying it no longer appears in the list or the database.

**Acceptance Scenarios**:

1. **Given** a mission with ID `PHX-DEV-TEST-001` exists with several agent outputs and an audit report, **When** the admin deletes it, **Then** the mission record, its agent outputs, and its audit report are all removed from the database.
2. **Given** a mission is deleted, **When** trying to access its detail page via URL, **Then** a 404 error is returned.

---

### User Story 3 - Deletion Audit Trail (Priority: P1)

As a security auditor, I want every deletion action to be logged in a dedicated audit trail so that we can track who deleted what and when.

**Why this priority**: Deletion is a destructive action. For compliance and troubleshooting, it's essential to have a non-repudiable record of these events.

**Independent Test**: Can be fully tested by performing a deletion and checking the `system_audit` table/log for a corresponding entry.

**Acceptance Scenarios**:

1. **Given** a user deletes a KB card, **When** the deletion is successful, **Then** a new record is created in the audit log containing the timestamp, user ID, resource type ("KB_CARD"), and the slug of the deleted card.

---

### User Story 4 - Admin Audit Dashboard (Priority: P2)

As an administrator, I want a dedicated dashboard to view the platform's audit trail so that I can easily monitor system changes and destructive actions without querying the database directly.

**Why this priority**: Operational transparency is key for a production-grade platform. Administrators need a user-friendly way to verify the history of actions like deletions.

**Independent Test**: Can be fully tested by navigating to the "Admin Audit" menu and verifying that a list of recent actions is displayed with correct timestamps and metadata.

**Acceptance Scenarios**:

1. **Given** multiple administrative actions have been performed, **When** the admin visits `/admin/audit`, **Then** a table is displayed showing all events in reverse chronological order.
2. **Given** a large number of audit logs, **When** the admin navigates between pages, **Then** the pagination controls work correctly and load the expected data.
3. **Given** a specific action type needs to be investigated, **When** the admin applies a filter, **Then** the table only displays events matching that criteria.

- What happens when a KB card being deleted is referenced as a "related card" by another card? (Default: Reference becomes a dead link, future index regeneration will handle it or we can leave it as a known behavior).
- How does the system handle concurrent deletion requests for the same mission? (Default: Second request should return 404).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a DELETE endpoint for KB cards identified by slug.
- **FR-002**: System MUST physically delete the corresponding `.md` file from the configured `KB_DIR/incidents` directory.
- **FR-003**: System MUST trigger an immediate regeneration of `kb/INDEX.md` after a KB card is deleted.
- **FR-004**: System MUST provide a DELETE endpoint for Missions identified by `mission_id`.
- **FR-005**: System MUST perform a cascading deletion of all database records related to a mission (Agent Outputs, Audits).
- **FR-006**: System MUST persist a record of every deletion in a `SystemAudit` table.
- **FR-007**: UI MUST implement a "Delete" button with a confirmation modal for both KB cards and Missions.

### Key Entities

- **SystemAudit**: Represents a trace of an administrative action. Attributes: `id`, `action`, `resource_type`, `resource_id`, `metadata`, `created_at`, `created_by`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of successful deletions are reflected in the `SystemAudit` table.
- **SC-002**: KB Index regeneration after deletion completes in under 500ms.
- **SC-003**: No orphaned agent outputs or audit reports remain in the database after a mission is deleted.

## Assumptions

- We assume the operator has sufficient filesystem permissions to delete files in the `KB_DIR`.
- We assume that the `SystemAudit` table will be used for all future administrative actions, not just deletions.
