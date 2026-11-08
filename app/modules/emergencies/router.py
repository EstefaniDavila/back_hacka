"""Rutas de API v1 para el módulo de emergencias vecinales de VeciRed IA."""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, status

from app.core.security import CurrentUser, get_current_user
from app.modules.emergencies.dependencies import get_emergency_service
from app.modules.emergencies.schemas import (
    EmergencyContributionCreate,
    EmergencyContributionResponse,
    EmergencyCreate,
    EmergencyDetailResponse,
    EmergencyListItemResponse,
    EmergencyNeedCreate,
    EmergencyNeedResponse,
    EmergencyStatusUpdate,
    VolunteerRegister,
)
from app.modules.emergencies.service import EmergencyService
from app.shared.pagination import PaginatedResponse

router = APIRouter(prefix="/emergencies", tags=["Emergencias Barriales"])


# -------------------------------------------------------------
# EMERGENCIAS: LISTADO Y CONSULTA
# -------------------------------------------------------------
@router.get(
    "",
    response_model=PaginatedResponse[EmergencyListItemResponse],
    summary="Listar emergencias barriales",
)
async def list_emergencies(
    community_id: Optional[uuid.UUID] = Query(None, description="Filtrar por comunidad"),
    status: Optional[str] = Query(None, description="Filtrar por estado (reportada, en_atencion, atendida, cerrada)"),
    severity: Optional[str] = Query(None, description="Filtrar por severidad (low, medium, high, critical)"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    service: EmergencyService = Depends(get_emergency_service),
):
    """Retorna las emergencias reportadas en el vecindario."""
    return await service.list_emergencies(
        community_id=community_id,
        status=status,
        severity=severity,
        page=page,
        limit=limit,
    )


@router.get(
    "/active",
    response_model=Optional[EmergencyListItemResponse],
    summary="Consultar emergencia activa prioritaria (Banner de Alerta)",
)
async def get_active_emergency(
    community_id: Optional[uuid.UUID] = Query(None, description="Filtrar por comunidad"),
    service: EmergencyService = Depends(get_emergency_service),
):
    """
    Retorna la emergencia activa más urgente (en_atencion / reportada) para desplegar
    el banner rojo superior en la aplicación móvil de VeciRed.
    """
    return await service.get_active_emergency(community_id=community_id)


@router.get(
    "/{emergency_id}",
    response_model=EmergencyDetailResponse,
    summary="Consultar detalle de una emergencia con necesidades",
)
async def get_emergency_detail(
    emergency_id: uuid.UUID,
    service: EmergencyService = Depends(get_emergency_service),
):
    """Obtiene la ficha técnica, necesidades requeridas y aportes recibidos para la emergencia."""
    return await service.get_emergency_detail(emergency_id)


# -------------------------------------------------------------
# REPORTE Y ADMINISTRACIÓN DE EMERGENCIAS
# -------------------------------------------------------------
@router.post(
    "",
    response_model=EmergencyDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Reportar una nueva emergencia en el barrio",
)
async def create_emergency(
    data: EmergencyCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: EmergencyService = Depends(get_emergency_service),
):
    """Permite a un vecino o líder vecinal activar un reporte de emergencia."""
    return await service.create_emergency(
        user_id=current_user.id,
        data=data,
    )


@router.patch(
    "/{emergency_id}/status",
    response_model=EmergencyDetailResponse,
    summary="Actualizar estado de atención de la emergencia",
)
async def update_emergency_status(
    emergency_id: uuid.UUID,
    status_update: EmergencyStatusUpdate,
    service: EmergencyService = Depends(get_emergency_service),
):
    """Actualiza el estado de la emergencia (ej: pasar de reportada a en_atencion o atendida)."""
    return await service.update_status(
        emergency_id=emergency_id,
        status_update=status_update,
    )


# -------------------------------------------------------------
# NECESIDADES DE RECURSOS Y CONTRIBUCIONES
# -------------------------------------------------------------
@router.post(
    "/{emergency_id}/needs",
    response_model=EmergencyNeedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar necesidad de recurso a la emergencia",
)
async def add_emergency_need(
    emergency_id: uuid.UUID,
    data: EmergencyNeedCreate,
    service: EmergencyService = Depends(get_emergency_service),
):
    """Agrega un recurso necesario (agua, alimentos, frazadas, sacos de arena)."""
    return await service.add_need(
        emergency_id=emergency_id,
        data=data,
    )


@router.post(
    "/needs/{need_id}/contribute",
    response_model=EmergencyContributionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Contribuir o donar a una necesidad de emergencia",
)
async def contribute_to_need(
    need_id: uuid.UUID,
    data: EmergencyContributionCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: EmergencyService = Depends(get_emergency_service),
):
    """Permite a un vecino solidario comprometer donaciones de un recurso requerido."""
    return await service.contribute(
        need_id=need_id,
        user_id=current_user.id,
        data=data,
    )


@router.post(
    "/{emergency_id}/volunteer",
    summary="Registrarse como voluntario en camino para la emergencia",
)
async def register_as_volunteer(
    emergency_id: uuid.UUID,
    data: VolunteerRegister,
    current_user: CurrentUser = Depends(get_current_user),
    service: EmergencyService = Depends(get_emergency_service),
):
    """Permite a los vecinos confirmar que van en camino a brindar auxilio."""
    return await service.register_volunteer(
        emergency_id=emergency_id,
        user_id=current_user.id,
        data=data,
    )


@router.post(
    "/{emergency_id}/broadcast",
    summary="Disparar transmisión de alerta y notificaciones a los vecinos",
)
async def broadcast_emergency_alert(
    emergency_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: EmergencyService = Depends(get_emergency_service),
):
    """Envía notificaciones de alerta inmediata a todos los vecinos registrados en la comunidad."""
    return await service.broadcast_alert(emergency_id, current_user.id)
