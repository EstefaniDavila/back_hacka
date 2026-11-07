"""Esquemas Pydantic v2 para el módulo commerce (servicios y valoraciones) de VeciRed IA."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


# -------------------------------------------------------------
# Categorías de Servicios
# -------------------------------------------------------------
class ServiceCategoryBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    icon: Optional[str] = Field(None, max_length=80)


class ServiceCategoryResponse(ServiceCategoryBase):
    id: uuid.UUID
    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------------
# Valoraciones / Reseñas (Reviews)
# -------------------------------------------------------------
class ReviewCreate(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="Calificación de 1 a 5 estrellas")
    comment: Optional[str] = Field(None, max_length=1000, description="Comentario o reseña de la experiencia")


class ReviewResponse(BaseModel):
    id: uuid.UUID
    reviewer_id: uuid.UUID
    reviewer_name: Optional[str] = None
    reviewer_avatar: Optional[str] = None
    reviewed_user_id: uuid.UUID
    service_id: Optional[uuid.UUID] = None
    rating: int
    comment: Optional[str] = None
    moderation_status: Optional[str] = "approved"
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------------
# Proveedor (resumen para tarjetas de servicios)
# -------------------------------------------------------------
class ProviderSummary(BaseModel):
    id: uuid.UUID
    full_name: str
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    account_status: Optional[str] = None
    is_verified: bool = False

    model_config = ConfigDict(from_attributes=True)


# -------------------------------------------------------------
# Servicios: Creación y Edición
# -------------------------------------------------------------
class ServiceCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=150, description="Título del servicio")
    description: Optional[str] = Field(None, max_length=2000, description="Descripción detallada de la oferta")
    category_id: uuid.UUID = Field(..., description="ID de la categoría del servicio")
    community_id: Optional[uuid.UUID] = Field(None, description="ID de la comunidad territorial (opcional si se infiere del usuario)")
    address_id: Optional[uuid.UUID] = Field(None, description="ID de dirección de referencia")
    price_from: Optional[Decimal] = Field(None, ge=0, description="Precio inicial o referencia en Soles")
    price_unit: Optional[str] = Field("servicio", max_length=30, description="Unidad de precio (hora, visita, servicio, presupuesto)")
    availability: Optional[str] = Field(None, max_length=100, description="Disponibilidad horaria (ej: 'Lunes a Viernes', '24/7')")


class ServiceUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=150)
    description: Optional[str] = Field(None, max_length=2000)
    category_id: Optional[uuid.UUID] = None
    price_from: Optional[Decimal] = Field(None, ge=0)
    price_unit: Optional[str] = Field(None, max_length=30)
    availability: Optional[str] = Field(None, max_length=100)


class ServiceStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(active|paused|inactive)$", description="Nuevo estado del servicio")


# -------------------------------------------------------------
# Respuestas de Servicios
# -------------------------------------------------------------
class ServiceListItemResponse(BaseModel):
    id: uuid.UUID
    provider_id: uuid.UUID
    provider_name: str
    provider_avatar: Optional[str] = None
    provider_phone: Optional[str] = None
    is_verified: bool = False
    category_id: uuid.UUID
    category_name: str
    category_icon: Optional[str] = None
    community_id: uuid.UUID
    community_name: Optional[str] = None
    title: str
    description: Optional[str] = None
    price_from: Optional[Decimal] = None
    price_unit: Optional[str] = "servicio"
    availability: Optional[str] = None
    status: str = "active"
    rating_avg: float = 0.0
    reviews_count: int = 0
    distance_m: Optional[int] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ServiceDetailResponse(ServiceListItemResponse):
    provider: ProviderSummary
    recent_reviews: List[ReviewResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

