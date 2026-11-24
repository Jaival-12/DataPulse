"""Safe file loading and persistence for quality analysis."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.dataset import Dataset
from app.models.data_quality import DataQualityIssue, DataQualityReport
from app.models.pipeline import ProcessedDataset
from app.services.pipeline_service import PipelineInputError, ProcessedFileError, safe_processed_path, source_path
from app.services.profiling_service import (
    InvalidProfileSource, ProfileSourceMissing, ProfileTooLarge,
    UnsupportedProfileFormat, load_dataset_frame,
)
from app.services.quality_engine import analyze_quality


class QualityRuleColumnMissing(ValueError):
    pass


def _load_original(dataset: Dataset, root: Path, max_bytes: int) -> pd.DataFrame:
    try:
        path = source_path(dataset, root)
        return load_dataset_frame(path, dataset.format, max_bytes, root)
    except PipelineInputError as exc:
        if "unavailable" in str(exc):
            raise ProfileSourceMissing from exc
        raise InvalidProfileSource from exc


def _load_processed(dataset: ProcessedDataset, root: Path, max_bytes: int) -> pd.DataFrame:
    path = safe_processed_path(root, dataset.storage_path)
    # load_dataset_frame enforces that the file is inside the provided root; the safe
    # processed path resolver has already established the stronger storage/processed boundary.
    return load_dataset_frame(path, dataset.file_type, max_bytes, path.parent)


def _analyze(db: Session, frame: pd.DataFrame, rules: list[dict[str, Any]], *, dataset_id: str | None,
             processed_dataset_id: str | None) -> DataQualityReport:
    for rule in rules:
        if rule["type"] == "required_columns":
            continue
        if rule.get("column") not in frame.columns:
            raise QualityRuleColumnMissing(f"Rule column '{rule.get('column')}' is not present in this dataset.")
    result = analyze_quality(frame, rules)
    report = DataQualityReport(
        id=str(uuid.uuid4()), dataset_id=dataset_id, processed_dataset_id=processed_dataset_id,
        overall_score=result["overall_score"], quality_label=result["quality_label"],
        dimension_scores=result["dimension_scores"], scoring_weights=result["scoring_weights"],
        methodology=result["methodology"], rules=result["rules"], total_rows=result["total_rows"],
        total_columns=result["total_columns"], total_issues=result["total_issues"], status=result["status"],
        issues=[DataQualityIssue(**issue) for issue in result["issues"]],
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def analyze_original_dataset(db: Session, dataset: Dataset, rules: list[dict[str, Any]]) -> DataQualityReport:
    root = settings.storage_dir
    frame = _load_original(dataset, root, settings.max_profile_mb * 1024 * 1024)
    return _analyze(db, frame, rules, dataset_id=dataset.id, processed_dataset_id=None)


def analyze_processed_dataset(db: Session, dataset: ProcessedDataset, rules: list[dict[str, Any]]) -> DataQualityReport:
    root = settings.storage_dir
    frame = _load_processed(dataset, root, settings.max_profile_mb * 1024 * 1024)
    return _analyze(db, frame, rules, dataset_id=None, processed_dataset_id=dataset.id)
