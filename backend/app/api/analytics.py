"""HTTP boundary for read-only dataset analytics."""
import logging
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.dataset import Dataset
from app.models.pipeline import ProcessedDataset
from app.schemas.analytics import (
    AggregateIn, AggregateOut, AnalyticsColumnOut, AnalyticsColumnsOut, AnalyticsOverviewOut,
    CompareIn, CompareOut, CorrelationOut, InsightsOut, TimeSeriesIn, TimeSeriesOut,
)
from app.services.analytics_insights import generate_insights
from app.utils.analytics_helpers import generated_at
from app.services.analytics_service import (
    AnalyticsColumnError, AnalyticsLineageError, AnalyticsRequestError,
    aggregate_frame, analyze_column, analyze_columns, analyze_correlation,
    analyze_overview, analyze_timeseries, compare_references, load_original_analytics,
    load_processed_analytics,
)
from app.services.pipeline_service import PipelineInputError, ProcessedFileError
from app.services.profiling_service import (
    InvalidProfileSource, ProfileSourceMissing, ProfileTooLarge, UnsupportedProfileFormat,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analytics", tags=["analytics"])


def _safe(call: Callable):
    try:
        return call()
    except HTTPException:
        raise
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ProfileSourceMissing as exc:
        raise HTTPException(404, "Dataset file is unavailable.") from exc
    except ProfileTooLarge as exc:
        from app.core.config import settings
        raise HTTPException(413, f"Dataset exceeds the {settings.max_profile_mb} MB analytics limit.") from exc
    except UnsupportedProfileFormat as exc:
        raise HTTPException(415, "Only CSV and JSON datasets can be analyzed.") from exc
    except (InvalidProfileSource, ProcessedFileError, PipelineInputError) as exc:
        raise HTTPException(400, "Dataset file could not be safely parsed.") from exc
    except (AnalyticsColumnError, AnalyticsRequestError, AnalyticsLineageError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        logger.exception("Analytics request failed")
        raise HTTPException(500, "Analytics could not be calculated.") from exc


def _load(kind: str, source_id: str, db: Session):
    if kind == "original":
        record = db.get(Dataset, source_id)
        if record is None:
            raise HTTPException(404, "Dataset not found.")
        frame, size = load_original_analytics(record)
    else:
        record = db.get(ProcessedDataset, source_id)
        if record is None:
            raise HTTPException(404, "Processed dataset not found.")
        frame, size = load_processed_analytics(record)
    return frame, size, record


def _overview(kind: str, source_id: str, db: Session):
    frame, size, _ = _load(kind, source_id, db)
    return {"source_id": source_id, "source_type": kind, **analyze_overview(frame, size)}


def _columns(kind: str, source_id: str, db: Session):
    frame, _, _ = _load(kind, source_id, db)
    return {"source_id": source_id, "source_type": kind, "columns": analyze_columns(frame), "generated_at": generated_at()}


def _column(kind: str, source_id: str, column_name: str, db: Session):
    frame, _, _ = _load(kind, source_id, db)
    return {"source_id": source_id, "source_type": kind, **analyze_column(frame, column_name), "generated_at": generated_at()}


def _correlation(kind: str, source_id: str, db: Session):
    frame, _, _ = _load(kind, source_id, db)
    return {"source_id": source_id, "source_type": kind, **analyze_correlation(frame), "generated_at": generated_at()}


def _timeseries(kind: str, source_id: str, body: TimeSeriesIn, db: Session):
    frame, _, _ = _load(kind, source_id, db)
    return {"source_id": source_id, "source_type": kind,
            **analyze_timeseries(frame, body.date_column, body.granularity, body.measure_column, body.aggregation, body.limit),
            "generated_at": generated_at()}


def _aggregate(kind: str, source_id: str, body: AggregateIn, db: Session):
    frame, _, _ = _load(kind, source_id, db)
    return {"source_id": source_id, "source_type": kind,
            **aggregate_frame(frame, body.group_by, body.operation, body.measure_column, body.limit, body.date_granularity),
            "generated_at": generated_at()}


def _insights(kind: str, source_id: str, db: Session):
    frame, _, record = _load(kind, source_id, db)
    original_count = None
    if kind == "processed":
        source = db.get(Dataset, record.source_dataset_id)
        if source is not None:
            original_frame, _ = load_original_analytics(source)
            original_count = len(original_frame)
    return {"source_id": source_id, "source_type": kind,
            "insights": generate_insights(frame, original_count), "generated_at": generated_at()}


@router.get("/datasets/{dataset_id}/overview", response_model=AnalyticsOverviewOut)
def original_overview(dataset_id: str, db: Session = Depends(get_db)):
    return _safe(lambda: _overview("original", dataset_id, db))


@router.get("/datasets/{dataset_id}/columns", response_model=AnalyticsColumnsOut)
def original_columns(dataset_id: str, db: Session = Depends(get_db)):
    return _safe(lambda: _columns("original", dataset_id, db))


@router.get("/datasets/{dataset_id}/columns/{column_name}", response_model=AnalyticsColumnOut)
def original_column(dataset_id: str, column_name: str, db: Session = Depends(get_db)):
    return _safe(lambda: _column("original", dataset_id, column_name, db))


@router.get("/datasets/{dataset_id}/correlation", response_model=CorrelationOut)
def original_correlation(dataset_id: str, db: Session = Depends(get_db)):
    return _safe(lambda: _correlation("original", dataset_id, db))


@router.post("/datasets/{dataset_id}/timeseries", response_model=TimeSeriesOut)
def original_timeseries(dataset_id: str, body: TimeSeriesIn, db: Session = Depends(get_db)):
    return _safe(lambda: _timeseries("original", dataset_id, body, db))


@router.post("/datasets/{dataset_id}/aggregate", response_model=AggregateOut)
def original_aggregate(dataset_id: str, body: AggregateIn, db: Session = Depends(get_db)):
    return _safe(lambda: _aggregate("original", dataset_id, body, db))


@router.get("/datasets/{dataset_id}/insights", response_model=InsightsOut)
def original_insights(dataset_id: str, db: Session = Depends(get_db)):
    return _safe(lambda: _insights("original", dataset_id, db))


@router.get("/processed-datasets/{processed_dataset_id}/overview", response_model=AnalyticsOverviewOut)
def processed_overview(processed_dataset_id: str, db: Session = Depends(get_db)):
    return _safe(lambda: _overview("processed", processed_dataset_id, db))


@router.get("/processed-datasets/{processed_dataset_id}/columns", response_model=AnalyticsColumnsOut)
def processed_columns(processed_dataset_id: str, db: Session = Depends(get_db)):
    return _safe(lambda: _columns("processed", processed_dataset_id, db))


@router.get("/processed-datasets/{processed_dataset_id}/columns/{column_name}", response_model=AnalyticsColumnOut)
def processed_column(processed_dataset_id: str, column_name: str, db: Session = Depends(get_db)):
    return _safe(lambda: _column("processed", processed_dataset_id, column_name, db))


@router.get("/processed-datasets/{processed_dataset_id}/correlation", response_model=CorrelationOut)
def processed_correlation(processed_dataset_id: str, db: Session = Depends(get_db)):
    return _safe(lambda: _correlation("processed", processed_dataset_id, db))


@router.post("/processed-datasets/{processed_dataset_id}/timeseries", response_model=TimeSeriesOut)
def processed_timeseries(processed_dataset_id: str, body: TimeSeriesIn, db: Session = Depends(get_db)):
    return _safe(lambda: _timeseries("processed", processed_dataset_id, body, db))


@router.post("/processed-datasets/{processed_dataset_id}/aggregate", response_model=AggregateOut)
def processed_aggregate(processed_dataset_id: str, body: AggregateIn, db: Session = Depends(get_db)):
    return _safe(lambda: _aggregate("processed", processed_dataset_id, body, db))


@router.get("/processed-datasets/{processed_dataset_id}/insights", response_model=InsightsOut)
def processed_insights(processed_dataset_id: str, db: Session = Depends(get_db)):
    return _safe(lambda: _insights("processed", processed_dataset_id, db))


@router.post("/compare", response_model=CompareOut)
def compare_datasets(body: CompareIn, db: Session = Depends(get_db)):
    return _safe(lambda: compare_references(db, body.left, body.right))
