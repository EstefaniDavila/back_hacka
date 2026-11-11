"""Esquemas Pydantic v2 para el módulo de usuarios y verificación."""
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ProfileBase(BaseModel):
    full_name: str = Field(..., max_length=150, description="Nombre y apellidos del usuario")
    phone: Optional[str] = Field(None, max_length=20, description="Número telefónico")
    avatar_url: Optional[str] = Field(None, description="URL del avatar del usuario")
    birth_date: Optional[date] = Field(None, description="Fecha de nacimiento")
    font_scale_preference: Optional[str] = Field("1.0", max_length=20, description="Preferencia de tamaño de fuente: 1.0, 1.15, 1.30")
    skill: Optional[str] = Field("Apoyo general", description="Habilidad u oficio principal del vecino")
    skills: Optional[List[str]] = Field(default_factory=list, description="Lista de habilidades y servicios que ofrece")


class ProfileCreate(ProfileBase):
    id: uuid.UUID = Field(..., description="UUID del usuario sincronizado con Supabase auth.users")
    account_status: Optional[str] = Field("pending_verification", max_length=20)


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(None, max_length=150)
    phone: Optional[str] = Field(None, max_length=20)
    avatar_url: Optional[str] = None
    birth_date: Optional[date] = None
    font_scale_preference: Optional[str] = Field(None, max_length=20)
    account_status: Optional[str] = Field(None, max_length=20)
    skill: Optional[str] = Field(None, description="Habilidad u oficio principal")
    skills: Optional[List[str]] = Field(None, description="Lista de habilidades")


class ProfileResponse(ProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_status: Optional[str] = "pending_verification"
    solidarity_helped_count: Optional[int] = 0
    solidarity_received_count: Optional[int] = 0
    created_at: Optional[datetime] = None
    address: Optional[str] = None
    street_address: Optional[str] = None
    reference: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    district_name: Optional[str] = None
    community_id: Optional[uuid.UUID] = None
    residence_status: Optional[str] = None


class IdentityVerificationBase(BaseModel):
    document_type: Optional[str] = Field("DNI", max_length=20)
    document_last4: Optional[str] = Field(None, max_length=4)
    identity_provider: Optional[str] = Field("vecired_ia_ocr", max_length=80)
    identity_status: Optional[str] = Field("pending", max_length=20)


class IdentityVerificationCreate(IdentityVerificationBase):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: uuid.UUID
    document_hash: Optional[str] = Field(None, max_length=128)
    verified_at: Optional[datetime] = None


class IdentityVerificationResponse(IdentityVerificationBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    document_hash: Optional[str] = None
    verified_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class UserAddressBase(BaseModel):
    address_id: uuid.UUID
    address_type: Optional[str] = Field("home", max_length=30)
    is_primary: Optional[bool] = True
    source: Optional[str] = Field("user_input", max_length=30)
    residence_status: Optional[str] = Field("unverified", max_length=20)


class UserAddressCreate(UserAddressBase):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: uuid.UUID
    valid_from: Optional[datetime] = Field(default_factory=datetime.utcnow)


class UserAddressResponse(UserAddressBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    valid_from: Optional[datetime] = None
    created_at: Optional[datetime] = None


class CommunityMembershipBase(BaseModel):
    community_id: uuid.UUID
    zone_id: Optional[uuid.UUID] = None
    block_id: Optional[uuid.UUID] = None
    role: Optional[str] = Field("neighbor", max_length=30)
    membership_status: Optional[str] = Field("active", max_length=20)


class CommunityMembershipCreate(CommunityMembershipBase):
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: uuid.UUID
    joined_at: Optional[datetime] = Field(default_factory=datetime.utcnow)


class CommunityMembershipResponse(CommunityMembershipBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    joined_at: Optional[datetime] = None


class IdentityVerificationResultResponse(BaseModel):
    success: bool
    identity_status: str = Field(..., description="incomplete, processing, verified, rejected, manual_review")
    document_type: str = "DNI"
    document_last4: Optional[str] = None
    extracted_data: Dict[str, Any] = Field(default_factory=dict)
    face_match: Dict[str, Any] = Field(default_factory=dict)
    message: str


class DNIExtractionResponse(BaseModel):
    """Respuesta estructurada para extracción de datos de DNI con Claude Vision."""
    success: bool
    dni_number: Optional[str] = None
    dni_last4: Optional[str] = None
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    birth_date: Optional[date] = None
    age: Optional[int] = None
    is_adult: bool = True
    underage_blocked: bool = False
    gender: Optional[str] = None
    ubigeo: Optional[str] = None
    unreadable_fields: List[str] = Field(default_factory=list)
    confidence: float = 0.0
    api_key_configured: bool = True
    message: str


class VerificationStatusSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    profile: ProfileResponse
    identity_verified: bool
    identity_status: str
    document_last4: Optional[str] = None
    residence_status: str
    community_id: Optional[uuid.UUID] = None
    community_name: Optional[str] = None


class StartDniVerificationResponse(BaseModel):
    """Respuesta para el Paso 1 de onboarding: OCR de DNI y apertura de sesión temporal."""
    success: bool
    stage: str = "dni_verified"
    session_id: Optional[str] = None
    verification_token: Optional[str] = None
    extracted_data: Optional[DNIExtractionResponse] = None
    underage_blocked: bool = False
    message: str


class VerifyFaceSessionResponse(BaseModel):
    """Respuesta para el Paso 2 de onboarding: Verificación facial contra el DNI con InsightFace."""
    success: bool
    stage: str = "face_verified"
    session_id: Optional[str] = None
    verification_token: Optional[str] = None
    is_match: bool
    confidence_score: float
    liveness_passed: bool
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class CompleteRegistrationRequest(BaseModel):
    """Cuerpo de solicitud para el Paso 6: Confirmación y registro definitivo."""
    verification_token: str = Field(..., description="Token JWT firmado emitido tras aprobar el Paso 2 de biometría")
    department: Optional[str] = Field("Lima", max_length=100)
    province: Optional[str] = Field("Lima", max_length=100)
    district: str = Field(..., max_length=100)
    community_name: Optional[str] = Field("Comunidad VeciRed", max_length=150)
    zone_name: Optional[str] = Field(None, max_length=100)
    block_code: Optional[str] = Field(None, max_length=30)
    street_address: str = Field(..., max_length=200)
    lot_number: Optional[str] = Field(None, max_length=30)
    reference: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    full_name: Optional[str] = Field(None, max_length=150)
    phone: Optional[str] = Field(None, max_length=20)
    avatar_url: Optional[str] = None
    occupation: Optional[str] = Field(None, max_length=80, description="Oficio o habilidad vecinal")
    skill: Optional[str] = Field(None, max_length=80, description="Habilidad vecinal complementaria")


class CompleteRegistrationResponse(BaseModel):
    """Respuesta del registro definitivo una vez persistidas todas las relaciones."""
    model_config = ConfigDict(from_attributes=True)

    success: bool
    user_id: uuid.UUID
    account_status: str = "verified"
    profile: ProfileResponse
    community_name: Optional[str] = None
    address: Optional[str] = None
    message: str


