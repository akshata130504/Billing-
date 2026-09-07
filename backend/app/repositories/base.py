from typing import Generic, TypeVar, Type, Optional, List, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, func

ModelType = TypeVar("ModelType")


class BaseRepository(Generic[ModelType]):
    """Generic repository providing baseline CRUD database operations."""

    def __init__(self, model: Type[ModelType]):
        self.model = model

    def get_by_id(self, db: Session, id: Any) -> Optional[ModelType]:
        return db.get(self.model, id)

    def list(self, db: Session, skip: int = 0, limit: int = 20) -> List[ModelType]:
        query = select(self.model).offset(skip).limit(limit)
        return list(db.scalars(query).all())

    def count(self, db: Session) -> int:
        query = select(func.count()).select_from(self.model)
        return db.scalar(query) or 0

    def create(self, db: Session, obj_in: ModelType) -> ModelType:
        db.add(obj_in)
        db.commit()
        db.refresh(obj_in)
        return obj_in

    def delete(self, db: Session, db_obj: ModelType) -> None:
        db.delete(db_obj)
        db.commit()
