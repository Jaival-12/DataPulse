import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.utils.cron_validation import next_cron_run

json_value = JSON().with_variant(JSONB(), "postgresql")


class PipelineDefinition(Base):
    __tablename__ = "pipeline_definitions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    source_dataset_id = Column(String(36), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    configuration = Column(json_value, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    source_dataset = relationship("Dataset", back_populates="pipelines")
    steps = relationship("TransformationStep", back_populates="pipeline", cascade="all, delete-orphan", order_by="TransformationStep.execution_order")
    executions = relationship("PipelineExecution", back_populates="pipeline", cascade="all, delete-orphan", order_by="PipelineExecution.started_at.desc()")
    schedule = relationship("PipelineSchedule", back_populates="pipeline", cascade="all, delete-orphan", uselist=False)


class TransformationStep(Base):
    __tablename__ = "transformation_steps"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_id = Column(String(36), ForeignKey("pipeline_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    operation = Column(String(64), nullable=False)
    configuration = Column(json_value, nullable=False)
    execution_order = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    pipeline = relationship("PipelineDefinition", back_populates="steps")
    __table_args__ = (Index("ix_transformation_step_order", "pipeline_id", "execution_order", unique=True),)


class PipelineExecution(Base):
    __tablename__ = "pipeline_executions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_id = Column(String(36), ForeignKey("pipeline_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    source_dataset_id = Column(String(36), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(16), nullable=False, default="pending", index=True)
    started_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration = Column(Float, nullable=True)
    total_input_rows = Column(Integer, nullable=True)
    total_output_rows = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    execution_summary = Column(json_value, nullable=False, default=dict)
    airflow_dag_id = Column(String(250), nullable=True)
    airflow_run_id = Column(String(250), nullable=True)

    pipeline = relationship("PipelineDefinition", back_populates="executions")
    source_dataset = relationship("Dataset", back_populates="pipeline_executions")
    processed_dataset = relationship("ProcessedDataset", back_populates="execution", cascade="all, delete-orphan", uselist=False)
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'running', 'success', 'failed')", name="ck_pipeline_execution_status"),
        Index("uq_pipeline_execution_airflow_run", "airflow_dag_id", "airflow_run_id", unique=True),
    )


class PipelineSchedule(Base):
    __tablename__ = "pipeline_schedules"

    pipeline_id = Column(String(36), ForeignKey("pipeline_definitions.id", ondelete="CASCADE"), primary_key=True)
    schedule_type = Column(String(16), nullable=False)
    cron_expression = Column(String(120), nullable=False)
    timezone = Column(String(64), nullable=False, default="UTC")
    start_date = Column(DateTime(timezone=True), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    retries = Column(Integer, nullable=False, default=2)
    retry_delay_seconds = Column(Integer, nullable=False, default=60)
    timeout_seconds = Column(Integer, nullable=False, default=3600)
    airflow_dag_id = Column(String(250), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_scheduled_execution_at = Column(DateTime(timezone=True), nullable=True)

    pipeline = relationship("PipelineDefinition", back_populates="schedule")

    @property
    def next_run_at(self):
        if not self.enabled:
            return None
        return next_cron_run(self.cron_expression, self.timezone, self.start_date)

    __table_args__ = (
        CheckConstraint("schedule_type IN ('hourly', 'daily', 'weekly', 'custom')", name="ck_pipeline_schedule_type"),
        CheckConstraint("retries BETWEEN 0 AND 5", name="ck_pipeline_schedule_retries"),
    )


class OrchestrationRun(Base):
    """DataPulse mirror of Airflow state; Airflow remains the orchestration authority."""
    __tablename__ = "orchestration_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pipeline_id = Column(String(36), nullable=False, index=True)
    airflow_dag_id = Column(String(250), nullable=False, index=True)
    airflow_run_id = Column(String(250), nullable=False)
    airflow_task_id = Column(String(250), nullable=True)
    status = Column(String(16), nullable=False, default="queued", index=True)
    execution_id = Column(String(36), nullable=True, index=True)
    try_number = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("uq_orchestration_run_identity", "airflow_dag_id", "airflow_run_id", unique=True),
        CheckConstraint("status IN ('queued', 'running', 'success', 'failed')", name="ck_orchestration_run_status"),
    )


class ProcessedDataset(Base):
    __tablename__ = "processed_datasets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    execution_id = Column(String(36), ForeignKey("pipeline_executions.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    source_dataset_id = Column(String(36), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(10), nullable=False)
    file_size = Column(Integer, nullable=False)
    row_count = Column(Integer, nullable=False)
    column_count = Column(Integer, nullable=False)
    storage_path = Column(String(255), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    execution = relationship("PipelineExecution", back_populates="processed_dataset")
    source_dataset = relationship("Dataset", back_populates="processed_datasets")
    quality_reports = relationship("DataQualityReport", cascade="all, delete-orphan", back_populates="processed_dataset")
