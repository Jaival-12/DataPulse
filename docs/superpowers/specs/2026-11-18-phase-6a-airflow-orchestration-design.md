# Phase 6A Airflow Orchestration Design

## Goal and boundaries

Let existing DataPulse pipelines run on schedules through Apache Airflow. Airflow owns cron scheduling, task retries, DAG/task state, and monitoring; DataPulse remains authoritative for pipeline definitions, source/output files, transformations, and ETL execution history. Existing manual execution stays on its current route and remains synchronous. No frontend scheduling work, streaming, or Phase 7 deployment work is included.

## Architecture

- Use the official `apache/airflow:2.11.2` image with the `LocalExecutor`, one scheduler, one webserver, and a dedicated PostgreSQL 16 metadata service in an opt-in `docker-compose.airflow.yml`. Keep the stack on a private Docker network, publish the web UI on loopback only, persist metadata/logs, and mount a shared DAG directory into the existing API container. The Airflow metadata database must never use `DATABASE_URL`.
- Keep a single reusable DAG generator. FastAPI writes one validated JSON schedule document per enabled pipeline into the shared DAG schedules directory using atomic replacement. The DAG parser reads only these small local files; it never queries DataPulse or the application database. Removing/pausing a schedule file removes the DAG on the next parse cycle; API guards also reject queued work for disabled/deleted pipelines.
- Add a schedule metadata table (one schedule per pipeline) and orchestration run mirror table. Add nullable Airflow DAG/run identifiers to `PipelineExecution` with a unique composite constraint, giving Airflow task retries an idempotency key without changing manual execution behavior. DataPulse's execution row stays authoritative for ETL outcome; Airflow is authoritative for orchestration state, mirrored by secured callbacks.
- Airflow tasks call authenticated, private FastAPI internal routes. A validation task verifies pipeline, enabled schedule, source metadata, and source file. An execution task invokes the existing `execute_pipeline` service with DAG/run identifiers; no transformation code is copied into DAGs. Transport failures are retryable, permanent validation/ETL failures fail fast, and an already correlated run is returned instead of publishing a second output.
- Expose public schedule CRUD/enable/disable and read-only orchestration status, scheduled pipeline, run, and log APIs. Never proxy Airflow credentials or unrestricted admin actions through FastAPI.
- Validate cron with pinned `croniter`, timezones with `zoneinfo`, and request limits with Pydantic. Schedule definitions include hourly/daily/weekly/custom cron, timezone, optional aware start time, retry count/delay, and execution timeout.

## Failure and security model

`DATAPULSE_INTERNAL_TOKEN` authenticates only internal task/monitor callback routes with constant-time comparison. It is read from the environment and is not stored in DAG JSON. Airflow requests use bounded timeouts. New execution IDs are uniquely tied to one DAG run. Disabled/deleted pipelines and missing source files are permanent errors. API/network/5xx failures are retried by Airflow. Task callbacks record the final orchestration state without replacing ETL execution status.

## Test strategy

Unit-test cron/timezone/retry validation, stable DAG-ID mapping, atomic schedule-file lifecycle, retry/persistence correlation, and callback state transitions. API tests cover schedule create/update/delete/toggle, internal authentication, idempotency, manual execution compatibility, and orchestration monitoring. Migration tests cover upgrade/downgrade. Test DAG module syntax/import behavior without requiring Airflow in normal backend tests; validate Compose config and Airflow DAG import using the optional local container stack when Docker is available.

## Local limitations

Airflow is an opt-in local orchestration stack, not a production deployment. DAG visibility/removal follows Airflow's configured file parsing interval. Airflow can be disabled when unused; manually triggered DataPulse execution remains available. The application API and Airflow share the local schedules directory, so schedule changes require the API process to have write access to that mount.
