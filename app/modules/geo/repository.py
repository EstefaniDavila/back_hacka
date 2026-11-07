from typing import Optional, Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.geo.models import Department, Community
from app.modules.geo.schemas import DepartmentCreate, DepartmentUpdate, CommunityCreate, CommunityUpdate
from app.shared.repository import BaseRepository


class DepartmentRepository(BaseRepository[Department, DepartmentCreate, DepartmentUpdate]):
    """Repositorio para operaciones sobre departamentos geográficos."""

    def __init__(self, session: AsyncSession):
        super().__init__(Department, session)

    async def get_by_ubigeo(self, ubigeo: str) -> Optional[Department]:
        """Busca un departamento por su código UBIGEO."""
        stmt = select(self.model).where(self.model.ubigeo == ubigeo)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Department]:
        """Busca un departamento por coincidencia exacta de nombre."""
        stmt = select(self.model).where(self.model.name.ilike(name))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class CommunityRepository(BaseRepository[Community, CommunityCreate, CommunityUpdate]):
    """Repositorio para operaciones sobre comunidades vecinales."""

    def __init__(self, session: AsyncSession):
        super().__init__(Community, session)

    async def get_by_district(self, district_id: int) -> Sequence[Community]:
        """Retorna las comunidades pertenecientes a un distrito específico."""
        stmt = select(self.model).where(self.model.district_id == district_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_active(self, skip: int = 0, limit: int = 50) -> Sequence[Community]:
        """Retorna comunidades con estado activo."""
        stmt = (
            select(self.model)
            .where(self.model.status == "active")
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
