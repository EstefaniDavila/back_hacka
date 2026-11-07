from typing import Any, Generic, List, Optional, Sequence, Type, TypeVar
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.base import Base

ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class BaseRepository(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """Repositorio base asíncrono con operaciones CRUD estándar en SQLAlchemy 2.0."""

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    async def get_by_id(self, id: Any) -> Optional[ModelType]:
        """Obtiene una entidad por su clave primaria."""
        stmt = select(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_multi(
        self,
        skip: int = 0,
        limit: int = 100,
        order_by: Optional[Any] = None,
    ) -> Sequence[ModelType]:
        """Obtiene un listado paginado de entidades."""
        stmt = select(self.model).offset(skip).limit(limit)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self) -> int:
        """Retorna el número total de registros de la entidad."""
        stmt = select(func.count()).select_from(self.model)
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def create(self, obj_in: CreateSchemaType | dict[str, Any]) -> ModelType:
        """Crea y persiste una nueva entidad."""
        if isinstance(obj_in, BaseModel):
            obj_data = obj_in.model_dump(exclude_unset=True)
        else:
            obj_data = dict(obj_in)

        db_obj = self.model(**obj_data)
        self.session.add(db_obj)
        await self.session.flush()
        await self.session.refresh(db_obj)
        return db_obj

    async def update(
        self,
        db_obj: ModelType,
        obj_in: UpdateSchemaType | dict[str, Any],
    ) -> ModelType:
        """Actualiza los campos proporcionados de una entidad existente."""
        if isinstance(obj_in, BaseModel):
            update_data = obj_in.model_dump(exclude_unset=True)
        else:
            update_data = dict(obj_in)

        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        self.session.add(db_obj)
        await self.session.flush()
        await self.session.refresh(db_obj)
        return db_obj

    async def delete(self, id: Any) -> Optional[ModelType]:
        """Elimina una entidad por su ID y la retorna si existía."""
        db_obj = await self.get_by_id(id)
        if db_obj:
            await self.session.delete(db_obj)
            await self.session.flush()
        return db_obj
