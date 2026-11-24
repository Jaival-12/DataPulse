# DataPulse

DataPulse is a data ingestion and analytics platform. Phases 1 and 2 provide validated CSV/JSON uploads, durable dataset metadata, source previews, persisted dataset profiling, and a React dashboard. Phase 3A adds synchronous backend pipeline definitions, transformation execution, history, and separate processed outputs. Phase 3B adds the React pipeline builder and execution screens, plus processed output browsing, previews, lineage, and downloads.

## Architecture

- `frontend/`: React + TypeScript + Vite client. Overview, dataset catalog, and dataset profile pages use live API responses.
- `backend/`: FastAPI service with SQLAlchemy models, a repository boundary, ingestion and profiling services, and Alembic migrations.
- Raw files are stored separately from the catalog under generated UUID names. The original display name is retained only as metadata.
- `backend/app/services/transformations.py` validates and applies one transformation at a time. `pipeline_service.py` bounds extraction, records ordered step logs, and atomically writes processed outputs beneath `STORAGE_DIR/processed/`.
- Pipeline definitions and ordered steps, executions, and processed dataset metadata are stored in PostgreSQL/SQLite. Every processed output references both its execution and source dataset; source uploads are never overwritten.
- `DATABASE_URL` configures PostgreSQL (including Neon) or local SQLite. For local development the default is `sqlite:///./datapulse.db`.

## Run locally

### Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
# Edit DATABASE_URL for Neon if desired. Keep the password in the ignored .env file.
alembic upgrade head
uvicorn app.main:app --reload
```

Interactive API docs are at `http://localhost:8000/docs`. Health checks are `/api/health` and `/api/health/db`.

### Frontend

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

Open `http://localhost:5173`. Set `VITE_API_URL` if the backend is hosted elsewhere.

### Docker

Copy `backend/.env.example` to `backend/.env`, configure `DATABASE_URL` and `STORAGE_DIR=/app/storage`, then run `docker compose up --build`. A Neon URL can be used directly; the Compose file does not start a separate database container.

## Environment

Backend variables: `DATABASE_URL`, `STORAGE_DIR`, `MAX_UPLOAD_MB` (default 25), `MAX_PROFILE_MB` (default 25), and comma-separated `CORS_ORIGINS`. Frontend variable: `VITE_API_URL` (default `http://localhost:8000/api`). No credentials are committed.

## API

- `POST /api/datasets` — upload CSV/JSON (`multipart/form-data`, field `file`).
- `GET /api/datasets?search=&limit=20&offset=0` — searchable, paginated catalog.
- `GET /api/datasets/{id}` — dataset metadata without reading preview rows.
- `GET /api/overview` — database-backed dataset and ingested-record totals plus the five most recent uploads.
- `GET /api/datasets/{id}/preview?limit=10` — schema metadata and first rows.
- `POST /api/datasets/{id}/profile` — profile the preserved raw file and save the report.
- `GET /api/datasets/{id}/profile` — retrieve the saved profile.
- `POST /api/datasets/{id}/profile/refresh` — rebuild and update the saved profile from the current raw file.
- `DELETE /api/datasets/{id}` — delete dataset and source file.
- `GET /api/health` and `GET /api/health/db` — application and DB health.

The upload limit and extension/content parsing are enforced server-side. The application does not trust MIME type and never uses the user filename for storage paths. Profiling preserves source values and applies conversions only while calculating a report. Numeric inference distinguishes integer, float, numeric mixed (some present values convert and some do not), string, categorical, boolean, date, datetime, identifier, mixed, and empty columns. Grouped numeric strings such as `1,499` are accepted only when comma grouping is well formed. Numeric reports include valid and invalid counts, conversion percentage, summary statistics, and a histogram. Supported date inputs include `YYYY-MM-DD`, `YYYY/MM/DD`, `DD-MM-YYYY`, and valid ISO datetimes; malformed or impossible date-shaped values are counted as invalid. Date reports include valid, invalid, missing, earliest, and latest values. Identifier-like names are profiled separately with uniqueness, duplicate occurrence count, and samples, without misleading frequency charts. Categorical columns use top-value frequencies; high-cardinality free text is reported as string.

Blanks, nulls and non-finite numeric values are treated as missing. Duplicate rows are full-row duplicates beyond the first occurrence; uniqueness is distinct non-null values divided by non-null records. The profile size limit bounds whole-file in-memory processing; larger files return a controlled 413 response. Source data is never rewritten.

## Phase 2 manual check

