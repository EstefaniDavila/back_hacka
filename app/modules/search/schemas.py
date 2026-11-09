"""Esquemas Pydantic v2 para el motor de búsqueda inteligente de VeciRed IA."""
import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class SearchSort(str, Enum):
    RELEVANCE = "relevance"
    DISTANCE = "distance"
    RECOMMENDED = "recommended"


class ScoreBreakdown(BaseModel):
    """Desglose transparente y documentado del ranking multidimensional."""
    match_score: float = Field(..., description="Puntuación de coincidencia textual (0.0 a 1.0, peso 25%)")
    distance_score: float = Field(..., description="Puntuación de proximidad barrial (0.0 a 1.0, peso 55%)")
    reputation_score: float = Field(..., description="Puntuación bayesiana de reputación (0.0 a 1.0, peso 15%)")
    experience_score: float = Field(..., description="Puntuación de experiencia comprobada (0.0 a 1.0, peso 5%)")
    final_score: float = Field(..., description="Puntuación consolidada normalizada (0.0 a 1.0)")
    distance_meters: Optional[float] = Field(None, description="Distancia real en metros")
    algorithm_notes: Optional[str] = Field(None, description="Observaciones del algoritmo")


# ----------------------------------------------------------------------
# 1. SERVICIOS
# ----------------------------------------------------------------------
class ServiceSearchResult(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str] = None
    category_id: Optional[uuid.UUID] = None
    category_name: Optional[str] = None
    category_icon: Optional[str] = None
    price_from: Optional[Decimal] = None
    price_unit: Optional[str] = None
    availability: Optional[str] = None
    provider_id: uuid.UUID
    provider_name: str
    provider_avatar: Optional[str] = None
    provider_phone: Optional[str] = None
    is_verified: bool = False
    is_new: bool = False
    rating_avg: float = 0.0
    reviews_count: int = 0
    bayesian_rating: float = 4.0
    completed_interactions: int = 0
    distance_km: Optional[float] = None
    distance_meters: Optional[float] = None
    community_id: Optional[uuid.UUID] = None
    community_name: Optional[str] = None
    district_name: Optional[str] = None
    score: float = 0.0
    ranking_score: float = 0.0
    score_breakdown: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------------
# 2. PRODUCTOS
# ----------------------------------------------------------------------
class ProductSearchResult(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    price: Decimal
    stock: Optional[int] = None
    image_url: Optional[str] = None
    business_id: Optional[uuid.UUID] = None
    business_name: Optional[str] = None
    category_id: Optional[uuid.UUID] = None
    category_name: Optional[str] = None
    owner_id: Optional[uuid.UUID] = None
    owner_name: Optional[str] = None
    is_verified: bool = False
    is_new: bool = False
    rating_avg: float = 0.0
    reviews_count: int = 0
    bayesian_rating: float = 4.0
    distance_km: Optional[float] = None
    distance_meters: Optional[float] = None
    community_name: Optional[str] = None
    district_name: Optional[str] = None
    score: float = 0.0
    ranking_score: float = 0.0
    score_breakdown: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------------
# 3. SOLIDARIDAD
# ----------------------------------------------------------------------
class SolidaritySearchResult(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    post_type: str = Field(..., description="request, offer, donation, exchange")
    status: Optional[str] = "open"
    author_id: uuid.UUID
    author_name: str
    author_avatar: Optional[str] = None
    is_verified: bool = False
    is_urgent: bool = False
    distance_km: Optional[float] = None
    distance_meters: Optional[float] = None
    community_name: Optional[str] = None
    district_name: Optional[str] = None
    score: float = 0.0
    ranking_score: float = 0.0
    score_breakdown: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------------
# 4. EMERGENCIAS
# ----------------------------------------------------------------------
class EmergencySearchResult(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str] = None
    emergency_type: str
    severity: str = Field(..., description="critical, high, medium, low")
    status: str = Field(..., description="active, reported, in_progress, resolved")
    reported_by: uuid.UUID
    reporter_name: Optional[str] = None
    occurred_at: Optional[datetime] = None
    distance_km: Optional[float] = None
    distance_meters: Optional[float] = None
    community_name: Optional[str] = None
    district_name: Optional[str] = None
    score: float = 0.0
    ranking_score: float = 0.0
    score_breakdown: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ----------------------------------------------------------------------
# 5. RESULTADO UNIFICADO Y BÚSQUEDA GLOBAL
# ----------------------------------------------------------------------
class UnifiedSearchResultItem(BaseModel):
    """Representación unificada de cualquier entidad en la búsqueda transversal."""
    id: uuid.UUID
    module: str = Field(..., description="services, products, solidarity, emergencies")
    title: str
    subtitle: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    icon: Optional[str] = None
    badge: Optional[str] = None
    price_label: Optional[str] = None
    distance_km: Optional[float] = None
    distance_meters: Optional[float] = None
    location_label: Optional[str] = None
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    is_new: bool = False
    is_verified: bool = False
    score: float
    ranking_score: float
    score_breakdown: Optional[Dict[str, Any]] = None
    detail_path: str


class SearchLocationMeta(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius_km: Optional[float] = None
    reference: Optional[str] = None


class SearchPaginationMeta(BaseModel):
    total: int
    page: int
    limit: int
    total_pages: int


class GlobalSearchResponse(BaseModel):
    """Respuesta consolidada para GET /api/v1/search."""
    query: Optional[str] = None
    location_applied: Optional[SearchLocationMeta] = None
    sort_applied: str = "recommended"
    total_results: int
    page: int
    limit: int
    total_pages: int
    items: List[UnifiedSearchResultItem]
    sections_summary: Dict[str, int] = Field(default_factory=dict)
    top_sections: Dict[str, List[Any]] = Field(default_factory=dict)


class PaginatedServicesSearch(BaseModel):
    items: List[ServiceSearchResult]
    meta: SearchPaginationMeta
    location_applied: Optional[SearchLocationMeta] = None
    sort_applied: str = "recommended"


class PaginatedProductsSearch(BaseModel):
    items: List[ProductSearchResult]
    meta: SearchPaginationMeta
    location_applied: Optional[SearchLocationMeta] = None
    sort_applied: str = "recommended"


class PaginatedSolidaritySearch(BaseModel):
    items: List[SolidaritySearchResult]
    meta: SearchPaginationMeta
    location_applied: Optional[SearchLocationMeta] = None
    sort_applied: str = "recommended"


class PaginatedEmergenciesSearch(BaseModel):
    items: List[EmergencySearchResult]
    meta: SearchPaginationMeta
    location_applied: Optional[SearchLocationMeta] = None
    sort_applied: str = "recommended"

