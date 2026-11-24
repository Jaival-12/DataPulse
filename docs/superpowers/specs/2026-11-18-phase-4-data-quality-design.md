# DataPulse Phase 4: Data Quality Engine

## Intent

Evaluate uploaded and processed CSV/JSON datasets with transparent completeness, validity, uniqueness, consistency, and rule-based correctness reporting. Preserve source files and historical report interpretation while bringing the workflow into the existing dark dashboard.

## Goals and constraints

- Use the existing bounded dataset loader, Phase 2 profiler, processed-path validator, FastAPI dependencies, SQLAlchemy models, Alembic chain, and React/Vite components.
- Never mutate source files or evaluate arbitrary code. Cap sample values and issue payloads; paginate API collections.
- Persist one report source only: either a dataset or a processed dataset. Resolve comparison lineage through `ProcessedDataset.source_dataset_id`.
- Keep scoring weights and methodology version with every report. A dimension with no applicable checks is `null`, not 100; the overall score renormalizes configured weights across measured dimensions. If none are measured, score is null and label is `Not scored`.
- “Accuracy” is labeled **Rule-based correctness** and means only configured validation rules; it is not real-world truth.
- Synchronous analysis is acceptable within the existing `MAX_PROFILE_MB` bound. No background queue or Phase 5 work.

## Architecture

Add a pure `quality_engine` that accepts a loaded DataFrame and validated structured rules and returns score metadata plus bounded issue records. The API loads original files through the existing safe profiler loader and processed files through `safe_processed_path`, persists report and issues transactionally, and exposes paginated report/issue reads. The frontend consumes those APIs in a new quality overview and integrates analysis/history/comparison into the existing dataset and processed-dataset pages.

## Approaches considered

1. Derive quality from persisted profile data only. This avoids re-reading data but cannot distinguish whitespace-only cells or inspect non-normalized consistency; rejected.
2. Build a pure analyzer over the existing bounded loader and reuse `build_profile` for type-aware invalid counts. This is deterministic, non-mutating, testable, and stays within the current synchronous architecture; selected.
3. Introduce queued/background analysis. This prepares for large files but adds worker state and asynchronous UX beyond the current platform; deferred.

## Scoring and rules

Default weights are completeness 25%, validity 25%, uniqueness 20%, consistency 15%, rule-based correctness 15%. A missing dimension is excluded and remaining weights are normalized; score computation stores the method version, configured weights, applicable dimensions, and normalized denominator policy. Rules are a validated allow-list: required columns, not-null, unique, non-negative, greater-than, and bounded range. Rule values are scalars; no expressions are accepted. Severity is deterministic from issue type and affected-row rate, with required-column absence critical.

Consistency findings distinguish observed variants (whitespace, capitalization, date-format, and normalized categorical collisions) from recommendations; analysis never standardizes values.

## Data model and API

Add `DataQualityReport` and `DataQualityIssue`, indexes and foreign keys with cascades, and a check constraint enforcing exactly one report source. Persist dimension scores, scoring weights/methodology, rules, counts, status, and timestamps. API families cover analyze, report list/detail/issues, and source-specific history for original and processed datasets. Lists are paginated; issue lists filter by severity and dimension.

## Frontend

Add a Data Quality navigation section with live report data, overview score, dimensions, Recharts summaries, and a searchable/filterable issue explorer. Original and processed detail pages gain analyze controls and report histories. A processed report may compare only with an original report whose dataset ID equals the processed dataset's `source_dataset_id`; show positive, negative, or unchanged score/dimension/issue deltas without assuming improvement.

## Out of scope and known limits

No real-world accuracy claims, data rewriting, automatic standardization, arbitrary rule code, background workers, distributed tools, or Phase 5 features. Quality scoring is heuristic and its observed validity/consistency checks are limited to the explicit rules and deterministic checks documented in the report.
