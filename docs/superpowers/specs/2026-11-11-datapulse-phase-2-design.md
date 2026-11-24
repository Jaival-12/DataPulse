# DataPulse Phase 2: Ingestion and Profiling Design

## Intent

Add an inspectable, persisted profile for each uploaded dataset so users can understand missingness, duplicates, inferred types, numeric distributions, and category frequency without changing the source file. Keep Phase 1 upload, catalog, preview, and delete behavior intact.

## Goals

- Generate CSV and JSON profiles from the current generated-name source file.
- Persist one refreshable profile per dataset, with PostgreSQL JSONB in production and portable JSON in isolated SQLite tests.
- Detect numeric, categorical, identifier, boolean, date, and empty columns; compute transparent counts and summary statistics without a quality score.
- Bound in-memory profile work using configurable `MAX_PROFILE_MB` and return safe errors for inaccessible, unsupported, malformed, empty, or too-large sources.
- Provide dataset detail navigation with Overview, Preview, and Profile tabs; render real profile data and responsive category frequencies.
- Extend isolated tests and Alembic migration without touching or resetting the configured database.

## Non-goals

ETL pipelines, Airflow, Phase 4 quality scores, anomaly detection, background jobs, chunked profiles, or automatic profiling during upload.

## Approaches

1. **Profile synchronously on upload.** This makes every upload immediately profiled, but increases upload latency and risks changing the existing ingestion path for larger files.
2. **Generate and refresh through explicit profile endpoints (chosen).** Keep existing upload semantics; the profile page can load a saved report or request generation/refresh from the original file. This matches the requested endpoints and bounds expensive work to a user action.
3. **Queue background profile work.** This scales better for large inputs but introduces a job system outside Phase 2 scope.

## Data and API decisions

- Add `DatasetProfile` with UUID-string primary key, unique `dataset_id`, cascading FK, profile JSON, generated and updated timestamps.
- Use SQLAlchemy `JSON` with PostgreSQL `JSONB` variant so SQLite fixtures can exercise persistence; migration creates JSONB on PostgreSQL.
- Endpoints: `POST /api/datasets/{id}/profile`, `GET /api/datasets/{id}/profile`, and `POST /api/datasets/{id}/profile/refresh`.
- POST and refresh calculate from the unchanged source and upsert the same profile row. GET returns 404 when no report exists.
- Mark `id`, `uuid`, `*_id`, `*_key`, `identifier`, and common contact/postal identifiers as identifiers rather than numeric measures. Parse date-like string columns only when all present values parse.
- Treat null/NaN/NaT, whitespace-only strings, and non-finite numeric values as missing. Duplicate percentage uses all records as denominator; per-column uniqueness uses non-null values. Percentages are rounded to four decimals. Numeric stats omit non-finite values; categorical tops contain at most ten values.
- Empty tabular frames return zero-safe metrics. Files with no columns remain valid only when supplied to the profiling service directly; current upload validation remains unchanged.
- Full-file in-memory profiling is limited to `MAX_PROFILE_MB` (default 25 MB). Larger files fail clearly; chunked processing is a later extension.
- The profile tab presents source metadata, summary metrics, issue indicators based on observed nonzero values, searchable columns, numeric summaries, and a category frequency chart. It displays no arbitrary quality score.

## Existing project context

Backend files are under `backend/app`; SQLAlchemy models and a first Alembic revision already exist. Upload parsing is in `services/ingestion.py`, dataset routes in `api/datasets.py`, and the frontend currently has a dataset catalog with an inline preview modal. New work extends those layers and introduces a dataset detail route; it does not replace Phase 1 structure.
