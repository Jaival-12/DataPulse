"""Add persisted data quality reports and issues.

Revision ID: 0004_data_quality
Revises: 0003_etl_pipelines
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_data_quality"
down_revision = "0003_etl_pipelines"
branch_labels = None
depends_on = None

json_value = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade():
    op.create_table(
        "data_quality_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("dataset_id", sa.String(36), sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=True),
        sa.Column("processed_dataset_id", sa.String(36), sa.ForeignKey("processed_datasets.id", ondelete="CASCADE"), nullable=True),
        sa.Column("overall_score", sa.Float(), nullable=True),
        sa.Column("quality_label", sa.String(32), nullable=False),
        sa.Column("dimension_scores", json_value, nullable=False),
        sa.Column("scoring_weights", json_value, nullable=False),
        sa.Column("methodology", json_value, nullable=False),
        sa.Column("rules", json_value, nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("total_columns", sa.Integer(), nullable=False),
        sa.Column("total_issues", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(dataset_id IS NOT NULL AND processed_dataset_id IS NULL) OR "
            "(dataset_id IS NULL AND processed_dataset_id IS NOT NULL)",
            name="ck_quality_report_exactly_one_source",
        ),
        sa.CheckConstraint("overall_score IS NULL OR (overall_score >= 0 AND overall_score <= 100)", name="ck_quality_report_score_range"),
        sa.CheckConstraint("status IN ('complete', 'not_scored')", name="ck_quality_report_status"),
    )
    op.create_index("ix_data_quality_reports_dataset_id", "data_quality_reports", ["dataset_id"])
    op.create_index("ix_data_quality_reports_processed_dataset_id", "data_quality_reports", ["processed_dataset_id"])
    op.create_index("ix_data_quality_reports_created_at", "data_quality_reports", ["created_at"])
    op.create_index("ix_quality_report_dataset_created", "data_quality_reports", ["dataset_id", "created_at"])
    op.create_index("ix_quality_report_processed_created", "data_quality_reports", ["processed_dataset_id", "created_at"])

    op.create_table(
        "data_quality_issues",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("report_id", sa.String(36), sa.ForeignKey("data_quality_reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dimension", sa.String(40), nullable=False),
        sa.Column("issue_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("column_name", sa.String(255), nullable=True),
        sa.Column("affected_rows", sa.Integer(), nullable=False),
        sa.Column("affected_percentage", sa.Float(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("sample_values", json_value, nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.CheckConstraint("dimension IN ('completeness', 'validity', 'uniqueness', 'consistency', 'rule_based_correctness')", name="ck_quality_issue_dimension"),
        sa.CheckConstraint("severity IN ('critical', 'high', 'medium', 'low')", name="ck_quality_issue_severity"),
        sa.CheckConstraint("affected_rows >= 0", name="ck_quality_issue_affected_rows"),
        sa.CheckConstraint("affected_percentage >= 0 AND affected_percentage <= 100", name="ck_quality_issue_affected_percentage"),
    )
    op.create_index("ix_data_quality_issues_report_id", "data_quality_issues", ["report_id"])
    op.create_index("ix_quality_issue_report_severity", "data_quality_issues", ["report_id", "severity"])
    op.create_index("ix_quality_issue_report_dimension", "data_quality_issues", ["report_id", "dimension"])


def downgrade():
    op.drop_index("ix_quality_issue_report_dimension", table_name="data_quality_issues")
    op.drop_index("ix_quality_issue_report_severity", table_name="data_quality_issues")
    op.drop_index("ix_data_quality_issues_report_id", table_name="data_quality_issues")
    op.drop_table("data_quality_issues")
    op.drop_index("ix_quality_report_processed_created", table_name="data_quality_reports")
    op.drop_index("ix_quality_report_dataset_created", table_name="data_quality_reports")
    op.drop_index("ix_data_quality_reports_created_at", table_name="data_quality_reports")
    op.drop_index("ix_data_quality_reports_processed_dataset_id", table_name="data_quality_reports")
    op.drop_index("ix_data_quality_reports_dataset_id", table_name="data_quality_reports")
    op.drop_table("data_quality_reports")
