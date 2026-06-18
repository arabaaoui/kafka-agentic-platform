# Feature Specification: Marcel Web Renew Frontend Integration

**Feature Branch**: `012-marcel-frontend-integration`  
**Created**: 2026-06-12  
**Status**: Draft  
**Input**: User description: "Integrate Carrefour's Marcel Web Renew Design System into the Next.js frontend of the Kafka Agentic Platform."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Brand Theme & Token Integration (Priority: P1)

Integrate the official `@marcel/web-tokens` styling library into the global Next.js CSS layout to apply Carrefour's colors, spacings, and typographies globally.

**Why this priority**: It is the foundation of the brand integration. All components and styling depend on these tokens and fonts.

**Independent Test**: Start the frontend development server and verify that the page background, general spacing, and typography inherit from Carrefour's custom CSS custom properties (like `--mrcl-font-family-default`).

**Acceptance Scenarios**:

1. **Given** the frontend dev server is running, **When** loading the root layout, **Then** the global font bunny `Ubuntu` is requested and applied globally.
2. **Given** custom styles are loaded, **When** using token variables (e.g. `var(--mrcl-color-background-primary-dark)`), **Then** they correctly resolve to Carrefour's brand color hex codes.

---

### User Story 2 - Layout & Sidebar Rework (Priority: P1)

Refactor the platform's core layout and Sidebar to use the modern design style, integrating `@marcel/web-components` links, icons, and buttons where applicable while preserving Next.js App Router client-side routing.

**Why this priority**: Navigating the platform is the primary user journey. Sidebar and navigation must look consistent and work flawlessly without triggering page reloads.

**Independent Test**: Click sidebar navigation items and confirm they transition between pages instantly using Next.js client-side router, retaining the dynamic Marcel look.

**Acceptance Scenarios**:

1. **Given** the Sidebar layout is loaded, **When** hovering over links, **Then** they show Marcel hover tokens and styling.
2. **Given** a user clicks on "Missions" or "Triggers" in the sidebar, **When** the page transitions, **Then** routing is handled client-side without full-page reloads.

---

### User Story 3 - Dashboard Modernization (Priority: P2)

Rework the home Dashboard (`app/page.tsx`) by replacing generic Tailwind/HTML divs and cards with sémantic Marcel Web Components (like `<mrcl-card>`, `<mrcl-badge>`, and `<mrcl-button>`) representing active missions, diagnostic SLAs, and operational status control.

**Why this priority**: The Dashboard is the initial screen users see. It needs to present operational metrics and health status with top-tier, unified branding.

**Independent Test**: Open the home page and verify that all stat boxes and system status rows are rendered using hydrated Stencil web components.

**Acceptance Scenarios**:

1. **Given** the dashboard is loaded, **When** the backend is online, **Then** status indicators show green success indicators using `<mrcl-status-indicator state="success">`.
2. **Given** the action buttons are displayed, **When** clicking "Launch Mission", **Then** the action registers and triggers the expected React click handler.

---

### User Story 4 - Form and Filter Controls (Priority: P2)

Replace the standard HTML form elements (like selects and text inputs in settings/filters) with `<mrcl-select>`, `<mrcl-input-text>`, and `<mrcl-radio-group>` components.

**Why this priority**: Ensures settings and filters look highly professional and match the brand's WCAG accessibility guidelines.

**Independent Test**: Change filtering criteria or add filter rules in settings and verify that the select/input values are correctly bound to the state and submitted to the API.

**Acceptance Scenarios**:

1. **Given** a settings form, **When** selecting an item from `<mrcl-select>`, **Then** the React state is updated with the selected value.
2. **Given** an invalid entry in `<mrcl-input-text>`, **When** triggering validation, **Then** error/warning helper text displays according to Marcel styling rules.

---

### Edge Cases

- **SSR Hydration Mismatch**: Stencil.js web components register themselves purely client-side on the `window` object. Next.js server-side rendering must bypass pre-rendering the shadow DOM structure, and defer element hydration until the client takes over to prevent hydration mismatch.
- **Custom Event Binding**: In React 18, standard custom events emitted by Web Components (e.g. custom `onChange` or `onSelect`) are not automatically mapped to React props. We must bind them using React `ref`s and `addEventListener` or create thin wrappers where necessary.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST load and apply `@marcel/web-tokens` globally across all views.
- **FR-002**: The system MUST register `@marcel/web-components` custom elements dynamically on client-side hydration.
- **FR-003**: TypeScript compiler MUST compile TSX pages containing `<mrcl-*>` tags with zero errors.
- **FR-004**: Custom web components MUST capture and propagate standard React `onClick` and event handlers.
- **FR-005**: All UI changes MUST maintain responsive behavior, resizing fluidly on standard tablet and desktop widths.

### Key Entities *(include if feature involves data)*

- **MarcelProvider**: A React client-side component responsible for lazy-loading and invoking Stencil's `defineCustomElements()` once the document body is hydrated.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of the Next.js production build (`npm run build`) compiles successfully with zero TypeScript typings errors regarding `<mrcl-*>` tags.
- **SC-002**: The home Dashboard exhibits an initial load with no visible layouts shifts (CLS < 0.1) during client-side hydration of Marcel custom elements.
- **SC-003**: Every core page (Dashboard, Missions, Triggers, Settings, KB) remains fully navigable with zero regression in functional API communications.

## Assumptions

- **Local Registry Access**: The developer machine is properly authenticated to the Carrefour Artifactory npm registry to fetch `@marcel` scoped packages.
- **Theme Compatibility**: Since the platform currently uses a dark layout (`className="dark" bg-slate-950`), Marcel's tokens are assumed to provide compatible dark-mode values or base themes.
