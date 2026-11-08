from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.dependencies import get_db_session
from app.modules.geo.repository import DepartmentRepository, CommunityRepository, MapRepository
from app.modules.geo.service import GeoService


def get_geo_service(
    session: AsyncSession = Depends(get_db_session),
) -> GeoService:
    """Provee una instancia de GeoService con sus repositorios inyectados."""
    dept_repo = DepartmentRepository(session)
    comm_repo = CommunityRepository(session)
    map_repo = MapRepository(session)
    return GeoService(dept_repo=dept_repo, comm_repo=comm_repo, map_repo=map_repo)
