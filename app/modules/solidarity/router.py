"""Rutas de API v1 para el módulo de solidaridad y muro vecinal de VeciRed IA."""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status

from app.core.security import CurrentUser, get_current_user
from app.modules.solidarity.dependencies import get_solidarity_service
from app.modules.solidarity.schemas import (
    SolidarityPostCreate,
    SolidarityPostDetail,
    SolidarityPostListItem,
    SolidarityPostStatusUpdate,
    SolidarityPostUpdate,
    SolidarityResponseCreate,
    SolidarityResponseItem,
    SolidarityResponseStatusUpdate,
)
from app.modules.solidarity.service import SolidarityService
from app.shared.pagination import PaginatedResponse

router = APIRouter(prefix="/solidarity", tags=["Ayuda Solidaria y Muro"])


# -------------------------------------------------------------
# MURO SOLIDARIO: EXPLORACIÓN Y BÚSQUEDA
# -------------------------------------------------------------
@router.get(
    "/posts",
    response_model=PaginatedResponse[SolidarityPostListItem],
    summary="Explorar publicaciones del muro solidario",
)
async def list_solidarity_posts(
    q: Optional[str] = Query(None, description="Búsqueda por título, descripción o vecino"),
    category: Optional[str] = Query(None, description="Filtrar por categoría (ej: Herramientas, Donaciones, Apoyo temporal)"),
    post_type: Optional[str] = Query(None, pattern="^(request|offer|donation|exchange)$", description="Tipo de post"),
    community_id: Optional[uuid.UUID] = Query(None, description="Filtrar por ID de comunidad"),
    status: Optional[str] = Query("active", description="Estado de la publicación"),
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(20, ge=1, le=100, description="Cantidad por página"),
    service: SolidarityService = Depends(get_solidarity_service),
):
    """Retorna las publicaciones activas del muro comunitario con filtros y paginación."""
    return await service.list_posts(
        query=q,
        category=category,
        post_type=post_type,
        community_id=community_id,
        status=status,
        page=page,
        limit=limit,
    )


@router.get(
    "/posts/my",
    response_model=PaginatedResponse[SolidarityPostListItem],
    summary="Listar mis publicaciones en el muro",
)
async def list_my_solidarity_posts(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    service: SolidarityService = Depends(get_solidarity_service),
):
    """Retorna todas las publicaciones creadas por el usuario autenticado (activas, completadas o pausadas)."""
    return await service.list_posts(
        author_id=current_user.id,
        status=None,  # Ver todos los estados del propio usuario
        page=page,
        limit=limit,
    )


@router.get(
    "/posts/{post_id}",
    response_model=SolidarityPostDetail,
    summary="Consultar detalle de una publicación solidaria",
)
async def get_solidarity_post_detail(
    post_id: uuid.UUID,
    service: SolidarityService = Depends(get_solidarity_service),
):
    """Obtiene los datos completos de una solicitud, oferta o donación vecinal."""
    return await service.get_post_detail(post_id)


# -------------------------------------------------------------
# PUBLICACIÓN, EDICIÓN Y GESTIÓN EN EL MURO
# -------------------------------------------------------------
@router.post(
    "/posts",
    response_model=SolidarityPostDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Publicar en el muro solidario",
)
async def create_solidarity_post(
    data: SolidarityPostCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: SolidarityService = Depends(get_solidarity_service),
):
    """Crea una nueva solicitud, oferta, donación o intercambio en el muro del barrio."""
    return await service.create_post(
        user_id=current_user.id,
        data=data,
    )


@router.put(
    "/posts/{post_id}",
    response_model=SolidarityPostDetail,
    summary="Editar una publicación propia",
)
async def update_solidarity_post(
    post_id: uuid.UUID,
    data: SolidarityPostUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    service: SolidarityService = Depends(get_solidarity_service),
):
    """Permite al autor modificar el contenido de su publicación en el muro."""
    return await service.update_post(
        post_id=post_id,
        user_id=current_user.id,
        data=data,
    )


@router.patch(
    "/posts/{post_id}/status",
    response_model=SolidarityPostDetail,
    summary="Cambiar estado de la publicación (ej: completada, cancelada)",
)
async def update_solidarity_post_status(
    post_id: uuid.UUID,
    status_update: SolidarityPostStatusUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    service: SolidarityService = Depends(get_solidarity_service),
):
    """Actualiza el estado de la publicación en el muro."""
    return await service.update_post_status(
        post_id=post_id,
        user_id=current_user.id,
        status_update=status_update,
    )


@router.delete(
    "/posts/{post_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar una publicación propia",
)
async def delete_solidarity_post(
    post_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: SolidarityService = Depends(get_solidarity_service),
):
    """Elimina definitivamente la publicación del muro solidario."""
    await service.delete_post(
        post_id=post_id,
        user_id=current_user.id,
    )


# -------------------------------------------------------------
# RESPUESTAS SOLIDARIAS / MANO AMIGA / QR HANDSHAKE
# -------------------------------------------------------------
@router.post(
    "/posts/{post_id}/respond",
    response_model=SolidarityResponseItem,
    status_code=status.HTTP_201_CREATED,
    summary="Ofrecer ayuda o responder a una solicitud",
)
async def respond_to_solidarity_post(
    post_id: uuid.UUID,
    data: SolidarityResponseCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: SolidarityService = Depends(get_solidarity_service),
):
    """Permite a un vecino postularse para ayudar, prestando una herramienta o coordinando."""
    return await service.respond_to_post(
        post_id=post_id,
        user_id=current_user.id,
        data=data,
    )


@router.get(
    "/posts/{post_id}/responses",
    response_model=List[SolidarityResponseItem],
    summary="Listar respuestas y voluntarios para una publicación",
)
async def list_solidarity_responses(
    post_id: uuid.UUID,
    service: SolidarityService = Depends(get_solidarity_service),
):
    """Retorna los vecinos que han respondido u ofrecido su apoyo para este pedido."""
    return await service.list_responses(post_id)


@router.patch(
    "/responses/{response_id}/status",
    response_model=SolidarityResponseItem,
    summary="Aceptar, rechazar o confirmar entrega solidaria",
)
async def update_solidarity_response_status(
    response_id: uuid.UUID,
    status_update: SolidarityResponseStatusUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    service: SolidarityService = Depends(get_solidarity_service),
):
    """Permite al creador o al voluntario validar el avance o entrega mediante QR."""
    return await service.update_response_status(
        response_id=response_id,
        user_id=current_user.id,
        status_update=status_update,
    )