1. Start the backend and frontend using the commands above.
2. Upload a CSV or JSON dataset from **Datasets**.
3. Select the dataset name, open **Data profile**, then choose **Generate profile**.
4. Review row/column/missing/duplicate/completeness metrics, search the column table, and select numeric or categorical columns for details.
5. Change the local original source file only if you are testing refresh; choose **Refresh profile** to recalculate and persist the report.
6. Confirm **Data preview** still shows original records, then delete the dataset and verify it disappears from the catalog.

## Tests

```powershell
cd backend
pip install -r requirements-dev.txt
python -m pytest -q
```

```powershell
cd frontend
npm install
npm test
npm run build
```

## Phase 3A ETL

Run the schema migration before using pipeline APIs:

```powershell
cd backend
alembic upgrade head
```

Create a pipeline using an ordered list of validated operations:

```json
{
  "name": "clean orders",
  "description": "Remove duplicate IDs and retain positive quantities",
  "source_dataset_id": "<dataset-id>",
  "output_format": "csv",
  "steps": [
    {"operation": "remove_duplicates", "config": {"subset": ["order_id"]}},
    {"operation": "fill_missing", "config": {"column": "quantity", "strategy": "median"}},
    {"operation": "trim_whitespace", "config": {"columns": ["product", "city"]}},
    {"operation": "filter_rows", "config": {"column": "quantity", "operator": "greater_than", "value": 0}}
  ]
}
```

Create with `POST /api/pipelines`, then execute with `POST /api/pipelines/{id}/execute`. The execution response includes status, input/output row counts, step logs, and processed dataset metadata. Browse history with `GET /api/pipelines/{id}/executions`, `GET /api/executions/{id}`, or `GET /api/executions/{id}/logs`. Preview an output using `GET /api/processed-datasets/{processed-id}/preview`; download it with `/api/processed-datasets/{processed-id}/download`. Pipeline CRUD uses `GET /api/pipelines`, `GET /api/pipelines/{id}`, `PUT /api/pipelines/{id}`, and `DELETE /api/pipelines/{id}`. Processed output listing and metadata use `GET /api/processed-datasets` and `GET /api/processed-datasets/{id}`.

Supported operations are `remove_duplicates` (optional `subset`), `fill_missing` (`drop_rows`, `constant`, `mean`, `median`, or `mode`), `rename_columns`, `remove_columns`, `reorder_columns`, `filter_rows` (equals/not-equals, numeric comparisons, contains/not-contains, null checks), `convert_type` (string/integer/float/boolean/date), `trim_whitespace`, `lowercase`, `uppercase`, `title_case`, and `add_calculated_column`. Calculated columns use structured operands, for example `{"name":"net","left":{"column":"price"},"operator":"subtract","right":{"column":"discount"}}`; operands may also be finite numeric constants. Python expressions are never evaluated.

Execution is synchronous and in memory, bounded by `MAX_PROFILE_MB` for both source and output files. A failed step stops execution and records a failed execution and step log without publishing a processed output. CSV values remain text during extraction to preserve values such as `0012`; apply explicit type conversion before numeric operations where required. There is no background worker, scheduler, retry system, or frontend transformation builder in Phase 3A. Deleting a source dataset or pipeline cascades its execution and processed metadata and removes generated output files.

## Phase 3B frontend

Open **Pipelines** to create, edit, delete, and run pipeline definitions. The builder configures the Phase 3A operations in order, adjusts column choices based on earlier schema changes, validates required values, and submits the existing pipeline API contract. Runs execute synchronously; the UI displays the returned status, row counts, duration, output link, and step logs, with paginated run history.

Open **Processed data** to browse pipeline outputs, inspect source and pipeline lineage, preview up to 100 rows, and download the original processed CSV or JSON file. Source uploads remain unchanged. The UI uses the existing Phase 3A API and database schema; no backend endpoints or migrations were added for Phase 3B.

## Phase 4 Data Quality

Apply the new quality report and issue tables before using quality endpoints:

```powershell
cd backend
alembic upgrade head
```

Run an analysis for an uploaded source or a processed output. Analyses are read-only and create an immutable report with persisted issues:

```http
POST /api/quality/datasets/{dataset_id}/analyze
POST /api/quality/processed-datasets/{processed_dataset_id}/analyze
```

Optional rules use structured, allow-listed JSON (no expressions or user code):

```json
{
  "rules": [
    {"type": "not_null", "column": "customer_id"},
    {"type": "unique", "column": "customer_id"},
    {"type": "non_negative", "column": "quantity"},
    {"type": "range", "column": "discount", "min_value": 0, "max_value": 1},
    {"type": "required_columns", "columns": ["customer_id", "order_date"]}
  ]
}
```

