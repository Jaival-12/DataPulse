# DataPulse Profiling Improvements Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Phase 2 profiles accurate and useful for mixed numeric, formatted numeric, date, and identifier columns.

**Architecture:** Extend `build_profile` and its safe parsers in the existing profiler. Preserve the profile endpoint and report envelope, adding JSON fields for conversion counts, date ranges, identifier uniqueness, samples, and numeric histograms. Extend existing TypeScript report types and `ColumnDetails` rendering to consume those fields.

**Tech Stack:** Existing Python, Pandas, NumPy, FastAPI, pytest, React, TypeScript, Recharts, Vitest.

**Spec:** `docs/superpowers/specs/2026-11-11-profiling-improvements-design.md` and user request.

## Global Constraints

- Preserve profile endpoint paths, JSONB persistence, and migrations.
- Do not modify source files or begin Phase 3.
- Missing values remain distinct from invalid conversions.
- All displayed metrics and distributions come from stored profile responses.
- Keep tests isolated from the configured Neon database.

## Review Focus

- Comma grouping: accept `1,499`, reject malformed grouping; backend test.
- Mixed quantities: report numeric and invalid counts without categorical fallback; backend test.
- Impossible date: count as invalid; backend test.
- Date-only versus ISO datetime: return distinct labels and valid ranges; backend test.
- Repeated IDs: uniqueness/duplicate counts ignore missing IDs and avoid a frequency chart; backend test.

### Task 1: Profiler and backend coverage

**Files:** Modify `backend/app/services/profiling_service.py`, `backend/tests/test_profiling_api.py`.

**Interfaces:** Keep `build_profile(DataFrame) -> dict`; retain `numeric_statistics` and `categorical_statistics`, add `identifier_statistics`, `date_statistics`, and numeric distribution data.

- [ ] Add failing tests for mixed numbers, formatted commas, date formats/invalid dates, identifier duplication, and mixed CSV/JSON data.
- [ ] Run the new tests and confirm failures are behavioral.
- [ ] Implement strict parsers, type classification, and safe type-specific profile details.
- [ ] Run backend tests.

### Task 2: Frontend type-specific detail rendering

**Files:** Modify `frontend/src/types/profile.ts`, `frontend/src/pages/DatasetDetail.tsx`, `frontend/src/pages/dataset-detail.css`; add/update frontend tests.

- [ ] Add failing tests for rendering numeric-mixed counts, date ranges, and identifier uniqueness without a chart.
- [ ] Implement type badges/details and actual numeric histogram rendering.
- [ ] Run frontend tests and build.

### Task 3: Documentation and final verification

**Files:** Modify `README.md`.

- [ ] Document inference rules, strict date handling, numeric conversion, identifiers, and limitations.
- [ ] Run complete backend/frontend suites and production build; preserve existing API and migration checks.
