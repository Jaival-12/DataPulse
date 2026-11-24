# DataPulse Phase 3A ETL Engine Design

## Intent

Add a synchronous, modular backend ETL flow that operates on an existing uploaded dataset, applies an ordered and validated transformation sequence, and publishes the result as a separate processed dataset. The original upload remains unchanged and all existing dataset, preview, and profiling API behavior remains intact.

## Goals and boundaries

- Persist pipeline definitions, ordered steps, execution history, and processed dataset metadata.
- Support CSV and JSON input/output and the required transformations: duplicate removal, missing-value handling, column rename/remove/reorder, row filters, type conversion, text standardization, and safe calculated columns.
- Provide pipeline CRUD, execution/history/logs, and processed dataset list/detail/preview/download APIs.
- Enforce source and output size limits, generated storage names, path validation, failure cleanup, and persisted step logs.
- Keep execution synchronous and service boundaries ready for later worker execution.
- Do not change the frontend, add scheduling/streaming/Airflow/authentication/quality scoring, or use `create_all` in migrations.

## Existing conventions

The application uses FastAPI routers under `/api`, SQLAlchemy 2.x declarative models registered through `Base`, Pydantic v2 schemas, Alembic revisions under `backend/migrations/versions`, `get_db` dependency injection, and generated UUID storage keys under `settings.storage_dir`. Tests use isolated in-memory SQLite and `tmp_path` storage. JSON columns use `JSON().with_variant(JSONB(), "postgresql")`.

## Approaches

1. **Keep ETL services and API schemas modular (selected):** add pipeline/execution/processed models and schemas, a transformation registry, an orchestration service, and a dedicated API router. This follows current boundaries, makes individual transformations independently testable, and keeps synchronous orchestration replaceable later.
2. **Put ETL logic into the dataset router/service:** fewer files, but mixes source catalog behavior with pipeline lifecycle and transformation semantics, making validation and failure handling harder to isolate.
3. **Introduce an external workflow engine now:** adds deployment and dependency complexity, is outside this phase's synchronous constraint, and is explicitly excluded by the request.

## Data model and API decisions

- `PipelineDefinition` references a source `Dataset` and owns ordered `TransformationStep` rows. The step's operation/configuration are validated through a discriminated Pydantic schema before persistence.
- `PipelineExecution` snapshots execution status, timings, row counts, error, and JSON execution summary/log entries. Status values are `pending`, `running`, `success`, and `failed`.
- `ProcessedDataset` references the successful execution and source dataset, and owns a generated key and output metadata. Files are written beneath a `processed` subdirectory and never overwrite source uploads.
- Deleting a pipeline cascades to steps and executions; deleting an execution cascades to processed metadata. Deleting a source dataset cascades to its pipelines/executions/processed metadata. File cleanup is handled by services/API operations because database cascades cannot remove files.
- Pipeline creation/update accepts an ordered `steps` array. `GET /api/pipelines/{id}` returns the definition with steps. Existing route prefixes and response style remain consistent.
- Execution uses the existing profiling input size limit (`max_profile_mb`) unless a dedicated compatible setting is needed; output is capped at the same limit. CSV is read as object values so IDs/text are preserved. JSON follows the existing object/list-of-objects convention.
- Each execution log entry contains step id/index, operation, status, duration, row counts, and a safe message. Exceptions stop the sequence and prevent publication.
- Calculated columns use structured `{left, operator, right}` operands, where operands are either existing column references or JSON scalar constants. Only `+`, `-`, `*`, `/` are accepted; no Python expression evaluation is used.

## Validation and error handling

Invalid pipeline configurations return 422 before persistence. Missing pipeline/source records return 404. Unsupported formats return 415, invalid sources return 400, and size limit violations return 413. Step errors are captured in execution history while API errors do not expose filesystem paths or stack traces. Output writes use a temporary file in the processed directory followed by atomic replace after all transformations and metadata validation succeed; failures remove temporary and final outputs and mark the execution failed.

## Review focus

- A failed middle step must leave a failed execution, structured failure log, no processed record, and no published output file.
- JSON scalar, null, and mixed values must not be coerced into misleading comparisons or arithmetic results.
- Rename collisions, missing columns, invalid type conversions, and division by zero must fail with step context.
- Input and output path construction must use generated keys and resolved-root checks.
- DB failure during publication must clean output artifacts and roll back incomplete metadata.

## Implementation calls left to the engineer

Use portable SQLAlchemy JSON types with PostgreSQL JSONB variants, exact eager-loading only where response serialization needs it, and standard Pandas operations guarded by explicit schema/parameter validation. Keep table and response names aligned to the request. Add one reversible Alembic revision and no new runtime dependency.
