"""Inyección de dependencias para el módulo search de VeciRed IA."""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dependencies import get_db_session
from app.modules.search.service import SearchService


def get_search_service(
    session: AsyncSession = Depends(get_db_session),
) -> SearchService:
    """Provee una instancia de SearchService con la sesión de base de datos inyectada."""
    return SearchService(session)

