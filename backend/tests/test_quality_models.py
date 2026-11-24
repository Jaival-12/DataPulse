import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models.data_quality import DataQualityReport


def test_quality_report_requires_exactly_one_source():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.add(DataQualityReport(
                id="report-none", overall_score=None, quality_label="Not scored",
                dimension_scores={}, scoring_weights={}, methodology={}, rules=[],
                total_rows=0, total_columns=0, total_issues=0, status="not_scored",
            ))
            with pytest.raises(IntegrityError):
                session.commit()
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_quality_report_rejects_both_source_types():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.add(DataQualityReport(
                id="report-both", dataset_id="source-1", processed_dataset_id="processed-1",
                overall_score=None, quality_label="Not scored", dimension_scores={},
                scoring_weights={}, methodology={}, rules=[], total_rows=0,
                total_columns=0, total_issues=0, status="not_scored",
            ))
            with pytest.raises(IntegrityError):
                session.commit()
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
