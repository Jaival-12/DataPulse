import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.db.session import Base

json_value = JSON().with_variant(JSONB(), "postgresql")


class DataQualityReport(Base):
    __tablename__ = "data_quality_reports"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    dataset_id = Column(String(36), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=True, index=True)
    processed_dataset_id = Column(String(36), ForeignKey("processed_datasets.id", ondelete="CASCADE"), nullable=True, index=True)
    overall_score = Column(Float, nullable=True)
    quality_label = Column(String(32), nullable=False)
    dimension_scores = Column(json_value, nullable=False)
    scoring_weights = Column(json_value, nullable=False)
    methodology = Column(json_value, nullable=False)
    rules = Column(json_value, nullable=False, default=list)
    total_rows = Column(Integer, nullable=False)
    total_columns = Column(Integer, nullable=False)
    total_issues = Column(Integer, nullable=False)
    status = Column(String(24), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    dataset = relationship("Dataset", back_populates="quality_reports")
    processed_dataset = relationship("ProcessedDataset", back_populates="quality_reports")
    issues = relationship("DataQualityIssue", back_populates="report", cascade="all, delete-orphan", order_by="DataQualityIssue.id")

    __table_args__ = (
        CheckConstraint(
            "(dataset_id IS NOT NULL AND processed_dataset_id IS NULL) OR "
            "(dataset_id IS NULL AND processed_dataset_id IS NOT NULL)",
            name="ck_quality_report_exactly_one_source",
        ),
        CheckConstraint("overall_score IS NULL OR (overall_score >= 0 AND overall_score <= 100)", name="ck_quality_report_score_range"),
        CheckConstraint("status IN ('complete', 'not_scored')", name="ck_quality_report_status"),
        Index("ix_quality_report_dataset_created", "dataset_id", "created_at"),
        Index("ix_quality_report_processed_created", "processed_dataset_id", "created_at"),
    )


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issues"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    report_id = Column(String(36), ForeignKey("data_quality_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    dimension = Column(String(40), nullable=False)
    issue_type = Column(String(64), nullable=False)
    severity = Column(String(16), nullable=False)
    column_name = Column(String(255), nullable=True)
    affected_rows = Column(Integer, nullable=False)
    affected_percentage = Column(Float, nullable=False)
    description = Column(Text, nullable=False)
    sample_values = Column(json_value, nullable=False, default=list)
    recommendation = Column(Text, nullable=False)

    report = relationship("DataQualityReport", back_populates="issues")
    __table_args__ = (
        CheckConstraint("dimension IN ('completeness', 'validity', 'uniqueness', 'consistency', 'rule_based_correctness')", name="ck_quality_issue_dimension"),
        CheckConstraint("severity IN ('critical', 'high', 'medium', 'low')", name="ck_quality_issue_severity"),
        CheckConstraint("affected_rows >= 0", name="ck_quality_issue_affected_rows"),
        CheckConstraint("affected_percentage >= 0 AND affected_percentage <= 100", name="ck_quality_issue_affected_percentage"),
        Index("ix_quality_issue_report_severity", "report_id", "severity"),
        Index("ix_quality_issue_report_dimension", "report_id", "dimension"),
    )
