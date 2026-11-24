# DataPulse Phase 5A Analytics Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reusable, on-demand analytics APIs for original and processed datasets without modifying the files or persisting analytics state.

**Architecture:** Thin FastAPI endpoints call a shared Pandas analytics service. Safe dataset/processed loaders reuse existing path validation, size limits, profile type inference, numeric/date parsing, and JSON-safe serialization. Deterministic insights and typed request/response models remain separate from route handlers.

**Tech Stack:** Python, FastAPI, Pandas, NumPy, Pydantic, SQLAlchemy read-only metadata access, Pytest.

**Spec:** `docs/superpowers/specs/2026-11-18-phase-5a-analytics-design.md`

## Global Constraints

- Compute only from actual stored dataset contents; never fabricate statistics.
- Never mutate original or processed files.
- Do not add persistence, migrations, frontend code, or background workers.
- Respect `settings.max_profile_mb` and existing path validation.
- Bound category, histogram, comparison, insight, correlation, and aggregate responses.
- Numeric invalid values are not zero; date invalids/missing values are reported separately.
- Comparisons require matching stored source lineage.
- Never execute user expressions or construct unsafe SQL.

## Review Focus

- A malformed/unavailable/oversized stored file returns a safe error without leaking local paths or stack traces.
- An all-missing or constant numeric column returns null statistics/correlations rather than fabricated values.
- Dates with impossible values are excluded and counted; week/month bins stay chronological.
- Thousands of categories or group keys remain bounded by documented limits.
- Processed comparisons from different source datasets are rejected, including when both references exist.

---

### Task 1: Reusable analytics helpers and engine

**Files:** create `backend/app/utils/analytics_helpers.py`, `backend/app/services/analytics_service.py`, `backend/app/services/analytics_insights.py`, and `backend/tests/test_analytics_engine.py`.

- [x] Add failing tests for numeric parsing/statistics and categorical top-value limits.
- [x] Add failing tests for valid/invalid/missing dates, aggregation periods, correlation counts/constant columns, grouping, and empty inputs.
- [x] Implement pure dataframe functions with stable JSON-safe results and hard result limits.
- [x] Add deterministic insights with evidence fields and tests for positive and empty cases.
- [x] Run focused engine tests.

### Task 2: Schemas and shared safe source loading

**Files:** create `backend/app/schemas/analytics.py`; extend `backend/app/services/analytics_service.py`; test `backend/tests/test_analytics_api.py`.

- [x] Add typed requests for timeseries, aggregate and comparison; test invalid bounds, extra fields, invalid operations, and empty identifiers.
- [x] Add an original/processed resolver using `source_path`, `safe_processed_path`, `load_dataset_frame`, and `settings.max_profile_mb`.
- [x] Test missing IDs/files, malformed CSV/JSON, unsupported formats, size limits, and proof the file content is unchanged.
- [x] Run focused source-loading tests.

### Task 3: Analytics API

**Files:** create `backend/app/api/analytics.py`; modify `backend/app/main.py`; test `backend/tests/test_analytics_api.py`.

- [x] Add API tests for original and processed overview, columns/detail, correlation, timeseries, aggregate and insights.
- [x] Add API tests for compare, lineage rejection, schema additions/removals/rename candidates, and safe errors.
- [x] Implement thin, typed handlers for `/api/analytics/datasets/{id}/...`, `/api/analytics/processed-datasets/{id}/...`, and `/api/analytics/compare`.
- [x] Run focused API tests.

### Task 4: Documentation and full verification

**Files:** modify `README.md`.

- [x] Document architecture, endpoints, request/response examples, supported types, local execution, and limitations.
- [x] Run all backend tests and any configured static checks.
- [x] Verify migration head remains unchanged and no migration was added.
- [x] Report changed files, endpoint paths, test evidence, migration status, and limitations.
