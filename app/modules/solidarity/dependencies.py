"""Inyección de dependencias para el módulo de solidaridad de VeciRed IA."""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dependencies import get_db_session
from app.modules.solidarity.service import SolidarityService


async def get_solidarity_service(
    session: AsyncSession = Depends(get_db_session),
) -> SolidarityService:
    """Provee la instancia del servicio de solidaridad con sesión inyectada."""
    return SolidarityService(session)