Supported rules are `required_columns`, `not_null`, `unique`, `non_negative`, `greater_than`, and `range`. A rule may reference only a column present in the analyzed data (required-column checks can report absent names). Reports and issue lists are available from `GET /api/quality/reports`, `GET /api/quality/reports/{report_id}`, and `GET /api/quality/reports/{report_id}/issues`; each source also exposes paginated report history at `/api/quality/datasets/{dataset_id}/reports` or `/api/quality/processed-datasets/{processed_dataset_id}/reports`.

The dashboard is available from **Data quality** in the sidebar. Dataset details provide source analysis and history; processed dataset details provide output analysis, history, and a comparison with the latest report from that output's recorded source dataset. Comparisons are based on declared lineage and show only dimensions measured in both reports.

Scores cover completeness, validity, uniqueness, consistency, and rule-based correctness. Each dimension score is 0–100 and reports retain the configured weights and methodology version. The total score is the weighted mean over measured dimensions only; unmeasured dimensions are stored as `null` and excluded from the denominator. If none can be measured, the report is `Not scored`. Rule-based correctness describes only the configured checks and is not evidence of real-world accuracy. Validity currently checks profile-supported numeric/date values and email syntax for email-named columns; consistency uses conservative whitespace, text casing, and date-format indicators. Findings are capped at 500 per report, with at most five example values per finding. The synchronous in-memory analysis uses existing `MAX_PROFILE_MB` and safe storage path checks; chunked processing and background execution are outside this phase.

## Current scope

The current scope covers Phases 1, 2, 3A, 3B, Phase 4 data quality, Phase 5A analytics, the Phase 5B dashboard, and Phase 6A backend orchestration. Phase 6B scheduling UI, streaming, and production deployment architecture are not included. Airflow schedules and retries existing synchronous ETL runs; DataPulse continues to own transformation logic and business execution history. Profiling, ETL, quality, and analytics run in memory for files up to `MAX_PROFILE_MB`; larger-file chunking remains a future extension. Alembic owns application schema changes; Airflow uses its own local metadata database.

## Phase 5A Analytics & Insights Backend

Analytics are computed on demand from the actual original CSV/JSON file or ETL processed output. The analytics service uses the existing safe storage-path resolvers and `MAX_PROFILE_MB` bound. It performs no writes to input files or analytics tables; **no migration is required**. The API is mounted below `/api/analytics`.

### Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/analytics/datasets/{dataset_id}/overview` | Rows, columns by inferred type, missing/duplicate counts, actual file size and generation time |
| GET | `/api/analytics/datasets/{dataset_id}/columns` | Column type, missing, invalid and distinct counts |
| GET | `/api/analytics/datasets/{dataset_id}/columns/{column_name}` | Numeric statistics/histogram, category frequencies, or date range |
| GET | `/api/analytics/datasets/{dataset_id}/correlation` | Pearson matrix and pairwise observation counts |
| POST | `/api/analytics/datasets/{dataset_id}/timeseries` | Daily, weekly, or monthly record counts and optional numeric aggregation |
| POST | `/api/analytics/datasets/{dataset_id}/aggregate` | Bounded categorical or date-period grouping |
| GET | `/api/analytics/datasets/{dataset_id}/insights` | Deterministic observations based on measured values |
| GET / POST | `/api/analytics/processed-datasets/{processed_dataset_id}/...` | The same overview, columns, correlation, timeseries, aggregate, and insights functions for processed output |
| POST | `/api/analytics/compare` | Compare original-to-derived output or two outputs from the same source lineage |

Timeseries request:

```json
{
  "date_column": "order_date",
  "granularity": "monthly",
  "measure_column": "net_total",
  "aggregation": "sum",
  "limit": 500
}
```

Aggregation request:

```json
{
  "group_by": "region",
  "operation": "average",
  "measure_column": "net_total",
  "limit": 100
}
```

Comparison request:

```json
{
  "left": {"type": "original", "id": "<dataset-id>"},
  "right": {"type": "processed", "id": "<processed-dataset-id>"}
}
```

Both references may be processed outputs when they share a source dataset ID. Original-to-processed comparisons must reference the original recorded by the processed output's lineage. Comparisons return row, column, missing-cell, duplicate, numeric summary and top-category changes; common/added/removed columns; and exact-value rename candidates when row-aligned values match. Renames changed alongside row values cannot be proven automatically and remain represented as added and removed columns.

### Calculation and limits

