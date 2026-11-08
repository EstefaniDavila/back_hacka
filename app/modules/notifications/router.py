"""Rutas de API v1 para el módulo de notificaciones y alertas a la comunidad."""
import uuid
from typing import List
from fastapi import APIRouter, Depends

from app.core.security import CurrentUser, get_current_user
from app.modules.notifications.dependencies import get_notification_service
from app.modules.notifications.schemas import NotificationResponse, UnreadCountResponse
from app.modules.notifications.service import NotificationService

router = APIRouter(prefix="/notifications", tags=["Notificaciones y Alertas"])


@router.get(
    "",
    response_model=List[NotificationResponse],
    summary="Listar mis notificaciones y alertas recibidas",
)
async def list_my_notifications(
    current_user: CurrentUser = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    """Consulta todas las alertas y notificaciones enviadas al vecino autenticado."""
    return await service.list_my_notifications(current_user.id)


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    summary="Obtener contador de notificaciones no leídas",
)
async def get_unread_count(
    current_user: CurrentUser = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    """Retorna la cantidad de avisos o alertas urgentes pendientes de lectura."""
    return await service.get_unread_count(current_user.id)


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    summary="Marcar notificación como leída",
)
async def mark_notification_as_read(
    notification_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    """Marca la notificación indicada como leída."""
    return await service.mark_as_read(notification_id, current_user.id)
