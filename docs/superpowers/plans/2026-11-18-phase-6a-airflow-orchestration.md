# Phase 6A Airflow Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Schedule existing DataPulse ETL pipelines through an isolated local Airflow stack without duplicating ETL logic.

**Architecture:** FastAPI owns schedules and writes validated DAG config files to a shared directory; a reusable Airflow DAG generator reads those small files and calls secured internal DataPulse routes. Nullable DAG/run IDs on executions provide retry idempotency, while a separate schedule/run metadata layer supports orchestration monitoring. Airflow uses a separate PostgreSQL metadata database and remains opt-in.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic, croniter, Apache Airflow 2.11.2 official image, Docker Compose, PostgreSQL 16, Python 3.12.

**Spec:** `docs/superpowers/specs/2026-11-18-phase-6a-airflow-orchestration-design.md`

## Global Constraints

- Preserve manual `/api/pipelines/{pipeline_id}/execute` behavior and reuse `execute_pipeline`.
- Never point Airflow metadata at DataPulse `DATABASE_URL`.
- Never commit the internal token or Airflow UI credentials.
- Airflow must be opt-in; no Kafka, frontend scheduling, Phase 7, or ETL rewrite.
- Use bounded retries, timeouts, and existing source/output limits.

## Review Focus

- Duplicate HTTP deliveries and Airflow retries must not create multiple DataPulse execution/output records.
- Disabled schedules, deleted pipelines, missing source rows, and unavailable source files must fail before ETL.
- Invalid cron/timezones and excessive retry/timeout values must be rejected before persistence.
- Missing/incorrect internal token must never execute a pipeline or update orchestration state.
- Removing/updating the JSON schedule definition must not require editing DAG source or querying the database during DAG parsing.

## Files and responsibilities

- `backend/app/models/pipeline.py`, `backend/app/models/__init__.py`: schedule and orchestration run records; nullable Airflow execution identity.
- `backend/migrations/versions/0005_airflow_orchestration.py`: reversible schema additions.
- `backend/app/schemas/orchestration.py`: request/response contracts and schedule validation.
- `backend/app/services/orchestration_service.py`: cron/timezone validation, stable DAG ID, atomic schedule manifests, idempotency lookups, run status changes.
- `backend/app/api/orchestration.py`, `backend/app/api/pipelines.py`, `backend/app/main.py`: public schedule/monitoring APIs and secured internal callbacks/validation/execution routes.
- `backend/app/services/pipeline_service.py`: optional DAG/run correlation key in the existing execution path; no ETL changes.
- `airflow/dags/datapulse_scheduled_pipelines.py`: generic file-driven DAG generator and bounded internal HTTP calls.
- `docker-compose.airflow.yml`, `airflow/.env.example`, `.gitignore`, root `docker-compose.yml`: isolated optional Airflow stack, private networking, mount wiring and ignores.
- `backend/tests/test_orchestration_service.py`, `backend/tests/test_orchestration_api.py`, `backend/tests/test_airflow_dag.py`, `backend/tests/test_orchestration_migration.py`: unit/API/security/idempotency/DAG/migration coverage.
- `backend/requirements.txt`, `README.md`: pinned cron validation dependency and local setup/troubleshooting docs.

## Tasks

### Task 1: Schedule validation and DAG identity

- [x] Add unit tests first for hourly/daily/weekly/custom cron normalization, invalid cron, invalid timezone, aware start date, retry/timeout limits, and stable UUID-to-DAG-ID mapping.
- [x] Run tests and confirm they fail on missing orchestration contracts.
- [x] Add request/response schemas and pure validation helpers; pin `croniter` in backend requirements.
- [x] Run focused tests.

### Task 2: Persistence and migration

- [x] Test schedule metadata persistence, one schedule per pipeline, unique `(airflow_dag_id, airflow_run_id)` execution identity, and orchestration run fields.
- [x] Add `PipelineSchedule`, `OrchestrationRun`, nullable execution correlation columns, and reversible Alembic migration `0005`.
- [x] Run migration upgrade/downgrade against temporary SQLite and verify existing records remain.

### Task 3: Schedule-file service and public APIs

- [x] Test atomic manifest creation/replacement/removal, including disabled schedules and filesystem failure handling.
- [x] Add service and public schedule routes: POST/GET/PUT/DELETE, enable, disable.
- [x] Test 404 and duplicate create/update behavior, deleted pipeline behavior, and response models.

### Task 4: Secure internal execution and run synchronization

- [x] Test bearer-token rejection, source/pipeline/schedule validation, permanent versus retryable failures, execution correlation, and duplicate request behavior.
- [x] Add internal validation, idempotent execute, and callback routes; call the existing `execute_pipeline` service with Airflow IDs.
- [x] Test that failed ETL remains failed and creates no processed output; test manual execute remains unchanged.

### Task 5: Reusable Airflow DAG and isolated Compose stack

- [x] Add Python-level DAG helper tests for manifest discovery, safe DAG IDs, task retry settings, timeout, and task request payloads using mocked Airflow/request dependencies.
- [x] Implement a single generic DAG generator that reads schedule files only and fails fast on permanent 4xx/ETL errors while allowing network/5xx retries.
- [x] Add opt-in Compose services with Airflow 2.11.2 `LocalExecutor`, independent Postgres 16 metadata storage, health checks, persistent volumes, loopback UI binding, and modest concurrency.
- [x] Wire shared network and schedules mount without removing the existing Compose stack.

### Task 6: Orchestration monitoring APIs

- [x] Test service status, scheduled pipeline listing, run listing/detail/log retrieval, and secret non-disclosure.
- [x] Add read-only orchestration APIs over persisted schedule/run mirrors and DataPulse execution history.

### Task 7: Documentation and full verification

- [x] Document environment setup, separate metadata database, startup/shutdown/cleanup, schedule usage, retries, monitoring, and troubleshooting.
- [x] Run complete backend tests and frontend tests/build.
- [x] Run Alembic upgrade/downgrade and Compose config validation.
- [x] Run Airflow DAG import/integration if Docker is available; otherwise report that limitation explicitly.