Numeric strings use the existing safe parser, including grouped forms such as `1,499`; invalid and missing values are counted separately and never replaced with zero. Numeric column detail returns valid count, missing/invalid counts, mean, median, minimum, maximum, range, sample standard deviation and variance, quartiles, distinct count and at most 20 histogram bins. Categorical detail returns non-null/missing counts, cardinality, distinct values and at most 10 top values. Date detail and time series count invalid and missing dates separately; impossible dates are excluded. Correlation uses pairwise valid values and returns null where fewer than two observations or a constant column prevents calculation.

Grouping supports count, sum, average, minimum and maximum, with at most 100 returned groups. Grouping requires a categorical/identifier column or an explicit daily/weekly/monthly date period. Time series returns at most 500 chronological periods per request. Correlation is limited to 50 numeric columns per request. Automated insights are deterministic rules (missingness at 20%+, a dominant category at 75%+, dispersion, negative values, strong Pearson correlation, and processed row-count changes); they describe observed data and do not claim causality or statistical significance. When a dataset has more than 50 numeric columns, insights still return non-correlation observations, while the dedicated correlation endpoint reports the limit. No analytics result history or cache is persisted.

### Run locally

Use the existing backend environment and development database/storage settings:

```powershell
cd backend
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
python -m pytest -q
```

The Phase 5A feature does not alter the Alembic head. Tests use isolated temporary SQLite databases and temporary file storage; they do not connect to production Neon.

## Phase 5B Analytics Dashboard

The frontend Analytics workspace is available at `/analytics` from the sidebar. Select an original upload or processed pipeline output to view backend-provided record/column counts, inferred types, missing and duplicate counts, file size, and profile time. Column analysis adapts to numeric, categorical, date, and mixed profiles; charts use returned histograms and frequency values. The workspace also provides date-based trend controls, a Pearson correlation matrix, bounded group aggregation, deterministic backend insights, and original/processed comparisons. Comparison selection is checked against recorded source lineage before submitting.

Time-series and aggregation calculations run after the user submits their selections; summary metrics, column summaries, correlation, and insights load for the selected source. The compare endpoint provides row/column counts plus numeric and categorical changes; missing-cell and duplicate values are rendered as the backend-computed change deltas. The frontend does not insert sample data or recalculate those statistics locally.

## Phase 6A Workflow Orchestration Backend

Airflow is an optional local orchestration service. DataPulse stores pipeline schedules and source lineage, validates each scheduled run, calls the existing ETL service, and persists the authoritative `PipelineExecution`. Airflow owns cron scheduling, retries, DAG/task state, and task logs. A reusable DAG generator reads atomically written schedule JSON files; DAG parsing does not connect to the DataPulse database or API and DAG files never contain the internal token. The internal API uses a constant-time checked Bearer token. The Airflow metadata PostgreSQL database is separate from `DATABASE_URL` and is only reachable on an internal Docker network. Manual pipeline execution remains available when Airflow is stopped.

The local Airflow stack uses the official Apache Airflow 2.11.2 image with `LocalExecutor`, one scheduler, one webserver, and a dedicated PostgreSQL 16 service. It has no worker, Redis, or triggerer services. Parallelism is limited to one task at a time to keep local resource use modest and avoid overlapping ETL runs against shared source data. Airflow's official Docker quick start documents the Compose deployment pattern and supports this pinned release; this Compose configuration is for local development, not production ([Airflow 2.11.2 Docker guide](https://airflow.apache.org/docs/apache-airflow/2.11.2/howto/docker-compose/), [Airflow 2.11.2 Python support](https://airflow.apache.org/docs/apache-airflow/2.11.2/start.html)).

### Configure and start locally

1. Copy `.env.example` to `.env` at the project root. Generate unique values for `DATAPULSE_INTERNAL_TOKEN`, `AIRFLOW_DB_PASSWORD`, `AIRFLOW_FERNET_KEY`, `AIRFLOW_WEBSERVER_SECRET_KEY`, and `AIRFLOW_ADMIN_PASSWORD`; never commit `.env`. Use an alphanumeric `AIRFLOW_DB_PASSWORD` so the local PostgreSQL URL does not need URI escaping. `backend/.env` still supplies the DataPulse application database and storage configuration.
2. Start the existing API service first; this creates the private shared `datapulse-local` network and mounts the DAG schedule directory into FastAPI:

   ```powershell
   docker compose up -d api
   ```

3. Initialize the separate Airflow metadata database and create the configured UI account, then start the Airflow scheduler and webserver:

   ```powershell
   docker compose -f docker-compose.airflow.yml up airflow-init
   docker compose -f docker-compose.airflow.yml up -d airflow-webserver airflow-scheduler
   ```

