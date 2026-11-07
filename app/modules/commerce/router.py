"""Rutas de API v1 para el módulo de comercio y servicios de VeciRed IA."""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status

from app.core.security import CurrentUser, get_current_user
from app.modules.commerce.dependencies import get_commerce_service
from app.modules.commerce.schemas import (
    ReviewCreate,
    ReviewResponse,
    ServiceCategoryResponse,
    ServiceCreate,
    ServiceDetailResponse,
    ServiceListItemResponse,
    ServiceStatusUpdate,
    ServiceUpdate,
)
from app.modules.commerce.service import CommerceService
from app.shared.pagination import PaginatedResponse

router = APIRouter(prefix="/services", tags=["Servicios de Proximidad"])


# -------------------------------------------------------------
# CATEGORÍAS
# -------------------------------------------------------------
@router.get(
    "/categories",
    response_model=List[ServiceCategoryResponse],
    summary="Listar categorías de servicios",
)
async def list_service_categories(
    service: CommerceService = Depends(get_commerce_service),
):
    """Retorna la lista de todas las categorías de servicios disponibles en VeciRed IA."""
    return await service.list_categories()


# -------------------------------------------------------------
# SERVICIOS: LISTADO Y BÚSQUEDA
# -------------------------------------------------------------
@router.get(
    "",
    response_model=PaginatedResponse[ServiceListItemResponse],
    summary="Explorar servicios disponibles con búsqueda y filtros",
)
async def list_services(
    q: Optional[str] = Query(None, description="Término de búsqueda libre por título, descripción o vecino"),
    category_id: Optional[uuid.UUID] = Query(None, description="Filtrar por ID de categoría"),
    community_id: Optional[uuid.UUID] = Query(None, description="Filtrar por ID de comunidad"),
    sort_by: str = Query("newest", pattern="^(newest|rating|price_asc|price_desc)$", description="Criterio de ordenamiento"),
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(20, ge=1, le=100, description="Cantidad de registros por página"),
    service: CommerceService = Depends(get_commerce_service),
):
    """
    Retorna los servicios vecinales activos en base a criterios de búsqueda, categoría,
    comunidad y orden (por cercanía/recientes, mejor calificados o precio).
    """
    return await service.list_services(
        query=q,
        category_id=category_id,
        community_id=community_id,
        sort_by=sort_by,
        page=page,
        limit=limit,
    )


# -------------------------------------------------------------
# SERVICIOS PROPIOS Y POR VECINO
# -------------------------------------------------------------
@router.get(
    "/my",
    response_model=PaginatedResponse[ServiceListItemResponse],
    summary="Listar mis servicios publicados",
)
async def list_my_services(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    service: CommerceService = Depends(get_commerce_service),
):
    """Retorna todos los servicios publicados por el vecino autenticado, incluyendo pausados."""
    return await service.list_my_services(
        user_id=current_user.id,
        page=page,
        limit=limit,
    )


@router.get(
    "/user/{user_id}",
    response_model=PaginatedResponse[ServiceListItemResponse],
    summary="Listar servicios públicos de un vecino",
)
async def list_user_services(
    user_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    service: CommerceService = Depends(get_commerce_service),
):
    """Retorna los servicios públicos activos ofrecidos por un vecino específico."""
    return await service.list_user_services(
        user_id=user_id,
        page=page,
        limit=limit,
    )


# -------------------------------------------------------------
# DETALLE DE SERVICIO
# -------------------------------------------------------------
@router.get(
    "/{service_id}",
    response_model=ServiceDetailResponse,
    summary="Consultar detalle de un servicio",
)
async def get_service_detail(
    service_id: uuid.UUID,
    service: CommerceService = Depends(get_commerce_service),
):
    """Retorna la ficha descriptiva completa del servicio, su prestador y reseñas."""
    return await service.get_service_detail(service_id)


# -------------------------------------------------------------
# CREACIÓN, EDICIÓN Y ESTADOS DE SERVICIO
# -------------------------------------------------------------
@router.post(
    "",
    response_model=ServiceDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Publicar un nuevo servicio",
)
async def create_service(
    data: ServiceCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: CommerceService = Depends(get_commerce_service),
):
    """Crea y publica un nuevo servicio ofrecido por el vecino autenticado."""
    return await service.create_service(
        user_id=current_user.id,
        data=data,
    )


@router.put(
    "/{service_id}",
    response_model=ServiceDetailResponse,
    summary="Editar una publicación de servicio propia",
)
async def update_service(
    service_id: uuid.UUID,
    data: ServiceUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    service: CommerceService = Depends(get_commerce_service),
):
    """Permite al autor actualizar la información de su servicio."""
    return await service.update_service(
        service_id=service_id,
        user_id=current_user.id,
        data=data,
    )


@router.patch(
    "/{service_id}/status",
    response_model=ServiceDetailResponse,
    summary="Pausar o reactivar un servicio propio",
)
async def update_service_status(
    service_id: uuid.UUID,
    status_update: ServiceStatusUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    service: CommerceService = Depends(get_commerce_service),
):
    """Cambia el estado de una publicación (ej: 'active' a 'paused' o viceversa)."""
    return await service.update_service_status(
        service_id=service_id,
        user_id=current_user.id,
        status_update=status_update,
    )


@router.delete(
    "/{service_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desactivar o eliminar un servicio propio",
)
async def delete_service(
    service_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: CommerceService = Depends(get_commerce_service),
):
    """Desactiva lógicamente la publicación del servicio del usuario."""
    await service.delete_service(
        service_id=service_id,
        user_id=current_user.id,
    )


# -------------------------------------------------------------
# VALORACIONES / RESEÑAS
# -------------------------------------------------------------
@router.post(
    "/{service_id}/reviews",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Valorar un servicio contratado",
)
async def add_service_review(
    service_id: uuid.UUID,
    review_data: ReviewCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: CommerceService = Depends(get_commerce_service),
):
    """Registra una calificación (1-5 estrellas) y comentario para el servicio y su proveedor."""
    return await service.add_service_review(
        service_id=service_id,
        reviewer_id=current_user.id,
        data=review_data,
    )


@router.get(
    "/{service_id}/reviews",
    response_model=List[ReviewResponse],
    summary="Listar reseñas de un servicio",
)
async def list_service_reviews(
    service_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    service: CommerceService = Depends(get_commerce_service),
):
    """Consulta las valoraciones y comentarios de los vecinos para este servicio."""
    return await service.list_service_reviews(
        service_id=service_id,
        page=page,
        limit=limit,
    )
