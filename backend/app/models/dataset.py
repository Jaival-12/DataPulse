import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Integer, String, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.db.session import Base

class Dataset(Base):
    __tablename__ = "datasets"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False, index=True)
    storage_key = Column(String(64), nullable=False, unique=True)
    format = Column(String(10), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    row_count = Column(Integer, nullable=False)
    column_count = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    columns = relationship("DatasetColumn", cascade="all, delete-orphan", back_populates="dataset", order_by="DatasetColumn.position")
    profile = relationship("DatasetProfile", cascade="all, delete-orphan", back_populates="dataset", uselist=False)
    pipelines = relationship("PipelineDefinition", cascade="all, delete-orphan", back_populates="source_dataset")
    pipeline_executions = relationship("PipelineExecution", cascade="all, delete-orphan", back_populates="source_dataset")
    processed_datasets = relationship("ProcessedDataset", cascade="all, delete-orphan", back_populates="source_dataset")
    quality_reports = relationship("DataQualityReport", cascade="all, delete-orphan", back_populates="dataset")

class DatasetColumn(Base):
    __tablename__ = "dataset_columns"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(String(36), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    data_type = Column(String(32), nullable=False)
    position = Column(Integer, nullable=False)
    dataset = relationship("Dataset", back_populates="columns")
    __table_args__ = (Index("ix_dataset_column_unique", "dataset_id", "position", unique=True),)