4. Open `http://localhost:8080` and sign in with values from the ignored root `.env`. The webserver port is bound to loopback; the Airflow metadata database has no host port. Airflow requires Linux containers (Docker Desktop/WSL2 on Windows); its official docs recommend at least 4 GB Docker memory, though this LocalExecutor setup disables unused services and limits concurrency.

Stop Airflow while leaving DataPulse running:

```powershell
docker compose -f docker-compose.airflow.yml down
```

Remove Airflow containers and its metadata/log volumes only when you intend to erase local Airflow history:

```powershell
docker compose -f docker-compose.airflow.yml down --volumes --remove-orphans
```

The `airflow/dags/schedules` folder is shared with FastAPI. Keep it writable by the API container and readable by Airflow. Manifests contain validated schedule metadata only, never credentials. Changes are picked up on Airflow's next DAG-file scan (configured to 10 seconds). If DataPulse runs outside Compose, set `AIRFLOW_SCHEDULES_DIR` to a directory mounted at `/opt/airflow/dags/schedules` in Airflow and set `DATAPULSE_API_URL` to a host-reachable API URL.

### Create and manage a schedule

Create a schedule for an existing pipeline with the DataPulse API:

```http
POST /api/pipelines/{pipeline_id}/schedule
Content-Type: application/json

{"schedule_type":"daily","timezone":"Asia/Kolkata","retries":2,"retry_delay_seconds":60,"timeout_seconds":3600}
```

Supported schedule types are `hourly`, `daily`, `weekly`, and `custom`. Custom schedules use a validated five-field cron expression, for example `{"schedule_type":"custom","cron_expression":"30 8 * * 1-5","timezone":"UTC","retries":3,"retry_delay_seconds":120,"timeout_seconds":1800}`. Timezones must be valid IANA names. Optional `start_date` values must include an offset, such as `2026-12-01T08:00:00+05:30`. Retry count is limited to 0–5, delay to 1–3600 seconds, and task timeout to 30–14400 seconds. The response includes the stable `airflow_dag_id` and, when croniter is installed, the `next_run_at` value.

Retrieve or change a schedule with `GET` or `PUT /api/pipelines/{pipeline_id}/schedule`. Use `POST /api/pipelines/{pipeline_id}/schedule/disable` to pause it, `/enable` to resume it, or `DELETE /api/pipelines/{pipeline_id}/schedule` to remove it. Deleting a pipeline or its source dataset also removes its manifest; queued tasks revalidate schedule, pipeline, and source availability before ETL.

### Retry and execution behavior

Each Airflow DAG has a `validate_pipeline` task followed by `execute_pipeline`. The execution task calls an authenticated internal FastAPI route which invokes the existing `execute_pipeline` service; transformations are not reimplemented in Airflow. An Airflow DAG-run ID is persisted uniquely with the DataPulse execution, so a repeated task request returns that same execution and cannot publish a second processed dataset. A currently running correlated execution returns a retryable service response. Returned ETL failures are permanent and Airflow fails the task without repeating the transformation. Validation and other permanent 4xx failures fail fast; network failures, 5xx, 408, and 429 responses use the configured Airflow retry policy. API request timeouts and Airflow task/DAG timeouts are bounded by schedule configuration.

### Monitoring and troubleshooting

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/orchestration/status` | Internal-token and writable schedule-directory configuration; this is not a live Airflow health probe |
| GET | `/api/orchestration/pipelines` | Scheduled pipeline list, enabled state, and latest mirrored run |
| GET | `/api/orchestration/pipelines/{pipeline_id}/runs` | Paginated run history |
| GET | `/api/orchestration/runs/{run_id}` | Orchestration state and linked DataPulse execution |
| GET | `/api/orchestration/runs/{run_id}/logs` | DataPulse step logs and orchestration error |

Use Airflow's local UI for scheduler/task state and Airflow logs. `PipelineExecution` remains the business record for ETL results; DataPulse mirrors Airflow run state and IDs for API monitoring. If a DAG is missing, verify the schedule is enabled and both containers mount the same schedule directory. If an internal task returns 401/503, compare the root `.env` `DATAPULSE_INTERNAL_TOKEN` used by API and Airflow, then recreate the affected containers. Missing pipelines/sources and disabled schedules are permanent errors; correct or re-enable the source before retrying. The status endpoint reports configuration only; check Airflow's UI/container health for actual scheduler health.

This is a local development integration, not a production deployment. Ordinary backend tests mock Airflow and do not require Docker; actual DAG import and scheduled-run integration require Docker.
