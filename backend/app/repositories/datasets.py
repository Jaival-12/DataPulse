from sqlalchemy.orm import Session
from app.models.dataset import Dataset

def get_dataset(db: Session, dataset_id: str):
    return db.query(Dataset).filter(Dataset.id == dataset_id).first()
