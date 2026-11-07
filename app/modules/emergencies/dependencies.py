"""Inyección de dependencias para el módulo de emergencias de VeciRed IA."""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dependencies import get_db_session
from app.modules.emergencies.service import EmergencyService


async def get_emergency_service(
    session: AsyncSession = Depends(get_db_session),
) -> EmergencyService:
    """Provee la instancia del servicio de emergencias con sesión inyectada."""
    return EmergencyService(session)
