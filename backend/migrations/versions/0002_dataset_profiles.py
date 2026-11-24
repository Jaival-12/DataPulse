"""Add one persisted profile per dataset.

Revision ID: 0002_dataset_profiles
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_dataset_profiles"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

profile_json = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

def upgrade():
    op.create_table(
        "dataset_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("profile_data", profile_json, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dataset_profiles_dataset_id", "dataset_profiles", ["dataset_id"], unique=True)

def downgrade():
    op.drop_index("ix_dataset_profiles_dataset_id", table_name="dataset_profiles")
    op.drop_table("dataset_profiles")
