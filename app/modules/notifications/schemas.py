"""Esquemas Pydantic v2 para el módulo de notificaciones comunitarias."""
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class NotificationResponse(BaseModel):
    """Ficha de notificación recibida por el vecino."""
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    body: Optional[str] = None
    notification_type: Optional[str] = "emergency_alert"
    is_read: bool = False
    created_at: Optional[datetime] = None
    time: Optional[str] = "Ahora"
    model_config = ConfigDict(from_attributes=True)


class UnreadCountResponse(BaseModel):
    """Contador de alertas pendientes."""
    unread_count: int
