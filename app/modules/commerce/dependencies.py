"""Inyección de dependencias para el módulo commerce."""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.dependencies import get_db_session
from app.modules.commerce.service import CommerceService


def get_commerce_service(
    session: AsyncSession = Depends(get_db_session),
) -> CommerceService:
    """Provee una instancia de CommerceService con la sesión de base de datos inyectada."""
    return CommerceService(session)

