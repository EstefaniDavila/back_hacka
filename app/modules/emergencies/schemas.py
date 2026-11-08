"""Esquemas Pydantic v2 para el módulo de emergencias vecinales de VeciRed IA."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


# ----------------------------------------------------------------------
# ESQUEMAS DE NECESIDADES Y RECURSOS
# ----------------------------------------------------------------------
class EmergencyNeedCreate(BaseModel):
    """Payload para registrar una necesidad específica (agua, frazadas, arena, etc.)."""
    resource_name: str = Field(..., min_length=2, max_length=100, description="Nombre del recurso (ej: Agua potable)")
    quantity_required: Decimal = Field(..., gt=0, description="Cantidad total requerida")
    unit: str = Field("unidades", max_length=30, description="Unidad de medida (botellas, packs, sacos, etc.)")


class EmergencyNeedResponse(BaseModel):
    """Ficha de una necesidad de emergencia con avance de cumplimiento."""
    id: uuid.UUID
    emergency_id: uuid.UUID
    resource_name: str
    quantity_required: Decimal
    quantity_committed: Decimal = Decimal(0)
    quantity_delivered: Decimal = Decimal(0)
    unit: str
    status: Optional[str] = "active"
    model_config = ConfigDict(from_attributes=True)


class EmergencyContributionCreate(BaseModel):
    """Payload para donar o comprometer recursos a una necesidad."""
    quantity: Decimal = Field(..., gt=0, description="Cantidad que el vecino donará")
    collection_point_id: Optional[uuid.UUID] = Field(None, description="Punto de acopio opcional")


class EmergencyContributionResponse(BaseModel):
    """Ficha de una contribución vecinal a una necesidad de emergencia."""
    id: uuid.UUID
    need_id: uuid.UUID
    contributor_id: uuid.UUID
    contributor_name: str
    contributor_avatar: Optional[str] = None
    quantity: Decimal
    contribution_status: str
    committed_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------------
# ESQUEMAS DE EMERGENCIA BARRIAL
# ----------------------------------------------------------------------
class EmergencyCreate(BaseModel):
    """Payload para reportar una emergencia en el barrio."""
    emergency_type: str = Field("seguridad", min_length=2, max_length=50, description="Tipo: inundacion, incendio, sismo, seguridad, medica, otro")
    title: str = Field(..., min_length=3, max_length=150, description="Título breve (ej: Inundación en Mz 2)")
    description: Optional[str] = Field(None, max_length=2000, description="Detalle de lo ocurrido y requerimientos urgentes")
    severity: str = Field("high", pattern="^(low|medium|high|critical)$", description="Nivel de severidad")
    community_id: Optional[uuid.UUID] = Field(None, description="ID de la comunidad vecinal")
    address_id: Optional[uuid.UUID] = Field(None, description="ID de dirección específica si aplica")
    alert_radius_m: Optional[int] = Field(500, description="Radio de alerta en metros para notificación a vecinos")


class EmergencyStatusUpdate(BaseModel):
    """Payload para cambiar el estado de la emergencia."""
    status: str = Field(..., pattern="^(reportada|en_atencion|atendida|cerrada)$")


class EmergencyListItemResponse(BaseModel):
    """Ficha resumida de emergencia para listas y banners de alerta activa."""
    id: uuid.UUID
    reported_by: uuid.UUID
    reporter_name: str
    reporter_avatar: Optional[str] = None
    community_id: uuid.UUID
    community_name: Optional[str] = None
    emergency_type: str
    title: str
    description: Optional[str] = None
    severity: str
    status: str
    occurred_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    needs_count: int = 0
    volunteers_count: int = 0
    radius_m: Optional[int] = 500
    model_config = ConfigDict(from_attributes=True)


class EmergencyDetailResponse(EmergencyListItemResponse):
    """Ficha detallada con la lista de necesidades requeridas y aportes."""
    needs: List[EmergencyNeedResponse] = []
    contributions: List[EmergencyContributionResponse] = []
    model_config = ConfigDict(from_attributes=True)


class VolunteerRegister(BaseModel):
    """Payload para sumarse como voluntario ante la emergencia."""
    emergency_id: Optional[uuid.UUID] = Field(None, description="ID de la emergencia a la que apoya")
    name: Optional[str] = Field(None, max_length=150)
    skill: Optional[str] = Field(None, max_length=100)
    avatar: Optional[str] = Field("👤", max_length=50)
    distance_m: Optional[int] = Field(50, description="Distancia real calculada en metros")
    status: Optional[str] = Field("En camino", max_length=50)
    message: Optional[str] = Field(None, max_length=500, description="Mensaje o equipo disponible (ej: En camino con palas)")


class VolunteerResponse(BaseModel):
    """Ficha de un voluntario / brigadista vecinal en guardia."""
    id: str
    emergency_id: Optional[str] = None
    user_id: Optional[str] = None
    name: str
    skill: str
    avatar: str = "👤"
    distance: str = "50m"
    distance_m: int = 50
    status: str = "En guardia"
    model_config = ConfigDict(from_attributes=True)