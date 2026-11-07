"""Esquemas Pydantic v2 para el módulo de solidaridad y muro vecinal."""
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


# ----------------------------------------------------------------------
# ESQUEMAS PARA PUBLICACIONES SOLIDARIAS (MURO)
# ----------------------------------------------------------------------
class SolidarityPostCreate(BaseModel):
    """Payload para publicar una solicitud, oferta, donación o intercambio en el muro."""
    title: str = Field(..., min_length=3, max_length=150, description="Título claro del favor o ayuda")
    description: Optional[str] = Field(None, max_length=2000, description="Detalle del pedido o lo que se ofrece")
    category: Optional[str] = Field("Herramientas", max_length=60, description="Categoría: Herramientas, Donaciones, Apoyo temporal, Intercambio, etc.")
    post_type: str = Field("request", pattern="^(request|offer|donation|exchange)$", description="Tipo: request, offer, donation, exchange")
    community_id: Optional[uuid.UUID] = Field(None, description="Comunidad vecinal (si no se envía se usa la del perfil)")


class SolidarityPostUpdate(BaseModel):
    """Payload para actualizar una publicación propia en el muro."""
    title: Optional[str] = Field(None, min_length=3, max_length=150)
    description: Optional[str] = Field(None, max_length=2000)
    category: Optional[str] = Field(None, max_length=60)
    post_type: Optional[str] = Field(None, pattern="^(request|offer|donation|exchange)$")


class SolidarityPostStatusUpdate(BaseModel):
    """Payload para cambiar el estado de la publicación."""
    status: str = Field(..., pattern="^(active|in_progress|completed|cancelled)$")


class SolidarityPostListItem(BaseModel):
    """Ficha resumida de una publicación para el feed o muro solidario."""
    id: uuid.UUID
    author_id: uuid.UUID
    author_name: str
    author_avatar: Optional[str] = None
    community_id: uuid.UUID
    community_name: Optional[str] = None
    category: Optional[str] = None
    post_type: str
    title: str
    description: Optional[str] = None
    status: str
    responses_count: int = 0
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class SolidarityPostDetail(SolidarityPostListItem):
    """Ficha detallada con información adicional del contacto o ubicación."""
    author_phone: Optional[str] = None
    block_code: Optional[str] = None
    street_address: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------------
# ESQUEMAS PARA RESPUESTAS SOLIDARIAS / MANO AMIGA
# ----------------------------------------------------------------------
class SolidarityResponseCreate(BaseModel):
    """Payload para responder a una solicitud u oferta vecinal."""
    message: Optional[str] = Field(None, max_length=1000, description="Mensaje explicativo o disponibilidad")
    return_due_date: Optional[datetime] = Field(None, description="Fecha límite estimada de devolución si es préstamo")


class SolidarityResponseStatusUpdate(BaseModel):
    """Payload para actualizar el estado del intercambio o ayuda."""
    response_status: str = Field(..., pattern="^(pending|accepted|completed|cancelled)$")


class SolidarityResponseItem(BaseModel):
    """Detalle de una respuesta vecinal a una publicación solidaria."""
    id: uuid.UUID
    post_id: uuid.UUID
    responder_id: uuid.UUID
    responder_name: str
    responder_avatar: Optional[str] = None
    responder_phone: Optional[str] = None
    message: Optional[str] = None
    response_status: str
    handshake_qr_code: Optional[str] = None
    return_due_date: Optional[datetime] = None
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)
