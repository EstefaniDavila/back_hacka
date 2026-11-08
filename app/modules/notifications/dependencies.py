"""Inyección de dependencias para el módulo de notificaciones."""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dependencies import get_db_session
from app.modules.notifications.service import NotificationService


async def get_notification_service(
    session: AsyncSession = Depends(get_db_session),
) -> NotificationService:
    """Provee la instancia del servicio de notificaciones con sesión inyectada."""
    return NotificationService(session)
