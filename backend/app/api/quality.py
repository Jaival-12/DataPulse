import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.dataset import Dataset
from app.models.data_quality import DataQualityIssue, DataQualityReport
from app.models.pipeline import ProcessedDataset
from app.schemas.quality import (
    AnalyzeQualityIn, DataQualityIssuePage, DataQualityReportOut, DataQualityReportPage,
)
from app.services.pipeline_service import ProcessedFileError
from app.services.profiling_service import (
    InvalidProfileSource, ProfileSourceMissing, ProfileTooLarge, UnsupportedProfileFormat,
)
from app.services.quality_service import (
    QualityRuleColumnMissing, analyze_original_dataset, analyze_processed_dataset,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/quality", tags=["data quality"])


def _quality_error(db: Session, exc: Exception):
    db.rollback()
    if isinstance(exc, ProfileSourceMissing):
        raise HTTPException(404, "Dataset file is unavailable.") from exc
    if isinstance(exc, ProfileTooLarge):
        raise HTTPException(413, f"Dataset exceeds the {settings.max_profile_mb} MB quality analysis limit.") from exc
    if isinstance(exc, UnsupportedProfileFormat):
        raise HTTPException(415, "Only CSV and JSON datasets can be analyzed.") from exc
    if isinstance(exc, (InvalidProfileSource, ProcessedFileError)):
        raise HTTPException(400, "Dataset file could not be safely parsed.") from exc
    if isinstance(exc, QualityRuleColumnMissing):
        raise HTTPException(422, str(exc)) from exc
    logger.exception("Quality report could not be generated")
    raise HTTPException(500, "Quality report could not be saved.") from exc


@router.post("/datasets/{dataset_id}/analyze", response_model=DataQualityReportOut, status_code=201)
def analyze_dataset(dataset_id: str, body: AnalyzeQualityIn, db: Session = Depends(get_db)):
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise HTTPException(404, "Dataset not found.")
    rules = [rule.model_dump(exclude_none=True) for rule in body.rules]
    try:
        return analyze_original_dataset(db, dataset, rules)
    except (ProfileSourceMissing, ProfileTooLarge, UnsupportedProfileFormat, InvalidProfileSource, ProcessedFileError, QualityRuleColumnMissing) as exc:
        _quality_error(db, exc)
    except Exception as exc:
        _quality_error(db, exc)


@router.post("/processed-datasets/{processed_dataset_id}/analyze", response_model=DataQualityReportOut, status_code=201)
def analyze_processed(processed_dataset_id: str, body: AnalyzeQualityIn, db: Session = Depends(get_db)):
    dataset = db.get(ProcessedDataset, processed_dataset_id)
    if dataset is None:
        raise HTTPException(404, "Processed dataset not found.")
    rules = [rule.model_dump(exclude_none=True) for rule in body.rules]
    try:
        return analyze_processed_dataset(db, dataset, rules)
    except (ProfileSourceMissing, ProfileTooLarge, UnsupportedProfileFormat, InvalidProfileSource, ProcessedFileError, QualityRuleColumnMissing) as exc:
        _quality_error(db, exc)
    except Exception as exc:
        _quality_error(db, exc)


def _report_page(query, limit: int, offset: int):
    total = query.count()
    items = query.order_by(DataQualityReport.created_at.desc(), DataQualityReport.id.desc()).offset(offset).limit(limit).all()
    return DataQualityReportPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/reports", response_model=DataQualityReportPage)
def list_reports(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    return _report_page(db.query(DataQualityReport), limit, offset)


@router.get("/reports/{report_id}", response_model=DataQualityReportOut)
def get_report(report_id: str, db: Session = Depends(get_db)):
    report = db.get(DataQualityReport, report_id)
    if report is None:
        raise HTTPException(404, "Quality report not found.")
    return report


@router.get("/reports/{report_id}/issues", response_model=DataQualityIssuePage)
def list_report_issues(
    report_id: str,
    severity: str | None = Query(None, pattern="^(critical|high|medium|low)$"),
    dimension: str | None = Query(None, pattern="^(completeness|validity|uniqueness|consistency|rule_based_correctness)$"),
    search: str | None = Query(None, max_length=120),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    if db.get(DataQualityReport, report_id) is None:
        raise HTTPException(404, "Quality report not found.")
    query = db.query(DataQualityIssue).filter(DataQualityIssue.report_id == report_id)
    if severity:
        query = query.filter(DataQualityIssue.severity == severity)
    if dimension:
        query = query.filter(DataQualityIssue.dimension == dimension)
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(or_(DataQualityIssue.issue_type.ilike(term), DataQualityIssue.column_name.ilike(term), DataQualityIssue.description.ilike(term), DataQualityIssue.recommendation.ilike(term)))
    total = query.count()
    items = query.order_by(DataQualityIssue.severity, DataQualityIssue.dimension, DataQualityIssue.id).offset(offset).limit(limit).all()
    return DataQualityIssuePage(items=items, total=total, limit=limit, offset=offset)


@router.get("/datasets/{dataset_id}/reports", response_model=DataQualityReportPage)
def list_dataset_reports(dataset_id: str, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    if db.get(Dataset, dataset_id) is None:
        raise HTTPException(404, "Dataset not found.")
    return _report_page(db.query(DataQualityReport).filter(DataQualityReport.dataset_id == dataset_id), limit, offset)


@router.get("/processed-datasets/{processed_dataset_id}/reports", response_model=DataQualityReportPage)
def list_processed_reports(processed_dataset_id: str, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    if db.get(ProcessedDataset, processed_dataset_id) is None:
        raise HTTPException(404, "Processed dataset not found.")
    return _report_page(db.query(DataQualityReport).filter(DataQualityReport.processed_dataset_id == processed_dataset_id), limit, offset)
