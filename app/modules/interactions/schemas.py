"""Esquemas Pydantic v2 para el módulo de interacciones y calificaciones (reviews)."""
import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ReviewCreate(BaseModel):
    reviewed_user_id: Optional[uuid.UUID] = Field(None, description="UUID del usuario calificado")
    service_id: Optional[uuid.UUID] = Field(None, description="UUID del servicio contratado (opcional)")
    order_id: Optional[uuid.UUID] = Field(None, description="UUID del pedido local (opcional)")
    solidarity_response_id: Optional[uuid.UUID] = Field(None, description="UUID del favor solidario (opcional)")
    rating: int = Field(..., ge=1, le=5, description="Calificación de 1 a 5 estrellas")
    comment: Optional[str] = Field(None, max_length=1000, description="Comentario o reseña de la experiencia")


class ReviewResponse(BaseModel):
    id: uuid.UUID
    reviewer_id: uuid.UUID
    reviewer_name: Optional[str] = "Vecino de la comunidad"
    reviewer_avatar: Optional[str] = None
    reviewed_user_id: uuid.UUID
    service_id: Optional[uuid.UUID] = None
    order_id: Optional[uuid.UUID] = None
    solidarity_response_id: Optional[uuid.UUID] = None
    rating: int
    comment: Optional[str] = None
    moderation_status: Optional[str] = "approved"
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserReputationSummary(BaseModel):
    user_id: uuid.UUID
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    average_rating: float = Field(0.0, description="Promedio de estrellas")
    total_reviews: int = Field(0, description="Total de calificaciones recibidas")
    reviews: List[ReviewResponse] = Field(default_factory=list)
