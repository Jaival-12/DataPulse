# DataPulse Phase 4 Quality Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Analyze original and processed datasets for transparent quality dimensions, persist reports/issues, and expose them through APIs and the dashboard.

**Architecture:** Reuse `load_dataset_frame`, `build_profile`, and `safe_processed_path`; keep analysis pure and bounded, then persist report and issue rows in a new Alembic migration. Add typed API calls and React quality views using existing routes, dark styling, and Recharts.

**Tech Stack:** Python, FastAPI, Pandas, NumPy, SQLAlchemy, Pydantic, Alembic, React, TypeScript, Vite, Recharts, Vitest, Pytest.

**Spec:** `docs/superpowers/specs/2026-11-18-phase-4-data-quality-design.md`

## Global Constraints

- Source and processed files are read-only; use existing path validation and size limits.
- Configured rules are structured and allow-listed; never evaluate user code.
- Samples, issue sets, and API collections are bounded.
- Not-applicable dimensions are null and excluded from a normalized weighted score; never silently award 100.
- Report exactly one source and preserve weights/methodology for historical interpretation.
- Rule-based correctness is not a claim of real-world accuracy.
- Do not modify existing migrations or Phase 1–3 behavior.

## Review Focus

- Empty/zero-column datasets produce null applicable dimensions and a safe `Not scored` state.
- Whitespace-only values count as missing, while leading/trailing whitespace remains detectable as a consistency issue.
- Malformed/impossible dates and non-numeric values are reported without modifying source values.
- Overlapping identifier/unique-rule findings do not double-count one issue.
- Processed comparisons reject reports from a different source lineage.
- Malicious/malformed storage paths never escape configured storage roots.

### Task 1: Pure quality analysis engine

**Files:** create `backend/app/services/quality_engine.py`; test `backend/tests/test_quality_engine.py`.

- [x] Add failing calculation tests for completeness, validity, uniqueness, consistency, structured rules, weighted scoring, missing dimensions, empty frames, severity, and bounded samples.
- [x] Run the quality engine tests and verify they fail for missing implementation.
- [x] Implement deterministic issue generation with a capped sample list and a versioned weighted score result.
- [x] Run the engine tests.

### Task 2: Models and migration

**Files:** create `backend/app/models/data_quality.py`; modify model exports and `backend/migrations/env.py`; create next migration under `backend/migrations/versions/`.

- [x] Add metadata/model tests for source exclusivity, JSON fields, indexes, and cascade behavior.
- [x] Implement report and issue models and migration only after the tests describe required constraints.
- [x] Run model tests and verify migration upgrade/downgrade on a temporary SQLite database.

### Task 3: API schemas, services, and routes

**Files:** create quality schemas, service orchestration and router; modify `backend/app/main.py`; test `backend/tests/test_quality_api.py`.

- [x] Add failing tests for original/processed analyze, persistence, report history/detail, pagination/filtering, bad IDs/rules, and storage path/size errors.
- [x] Implement bounded loading and atomic report/issue persistence with existing dependencies and safe loaders.
- [x] Register `/api/quality` routes and run API tests plus existing backend tests.

### Task 4: Frontend API/types and quality dashboard

**Files:** create `frontend/src/types/quality.ts` and quality page/components/styles; modify API client, routes, and sidebar; test API and quality page.

- [x] Add failing API and UI tests for actual score, dimension values, issue charts/table, loading/error/empty states, filters, and pagination.
- [x] Implement typed quality endpoints and live dashboard backed only by API data.
- [x] Run focused frontend tests and production type-check/build.

### Task 5: Dataset integrations and lineage comparison

**Files:** modify original and processed dataset detail pages; add reusable report history/comparison components; extend API and frontend tests.

- [x] Add failing tests for analyze actions, histories, loading/errors, and same-lineage comparisons including negative deltas and mismatched lineage.
- [x] Implement actions/history and comparison using persisted reports and source lineage IDs.
- [x] Run focused frontend tests.

### Task 6: Documentation and full verification

**Files:** modify `README.md`; optionally add migration/API notes under `docs/`.

- [x] Document score math, missing-dimension policy, rules, endpoints, migration, run steps, examples, and limitations.
- [x] Run all backend tests, all frontend tests, production build, and migration upgrade/downgrade verification.
- [x] Report actual changed files and any incomplete requirement or limitation.
