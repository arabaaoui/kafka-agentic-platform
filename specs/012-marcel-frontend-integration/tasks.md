# Tasks: Marcel Web Renew Frontend Integration

**Input**: Design documents from `/specs/012-marcel-frontend-integration/`
**Branch**: `012-marcel-frontend-integration`
**Prerequisites**: plan.md ✅, spec.md ✅

**Format**: `[ID] [P?] [Story?] Description — file path`
- **[P]** = parallelizable (different files, no incomplete dependencies)
- **[US#]** = user story (US1=brand tokens, US2=navigation/layout, US3=dashboard, US4=forms)

---

## Phase 1: Environment & Dependency Setup

**Purpose**: Configure local npm workspaces to successfully fetch and register the scoped Enterprise Marcel packages from Artifactory.

- [ ] T001 [P] [US1] Create npm registry redirect file pointing the `@marcel` scope to Enterprise's general JFrog Artifactory repository — `web/.npmrc`
- [ ] T002 [P] [US1] Create the TypeScript declaration file importing `@marcel/web-components/react` to allow Next.js TSX to compile custom HTML element tags without compiler errors — `web/marcel.d.ts`
- [ ] T003 [US1] Update `package.json` under the `web` project to declare dependencies on `@marcel/web-tokens`, `@marcel/web-components`, and `@marcel/icons` — `web/package.json`

**Checkpoint**: Run `npm install` inside `/web` folder to ensure Artifactory resolves packages and dependencies are fully populated.

---

## Phase 2: Foundational Styles & Global Hydrator

**Purpose**: Load global brand design variables and set up the browser Custom Elements loader to safely hydrate Stencil elements on Next.js client-side mount.

- [ ] T004 [US1] Create `marcel-provider.tsx` as a Client Component (`"use client"`) that triggers Stencil's browser custom element registration using `defineCustomElements` inside a single-mount `useEffect` — `web/app/marcel-provider.tsx`
- [ ] T005 [P] [US1] Update global CSS styles file to import `@marcel/web-tokens` CSS variable mappings and apply Enterprise's default `Ubuntu` typography properties as the body base font — `web/app/globals.css`
- [ ] T006 [US1] Update the root server-side layout file to import and wrap the active routes inside the newly created `<MarcelProvider>` client hydrator — `web/app/layout.tsx`

**Checkpoint**: Run `npm run dev` and open `/` to verify that there are no server-client HTML hydration mismatches or startup runtime exceptions.

---

## Phase 3: Layout & Navigation Integration (US2) 🎯 MVP

**Goal**: Align Sidebar navigation items and platform actions with Marcel typography and hover components.

**Independent Test**: Navigate through the core pages using the sidebar and verify that routing works flawlessly and styles inherit correctly.

- [ ] T007 [US2] Refactor the SideBar Component to replace Tailwind custom classes with Marcel's classes (e.g. `mrcl-body-m-regular`) and implement `<mrcl-button>` / `<mrcl-link>` components where applicable — `web/components/SideBar.tsx`

**Checkpoint**: Navigate through Dashboard, Missions, and Triggers to confirm that page transitions remain smooth and client-side driven.

---

## Phase 4: Dashboard Page Modernization (US3)

**Goal**: Rework the main operations control page using semantic Marcel elements.

**Independent Test**: Dashboard displays stat cards, status lists, and action items rendered natively with web components under unified Enterprise branding.

- [ ] T008 [US3] Refactor the home page dashboard to replace custom stat cards with `<mrcl-card>`, custom status colors with `<mrcl-status-indicator>`, and use `@marcel/web-tokens` typographical classes globally — `web/app/page.tsx`

---

## Phase 5: Verification & Production Compilation

- [ ] T009 [P] Run static type-checking to ensure zero TS compiler violations: `npm run type-check` inside `web` — no file change, verification only
- [ ] T010 [P] Run Next.js compiler build to confirm production compilation sanity: `npm run build` inside `web` — no file change, verification only
