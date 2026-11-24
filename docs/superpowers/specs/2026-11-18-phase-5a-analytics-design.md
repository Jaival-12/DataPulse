# DataPulse Phase 5A Analytics Backend

## Intent and scope

Provide on-demand analytics for uploaded and ETL-processed CSV/JSON datasets using their real file contents. Preserve all source/output bytes and existing Phase 1–4 behavior. Phase 5B frontend work, persistence/history, migrations, background workers, arbitrary expressions, and generated/fabricated data are out of scope.

## Architecture

Add a typed `/api/analytics` router, Pydantic request/response schemas, a reusable analytics service, shared safe conversion/statistics helpers, and deterministic insight rules. Resolve source files through the existing dataset storage-key/path validation and processed files through `safe_processed_path`; load each file once per request with `load_dataset_frame` and the configured `max_profile_mb` limit. Reuse `build_profile`, `_parse_number`, and `_parse_date` where their semantics fit. No database model or migration is needed: analytics are calculated on demand.

Support overview and per-column summaries, bounded categorical top values and numeric histograms/statistics, pairwise Pearson correlations with observation counts, daily/weekly/monthly time series, bounded group aggregation, lineage-aware dataset comparisons, and deterministic insights tied to calculated evidence. For comparisons, original-to-processed requires the processed output's `source_dataset_id` to match; processed-to-processed requires both outputs to share that source. Exact column names determine common/added/removed columns; report a rename candidate only where value sequences match exactly, since name-only heuristics cannot prove a rename.

## API direction

- `GET /api/analytics/datasets/{dataset_id}/overview|columns|columns/{column_name}|correlation|insights`
- `POST /api/analytics/datasets/{dataset_id}/timeseries|aggregate`
- Equivalent processed-dataset endpoints for overview, columns, column detail, correlation, timeseries, aggregate, and insights.
- `POST /api/analytics/compare` with typed original/processed references.

All outputs are typed and JSON-safe. Bound top values, histogram bins, aggregate groups, insight counts, and pairwise work. Reject unknown columns/operations, invalid date parameters, unrelated comparison lineage, malformed sources, unsupported formats, and oversized files with safe HTTP errors.

## Scoring and interpretation

Analytics do not produce a quality score. Numeric invalids remain separate from missing values and are never coerced to zero. Date invalids and missing dates remain separate. Correlations are null when fewer than two pairwise observations exist or either input is constant. Time series omit invalid/missing dates and report their counts. Group aggregates skip invalid numeric values and include valid/missing/invalid measure counts. Insights are rule-based observations with supporting values and are not causal or statistical-significance claims.

## Approaches considered

1. **Shared per-request analytics service (selected):** load once, compute bounded in-memory results, keep routes thin, reuse profiling and safe-path helpers. This matches the current synchronous architecture and avoids extra storage state.
2. **Separate loader/statistics logic in each route:** superficially local, but duplicates parsing, path checks, and limits and risks inconsistent output.
3. **Persist analytics snapshots:** supports history but requires migrations, invalidation, and stale-file policy not requested for 5A; excluded.

## Verification

Use temporary SQLite test databases and temporary file storage. Cover numeric parsing/stats, categorical counts, dates and granularities, correlation/constant columns, group aggregation/limits, comparison lineage and schema drift, insights, empty/all-missing inputs, malformed files, API validation/errors, and size limits. Run the complete backend suite and migration checks. No migration is expected. Update README with routes, examples, local setup, and limitations.
