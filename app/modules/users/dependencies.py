"""Inyección de dependencias para el módulo users."""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.dependencies import get_db_session
from app.modules.users.service import UserService


def get_user_service(
    session: AsyncSession = Depends(get_db_session),
) -> UserService:
    """Provee una instancia de UserService con la sesión de base de datos inyectada."""
    return UserService(session)

