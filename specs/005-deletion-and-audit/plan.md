# Implementation Plan: Deletion and Audit Trail

**Branch**: `005-deletion-and-audit` | **Date**: 2026-05-11 | **Spec**: [specs/005-deletion-and-audit/spec.md](spec.md)
**Input**: Feature specification from `/specs/005-deletion-and-audit/spec.md`

## Summary

The platform currently lacks a way to remove obsolete Knowledge Base cards or investigation missions. This plan introduces a cascading deletion mechanism for Missions and a physical file removal for KB cards, both tracked via a new `SystemAudit` table for compliance and operational transparency.

## Technical Context

**Language/Version**: Python 3.12, TypeScript 5.4  
**Primary Dependencies**: FastAPI, SQLAlchemy, Next.js, Lucide React  
**Storage**: PostgreSQL (Missions, Audits, Triggers), Local Filesystem (KB Markdown cards)  
**Testing**: pytest (Backend), manual verification (Frontend)  
**Target Platform**: Linux server (Dockerized)
**Project Type**: Full-stack Web Service

## Project Structure

### Documentation (this feature)

```text
specs/005-deletion-and-audit/
├── plan.md              
└── tasks.md             
```

### Source Code

```text
api/
├── routes/
│   ├── missions.py      # New DELETE /v1/missions/{id}
│   └── kb.py            # New DELETE /v1/kb/cards/{slug}
core/
├── models.py            # SystemAudit table definition
├── kb_writer.py         # delete_card() implementation
web/
├── app/
│   ├── missions/
│   │   └── page.tsx     # Integration of Delete action
│   ├── kb/
│   │   └── page.tsx     # Integration of Delete action
├── components/
│   └── DeleteConfirmModal.tsx # Reusable confirmation UI
```

**Structure Decision**: Standard full-stack layout of the project is maintained. Deletion logic is localized in the existing route handlers and core writer classes.
