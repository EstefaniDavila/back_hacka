"""Repositorio asíncrono para el módulo de notificaciones y alertas."""
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.emergencies.models import AlertDelivery, EmergencyAlert
from app.modules.notifications.models import Notification
from app.modules.users.models import Profile


class NotificationRepository:
    """Acceso a datos para alertas y notificaciones a vecinos."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_notifications(
        self,
        user_id: uuid.UUID,
        limit: int = 30,
    ) -> List[Notification]:
        """Obtiene las notificaciones recibidas por el vecino."""
        stmt = (
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(desc(Notification.created_at))
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def count_unread(self, user_id: uuid.UUID) -> int:
        """Cuenta las notificaciones no leídas."""
        stmt = (
            select(func.count(Notification.id))
            .where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
        )
        res = await self.session.execute(stmt)
        return res.scalar() or 0

    async def mark_as_read(self, notification_id: uuid.UUID, user_id: uuid.UUID) -> Optional[Notification]:
        """Marca una notificación como leída."""
        stmt = select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
        res = await self.session.execute(stmt)
        notif = res.scalar_one_or_none()
        if notif:
            notif.is_read = True
            self.session.add(notif)
            await self.session.flush()
            await self.session.refresh(notif)
        return notif

    async def broadcast_alert_to_community(
        self,
        alert_id: uuid.UUID,
        title: str,
        message: str,
        sender_id: uuid.UUID,
    ) -> int:
        """Crea registros de entrega y notificaciones para todos los vecinos registrados."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Obtener todos los perfiles de vecinos excepto el emisor
        stmt = select(Profile.id).where(Profile.id != sender_id)
        res = await self.session.execute(stmt)
        user_ids = res.scalars().all()

        notifications_to_add = []
        deliveries_to_add = []

        for uid in user_ids:
            # 1. Notificación en bandeja
            notif = Notification(
                id=uuid.uuid4(),
                user_id=uid,
                title=f"🚨 ALERTA COMUNITARIA: {title}",
                body=message,
                notification_type="emergency_alert",
                is_read=False,
                created_at=now,
            )
            notifications_to_add.append(notif)

            # 2. Registro de entrega de alerta
            delivery = AlertDelivery(
                id=uuid.uuid4(),
                alert_id=alert_id,
                user_id=uid,
                delivery_status="sent",
                sent_at=now,
            )
            deliveries_to_add.append(delivery)

        if notifications_to_add:
            self.session.add_all(notifications_to_add)
        if deliveries_to_add:
            self.session.add_all(deliveries_to_add)

        await self.session.flush()
        return len(notifications_to_add)
