# DataPulse Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a runnable DataPulse foundation with real CSV/JSON uploads, dataset listing and preview, health reporting, and a connected dark React dashboard.

**Architecture:** FastAPI + SQLAlchemy persists dataset metadata and column profiles; validated originals are kept under generated names in backend storage. A Vite React client consumes paginated API endpoints. PostgreSQL is configured through `DATABASE_URL`; SQLite is the default local development database.

**Tech Stack:** Python, FastAPI, Pydantic, SQLAlchemy, Pandas; React, TypeScript, Vite, Tailwind, Recharts, Lucide, React Router.

**Spec:** User-provided DataPulse Phase 1 request.

## Global Constraints

- Implement Phase 1 only.
- Never trust client filename, extension, or MIME type; enforce configurable upload size.
- Preserve raw datasets and do not expose internal storage paths.
- Do not hardcode credentials; provide `.env.example`.
- No fake analytics: dashboard metrics derive from API data.
- Keep schema/profile and endpoint tests; do not claim unverified integrations.

## Review Focus

- Spoofed extension/content mismatch: reject upload; test CSV/JSON content validation.
- Oversized upload: reject before persistence; test configured limit.
- Traversal filename: store under generated key and return safe display name; test.
- Empty/corrupt content: safe 4xx response; test.
- Missing database or raw file: health reports disconnected and preview returns safe not-found; exercise where feasible.

### Task 1: Backend ingestion and metadata

**Files:** `backend/app/` configuration, db, models, schemas, repositories, services, API routes; `backend/tests/`; requirements and `.env.example`.

- [ ] Write tests for health, CSV/JSON upload, list, preview, invalid content, safe names, pagination.
- [ ] Run tests and confirm expected failures.
- [ ] Implement SQLAlchemy metadata, generated storage keys, validated parsing/profile, and endpoints.
- [ ] Run backend suite.

### Task 2: Connected dashboard

**Files:** `frontend/` Vite app, routes, API service, layout, pages, styles, package/config.

- [ ] Add frontend API/type tests for response handling and upload validation.
- [ ] Run tests to verify failures.
- [ ] Implement responsive dark dashboard with dataset uploads/list/preview and backend health.
- [ ] Run frontend tests and production build.

### Task 3: Documentation and integration

**Files:** root `README.md`, `docker-compose.yml`, `.gitignore`.

- [ ] Document environment, database, storage, run commands, API and limitations.
- [ ] Start backend and frontend, exercise CSV and JSON end-to-end if dependencies/environment permit.
- [ ] Report exact checks and unresolved environment constraints.
