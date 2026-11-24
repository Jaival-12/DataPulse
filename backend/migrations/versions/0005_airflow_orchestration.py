"""Add scheduled pipeline orchestration metadata.

Revision ID: 0005_airflow_orchestration
Revises: 0004_data_quality
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_airflow_orchestration"
down_revision = "0004_data_quality"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("pipeline_executions", sa.Column("airflow_dag_id", sa.String(length=250), nullable=True))
    op.add_column("pipeline_executions", sa.Column("airflow_run_id", sa.String(length=250), nullable=True))
    op.create_index("uq_pipeline_execution_airflow_run", "pipeline_executions", ["airflow_dag_id", "airflow_run_id"], unique=True)

    op.create_table(
        "pipeline_schedules",
        sa.Column("pipeline_id", sa.String(length=36), sa.ForeignKey("pipeline_definitions.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("schedule_type", sa.String(length=16), nullable=False),
        sa.Column("cron_expression", sa.String(length=120), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("retries", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("retry_delay_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="3600"),
        sa.Column("airflow_dag_id", sa.String(length=250), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_scheduled_execution_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("schedule_type IN ('hourly', 'daily', 'weekly', 'custom')", name="ck_pipeline_schedule_type"),
        sa.CheckConstraint("retries BETWEEN 0 AND 5", name="ck_pipeline_schedule_retries"),
    )
    op.create_index("ix_pipeline_schedules_enabled", "pipeline_schedules", ["enabled"])

    op.create_table(
        "orchestration_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("pipeline_id", sa.String(length=36), nullable=False),
        sa.Column("airflow_dag_id", sa.String(length=250), nullable=False),
        sa.Column("airflow_run_id", sa.String(length=250), nullable=False),
        sa.Column("airflow_task_id", sa.String(length=250), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("execution_id", sa.String(length=36), nullable=True),
        sa.Column("try_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('queued', 'running', 'success', 'failed')", name="ck_orchestration_run_status"),
    )
    op.create_index("uq_orchestration_run_identity", "orchestration_runs", ["airflow_dag_id", "airflow_run_id"], unique=True)
    op.create_index("ix_orchestration_runs_pipeline_id", "orchestration_runs", ["pipeline_id"])
    op.create_index("ix_orchestration_runs_airflow_dag_id", "orchestration_runs", ["airflow_dag_id"])
    op.create_index("ix_orchestration_runs_status", "orchestration_runs", ["status"])
    op.create_index("ix_orchestration_runs_execution_id", "orchestration_runs", ["execution_id"])


def downgrade():
    op.drop_index("ix_orchestration_runs_execution_id", table_name="orchestration_runs")
    op.drop_index("ix_orchestration_runs_status", table_name="orchestration_runs")
    op.drop_index("ix_orchestration_runs_airflow_dag_id", table_name="orchestration_runs")
    op.drop_index("ix_orchestration_runs_pipeline_id", table_name="orchestration_runs")
    op.drop_index("uq_orchestration_run_identity", table_name="orchestration_runs")
    op.drop_table("orchestration_runs")
    op.drop_index("ix_pipeline_schedules_enabled", table_name="pipeline_schedules")
    op.drop_table("pipeline_schedules")
    op.drop_index("uq_pipeline_execution_airflow_run", table_name="pipeline_executions")
    op.drop_column("pipeline_executions", "airflow_run_id")
    op.drop_column("pipeline_executions", "airflow_dag_id")
