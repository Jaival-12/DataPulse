"""Add pipeline definitions, executions, transformation steps, and outputs.

Revision ID: 0003_etl_pipelines
Revises: 0002_dataset_profiles
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_etl_pipelines"
down_revision = "0002_dataset_profiles"
branch_labels = None
depends_on = None

json_value = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade():
    op.create_table(
        "pipeline_definitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_dataset_id", sa.String(36), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("configuration", json_value, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_pipeline_definitions_name", "pipeline_definitions", ["name"])
    op.create_index("ix_pipeline_definitions_source_dataset_id", "pipeline_definitions", ["source_dataset_id"])

    op.create_table(
        "transformation_steps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("pipeline_id", sa.String(36), sa.ForeignKey("pipeline_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("configuration", json_value, nullable=False),
        sa.Column("execution_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_transformation_steps_pipeline_id", "transformation_steps", ["pipeline_id"])
    op.create_index("ix_transformation_step_order", "transformation_steps", ["pipeline_id", "execution_order"], unique=True)

    op.create_table(
        "pipeline_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("pipeline_id", sa.String(36), sa.ForeignKey("pipeline_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_dataset_id", sa.String(36), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("total_input_rows", sa.Integer(), nullable=True),
        sa.Column("total_output_rows", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("execution_summary", json_value, nullable=False),
        sa.CheckConstraint("status IN ('pending', 'running', 'success', 'failed')", name="ck_pipeline_execution_status"),
    )
    op.create_index("ix_pipeline_executions_pipeline_id", "pipeline_executions", ["pipeline_id"])
    op.create_index("ix_pipeline_executions_source_dataset_id", "pipeline_executions", ["source_dataset_id"])
    op.create_index("ix_pipeline_executions_status", "pipeline_executions", ["status"])

    op.create_table(
        "processed_datasets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("execution_id", sa.String(36), sa.ForeignKey("pipeline_executions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("source_dataset_id", sa.String(36), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_type", sa.String(10), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("column_count", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(255), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_processed_datasets_execution_id", "processed_datasets", ["execution_id"], unique=True)
    op.create_index("ix_processed_datasets_source_dataset_id", "processed_datasets", ["source_dataset_id"])
    op.create_index("ix_processed_datasets_created_at", "processed_datasets", ["created_at"])


def downgrade():
    op.drop_index("ix_processed_datasets_created_at", table_name="processed_datasets")
    op.drop_index("ix_processed_datasets_source_dataset_id", table_name="processed_datasets")
    op.drop_index("ix_processed_datasets_execution_id", table_name="processed_datasets")
    op.drop_table("processed_datasets")
    op.drop_index("ix_pipeline_executions_status", table_name="pipeline_executions")
    op.drop_index("ix_pipeline_executions_source_dataset_id", table_name="pipeline_executions")
    op.drop_index("ix_pipeline_executions_pipeline_id", table_name="pipeline_executions")
    op.drop_table("pipeline_executions")
    op.drop_index("ix_transformation_step_order", table_name="transformation_steps")
    op.drop_index("ix_transformation_steps_pipeline_id", table_name="transformation_steps")
    op.drop_table("transformation_steps")
    op.drop_index("ix_pipeline_definitions_source_dataset_id", table_name="pipeline_definitions")
    op.drop_index("ix_pipeline_definitions_name", table_name="pipeline_definitions")
    op.drop_table("pipeline_definitions")
