# DataPulse Phase 3B Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate pipeline management, transformation building, synchronous execution/history/logs, and processed dataset browsing into the existing frontend.

**Architecture:** Extend the shared typed API client; add route-level pipeline and processed dataset pages; keep step configuration and execution detail modular; use existing layout and responsive dark styles. No backend changes are planned.

**Tech Stack:** Existing React, TypeScript, React Router, Vite, Lucide React, Vitest, and Testing Library.

**Spec:** `docs/superpowers/specs/2026-11-11-phase-3b-frontend-design.md`

## Global Constraints

- Preserve existing dataset upload, preview, delete, and profile behavior.
- Match Phase 3A endpoint paths and actual response schemas.
- Never evaluate arbitrary expressions or add fake execution progress/results.
- Use accessible step reordering controls; no new dependencies.
- Do not modify backend routes or database migrations.

## Review Focus

- Config normalization must match backend omission rules (`fill_missing` drop rows and null filters omit value) — Task 3 builder tests.
- Reordering/removing/renaming steps must keep downstream column choices consistent — Task 3 builder test.
- A failed execution remains a real failed run with logs and error details — Task 4 tests.
- Downloads must handle non-JSON file responses and API errors — Task 5 tests.
- Processed related names resolve from backend IDs without assuming embedded names — Task 5 tests.

### Task 1: Typed Phase 3A API client

**Files:** create `frontend/src/types/pipeline.ts`; modify `frontend/src/services/api.ts`; test `frontend/src/services/api.test.ts`.

- [ ] Add failing tests for paginated pipeline/execution/processed requests, create/update/delete/execute, execution detail/logs, processed preview, and blob download/error handling.
- [ ] Run focused API tests and confirm new calls are missing.
- [ ] Add exact TS response/request types and API functions using current base URL/error handling.
- [ ] Run API tests.

### Task 2: Application navigation and routes

**Files:** modify `frontend/src/App.tsx`, `frontend/src/layouts/AppLayout.tsx`; create route pages in Tasks 3–5; test navigation through page tests.

- [ ] Add failing route/nav tests for Pipelines, pipeline create/detail, Processed Datasets, and processed detail.
- [ ] Run focused tests and confirm routes are absent.
- [ ] Add lazy routes, active sidebar links, and location-aware breadcrumbs.
- [ ] Run route/page tests.

### Task 3: Pipeline catalog and visual builder

**Files:** create `frontend/src/pages/Pipelines.tsx`, `frontend/src/pages/PipelineDetail.tsx`, `frontend/src/components/PipelineStepEditor.tsx`, `frontend/src/pages/pipeline.css`; test `frontend/src/pages/Pipelines.test.tsx`.

- [ ] Add failing tests for catalog/history status, create, edit, add/configure steps, config validation, and move up/down.
- [ ] Run focused tests and confirm the UI behaviors are absent.
- [ ] Implement pipeline catalog, confirmation, create/edit forms, all operation config forms, normalization, schema evolution, and keyboard-accessible reordering.
- [ ] Run focused tests.

### Task 4: Synchronous execution and history/logs

**Files:** modify `frontend/src/pages/PipelineDetail.tsx`; create `frontend/src/components/ExecutionDetails.tsx`; test `frontend/src/pages/Pipelines.test.tsx`.

- [ ] Add failing tests for synchronous loading, success, failed status/error, paginated history, and detail/log retrieval.
- [ ] Run focused tests and confirm expected states are absent.
- [ ] Integrate execute/history/detail/log APIs and render actual status, timing, row counts, step counts, and logs.
- [ ] Run focused tests.

### Task 5: Processed datasets, preview, and download

**Files:** create `frontend/src/pages/ProcessedDatasets.tsx`, `frontend/src/pages/ProcessedDatasetDetail.tsx`, `frontend/src/pages/processed-dataset.css`; test `frontend/src/pages/ProcessedDatasets.test.tsx`.

- [ ] Add failing tests for listing and relation-name resolution, preview table, metadata, and download.
- [ ] Run focused tests and confirm the page is absent.
- [ ] Implement paginated catalog/detail, related dataset/pipeline resolution, preview, and blob download.
- [ ] Run focused tests.

### Task 6: README and final verification

**Files:** modify `README.md`.

- [ ] Document pipeline UI workflow, synchronous execution semantics, history/logs, and processed datasets.
- [ ] Run all frontend tests with `npm test -- --run`.
- [ ] Run `npm run build`.
- [ ] Review changes and confirm backend, API, migrations, and existing Phase 1/2 UI remain untouched.
