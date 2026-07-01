# Implementation Plan: Marcel Web Renew Design System Integration

**Branch**: `012-marcel-frontend-integration` | **Date**: 2026-06-12 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/012-marcel-frontend-integration/spec.md`

## Summary

Integrate Enterprise's "Marcel Web Renew" design system into the Next.js 14 (App Router) frontend of the Kafka Agentic Platform. This includes installing the official `@marcel/*` scoped packages from the Enterprise registry, configuring global typography and styles using `@marcel/web-tokens` CSS variables, creating a client-side hydrator `MarcelProvider` to register the custom elements, and refactoring the Sidebar and Dashboard pages to employ Marcel web components.

## Technical Context

**Language/Version**: React 18, Next.js 14, TypeScript 5.4+
**Styling**: Tailwind CSS v3, PostCSS, `@marcel/web-tokens` CSS variable definitions
**UI Components**: `@marcel/web-components` (Stencil-based Custom Elements), `@marcel/icons` (SVG sprites)
**Package Management**: npm (local package-lock.json under the `/web` subdirectory)
**Testing**: Next.js development server (local HMR), Next.js production compiler (`next build`)
**Performance Goals**: CLS (Cumulative Layout Shift) < 0.1 on hydration; zero compilation/type-checking errors.
**Constraints**: Stencil custom elements must be registered on the client-side `window` object, bypassing SSR pre-hydration mismatches. Standard React onClick/onChange handlers must bind cleanly.

## Constitution Check

| Principle | Status | Notes |
|---|---|---|
| I. Read-Only v0 | ✅ PASS | Frontend modifications only — no backend mutating tools added |
| II. Mission Isolation Plugin | ✅ PASS | No change to backend pipeline or isolation |
| III. Post Jira/Care opt-in | ✅ PASS | Standard API interaction unchanged |
| IV. Eval Suite ≥80% | ✅ PASS | Backend evaluation unaffected |
| V. Zero Secret Leakage | ✅ PASS | No credentials committed in frontend changes |
| VI. Skills = SKILL.md | ✅ PASS | Handled strictly under local codebase and Marcel AI skills parameters |
| VII. Agnostic by Design | ✅ PASS | The frontend uses Enterprise's brand design system natively as instructed |

**Gate result: ALL PASS** — proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/012-marcel-frontend-integration/
├── spec.md              ← specification file
├── plan.md              ← this file
└── tasks.md             ← implementation tasks file
```

### Modified Frontend Codebase (web/ subdirectory)

```text
web/
├── .npmrc               # NEW: redirect @marcel registry to Enterprise repo
├── marcel.d.ts          # NEW: global TypeScript JSX types import
├── package.json         # MODIFIED: add @marcel/* dependencies
├── app/
│   ├── globals.css      # MODIFIED: import @marcel/web-tokens variables
│   ├── layout.tsx       # MODIFIED: wrap app inside MarcelProvider client-hydrator
│   ├── marcel-provider.tsx # NEW: Client Component to load defineCustomElements()
│   └── page.tsx         # MODIFIED: rewrite Dashboard page using <mrcl-*> components
└── components/
    └── SideBar.tsx      # MODIFIED: rewrite SideBar using Marcel design links/buttons
```

## Key Integration Patterns

### 1. Registry Redirection (`.npmrc`)
To resolve packages from `@marcel/*`, we will create `/web/.npmrc` pointing to Enterprise's general Artifactory server:
```ini
@marcel:registry=https://enterpriserepo.fr.enterprise.com/artifactory/api/npm/chapter-front-components-npm-releases-local/
always-auth=true
```

### 2. Typings Configuration (`marcel.d.ts`)
To allow the React TSX compiler to parse custom Stencil elements natively without erroring, we include global react bindings at `/web/marcel.d.ts`:
```typescript
import '@marcel/web-components/react';
```

### 3. Client Hydrator Provider (`marcel-provider.tsx`)
Because web components are client-only browser primitives, we isolate registration inside a Client Component:
```typescript
"use client";

import { useEffect, useState } from "react";
import { defineCustomElements } from "@marcel/web-components/loader";

export default function MarcelProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    // Avoid double-registration and hydrate once loaded
    defineCustomElements();
    setReady(true);
  }, []);

  return <div key={String(ready)}>{children}</div>;
}
```

This ensures zero server-side rendering mismatch errors or initial layout shifts during hydration.
