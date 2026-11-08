"""Rutas de API v1 para valoraciones y reputación comunitaria (reviews)."""
import uuid
from typing import List
from fastapi import APIRouter, Depends, Query, status

from app.core.security import CurrentUser, get_current_user
from app.modules.interactions.dependencies import get_review_service
from app.modules.interactions.schemas import (
    ReviewCreate,
    ReviewResponse,
    UserReputationSummary,
)
from app.modules.interactions.service import ReviewService

router = APIRouter(prefix="/reviews", tags=["Calificaciones y Reputación"])


@router.post(
    "",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar una nueva calificación o reseña vecinal",
)
async def create_review(
    data: ReviewCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: ReviewService = Depends(get_review_service),
):
    """Permite calificar un servicio, compra o favor recibido de 1 a 5 estrellas con comentario."""
    return await service.create_review(
        reviewer_id=current_user.id,
        data=data,
    )


@router.get(
    "/service/{service_id}",
    response_model=List[ReviewResponse],
    summary="Consultar valoraciones de un servicio",
)
async def list_service_reviews(
    service_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    service: ReviewService = Depends(get_review_service),
):
    """Retorna las reseñas y comentarios realizados por vecinos para un servicio."""
    return await service.list_service_reviews(
        service_id=service_id,
        page=page,
        limit=limit,
    )


@router.get(
    "/user/{user_id}",
    response_model=UserReputationSummary,
    summary="Consultar reputación y reseñas recibidas por un vecino",
)
async def get_user_reputation(
    user_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    service: ReviewService = Depends(get_review_service),
):
    """Calcula el promedio de estrellas y lista el historial de reseñas de un usuario."""
    return await service.get_user_reputation(
        user_id=user_id,
        page=page,
        limit=limit,
    )
