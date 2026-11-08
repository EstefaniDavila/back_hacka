"""Lógica de negocio y servicios para notificaciones y alertas vecinales."""
import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundException
from app.modules.notifications.repository import NotificationRepository
from app.modules.notifications.schemas import NotificationResponse, UnreadCountResponse


class NotificationService:
    """Capa de servicios para la entrega de alertas y lectura de notificaciones."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = NotificationRepository(session)

    async def list_my_notifications(self, user_id: uuid.UUID) -> List[NotificationResponse]:
        """Retorna las notificaciones para el usuario autenticado."""
        notifs = await self.repository.list_notifications(user_id=user_id)
        result = []
        for n in notifs:
            time_str = n.created_at.strftime("%H:%M") if n.created_at else "Ahora"
            result.append(
                NotificationResponse(
                    id=n.id,
                    user_id=n.user_id,
                    title=n.title,
                    body=n.body,
                    notification_type=n.notification_type or "emergency_alert",
                    is_read=n.is_read or False,
                    created_at=n.created_at,
                    time=time_str,
                )
            )
        return result

    async def get_unread_count(self, user_id: uuid.UUID) -> UnreadCountResponse:
        """Obtiene la cantidad de notificaciones sin leer."""
        count = await self.repository.count_unread(user_id)
        return UnreadCountResponse(unread_count=count)

    async def mark_as_read(self, notification_id: uuid.UUID, user_id: uuid.UUID) -> NotificationResponse:
        """Marca una alerta o aviso como leído."""
        notif = await self.repository.mark_as_read(notification_id, user_id)
        if not notif:
            raise EntityNotFoundException("Notificación", notification_id)
        await self.session.commit()
        time_str = notif.created_at.strftime("%H:%M") if notif.created_at else "Ahora"
        return NotificationResponse(
            id=notif.id,
            user_id=notif.user_id,
            title=notif.title,
            body=notif.body,
            notification_type=notif.notification_type or "emergency_alert",
            is_read=True,
            created_at=notif.created_at,
            time=time_str,
        )
