# DataPulse Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist accurate profiles for uploaded CSV/JSON data and let users inspect them from a dataset detail page.

**Architecture:** A profiling service loads only the generated-name original file, normalizes values in a copy, infers column kinds, and emits JSON-safe metrics. A one-to-one SQLAlchemy profile row is upserted through profile endpoints. React adds a routed dataset detail view that fetches dataset metadata, preview rows, and saved/generated profiles through the existing API client.

**Tech Stack:** Existing FastAPI, SQLAlchemy, Alembic, Pandas, NumPy, React, TypeScript, Recharts, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-11-11-datapulse-phase-2-design.md` and the user-provided Phase 2 brief.

## Global Constraints

- Implement Phase 2 only; do not add ETL or Airflow.
- Preserve uploaded raw files and all existing Phase 1 routes.
- Do not expose storage paths or internal exception details.
- Do not add an unexplained quality score or fabricated metrics/charts.
- Enforce configurable full-file profiling limit `MAX_PROFILE_MB` (default 25 MB).
- Do not reset, drop, or run destructive tests against the configured Neon database.

## Review Focus

- Identifier-like numeric columns: classify as identifiers rather than measures; service test.
- Blank and non-finite numeric values: count as missing and keep stats JSON-safe; service test.
- Date strings with invalid entries: avoid calling a mixed column wholly datetime; service test.
- Header-only/zero-row datasets: return finite zero-safe profile values; service test.
- Missing/corrupt/unsupported or oversized source: safe controlled HTTP errors; endpoint tests.

### Task 1: Profiling engine and report shape

**Files:** Create `backend/app/services/profiling_service.py`, `backend/tests/test_profiling.py`.

**Interfaces:** `build_profile(frame: pandas.DataFrame) -> dict`; `load_dataset_frame(path: Path, format: str, max_bytes: int, storage_root: Path) -> DataFrame`. The explicit root argument verifies stored-source paths remain inside the configured storage directory.

- [x] Write metric tests for missing/duplicates, numeric summaries, categorical top values, empty columns/frames, identifier inference, date inference, and JSON-safe non-finite values.
- [x] Run the focused tests and confirm expected assertion failures.
- [x] Implement non-mutating normalization, type inference, dataset/column summaries, and bounded CSV/JSON loading.
- [x] Run profiling tests.

### Task 2: Persistence, migration, and API

**Files:** Create `backend/app/models/dataset_profile.py`, `backend/app/schemas/profiling.py`, `backend/migrations/versions/0002_dataset_profiles.py`; modify dataset model, API router registration, dataset routes, config; tests in `backend/tests/test_profiling_api.py`.

**Interfaces:** `DatasetProfile` stores `profile_data`, `generated_at`, `updated_at`; route path `/api/datasets/{dataset_id}/profile` supports POST/GET and `/refresh` supports POST.

- [x] Write API tests for CSV/JSON profiles, GET persistence, refresh updates, not found, missing/corrupt file, unsupported format, size limit, and delete cascade.
- [x] Run tests and confirm profile-generation assertions fail against the existing API.
- [x] Add JSONB-on-PostgreSQL profile model and non-destructive migration; keep SQLite-compatible tests.
- [x] Implement safe profile loading, update/upsert, retrieval, refresh, and deletion cascade.
- [x] Run API and prior Phase 1 tests; upgrade isolated SQLite migration and check schema.

### Task 3: Dataset profile experience

**Files:** Create `frontend/src/pages/DatasetDetail.tsx`, `frontend/src/types/profile.ts`; modify dataset API service/types, `Datasets.tsx`, `App.tsx`, and styles; tests in `frontend/src/services/api.test.ts`.

- [x] Add API-client tests for profile GET/generate/refresh request methods.
- [x] Implement dataset detail routing and accessible Overview, Data Preview, and Data Profile tabs.
- [x] Show real summary metrics, searchable profile columns, per-column numeric/categorical details, and category chart from API profile data; add loading, empty, error, and success states.
- [x] Run frontend tests and production build.

### Task 4: Documentation and final regression check

**Files:** Modify `README.md`.

- [x] Document migration, profiling limit, endpoints, interpretation rules, and manual workflow.
- [x] Run complete backend/frontend tests and confirm Phase 1 upload, listing, preview, delete, and health tests remain green.
