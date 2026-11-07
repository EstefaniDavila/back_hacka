import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


# --- Departamentos ---

class DepartmentBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Nombre del departamento")
    ubigeo: Optional[str] = Field(None, min_length=2, max_length=2, description="Código UBIGEO (2 dígitos)")


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    ubigeo: Optional[str] = Field(None, min_length=2, max_length=2)


class DepartmentResponse(DepartmentBase):
    id: int = Field(..., description="Identificador único")
    model_config = ConfigDict(from_attributes=True)


# --- Comunidades ---

class CommunityBase(BaseModel):
    name: str = Field(..., min_length=3, max_length=150, description="Nombre de la comunidad o barrio")
    district_id: Optional[int] = Field(None, description="ID del distrito al que pertenece")
    description: Optional[str] = Field(None, description="Descripción de la comunidad")
    status: str = Field("active", max_length=20, description="Estado de la comunidad")


class CommunityCreate(CommunityBase):
    pass


class CommunityUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=150)
    district_id: Optional[int] = None
    description: Optional[str] = None
    status: Optional[str] = Field(None, max_length=20)


class CommunityResponse(CommunityBase):
    id: uuid.UUID = Field(..., description="Identificador UUID de la comunidad")
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)
