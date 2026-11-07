from typing import Generic, List, TypeVar
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PageMeta(BaseModel):
    """Metadatos de paginación."""
    total: int = Field(..., description="Total de registros encontrados")
    page: int = Field(..., description="Página actual (1-indexed)")
    limit: int = Field(..., description="Registros por página")
    total_pages: int = Field(..., description="Total de páginas disponibles")
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)


class PaginatedResponse(BaseModel, Generic[T]):
    """Estructura estándar de respuesta paginada."""
    items: List[T]
    meta: PageMeta
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)
