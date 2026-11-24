from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.dataset import Dataset

router = APIRouter(prefix="/overview", tags=["overview"])

@router.get("")
def overview(db: Session = Depends(get_db)):
    dataset_count, record_count = db.query(func.count(Dataset.id), func.coalesce(func.sum(Dataset.row_count), 0)).one()
    recent = db.query(Dataset).order_by(Dataset.created_at.desc()).limit(5).all()
    return {"dataset_count": dataset_count, "record_count": record_count, "recent_datasets": recent}
