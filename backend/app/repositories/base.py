from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import BaseModel

ModelType = TypeVar("ModelType", bound=BaseModel)


class BaseRepository(Generic[ModelType]):
    def __init__(self, model: type[ModelType], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def get_by_id(self, id: UUID) -> ModelType | None:
        result = await self.session.execute(
            select(self.model).where(
                self.model.id == id, self.model.is_deleted == False
            )
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 50,
        filters: dict[str, Any] | None = None,
    ) -> tuple[list[ModelType], int]:
        query = select(self.model).where(self.model.is_deleted == False)
        if filters:
            for field, value in filters.items():
                if value is not None and hasattr(self.model, field):
                    query = query.where(getattr(self.model, field) == value)

        count_query = select(func.count()).select_from(query.subquery())
        total = await self.session.scalar(count_query)

        query = query.offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all()), total or 0

    async def create(self, obj_in: dict[str, Any]) -> ModelType:
        db_obj = self.model(**obj_in)
        self.session.add(db_obj)
        await self.session.flush()
        await self.session.refresh(db_obj)
        return db_obj

    async def update(self, db_obj: ModelType, update_data: dict[str, Any]) -> ModelType:
        for field, value in update_data.items():
            if value is not None and hasattr(db_obj, field):
                setattr(db_obj, field, value)
        self.session.add(db_obj)
        await self.session.flush()
        await self.session.refresh(db_obj)
        return db_obj

    async def soft_delete(self, db_obj: ModelType) -> ModelType:
        db_obj.soft_delete()
        self.session.add(db_obj)
        await self.session.flush()
        return db_obj
