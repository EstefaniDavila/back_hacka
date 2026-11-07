"""Módulo de Geo / Territorio para VeciRed IA."""
from .models import (
    Address,
    Block,
    Community,
    Department,
    District,
    Province,
    Zone,
)
from .repository import CommunityRepository, DepartmentRepository
from .router import router as geo_router
from .schemas import (
    CommunityCreate,
    CommunityResponse,
    CommunityUpdate,
    DepartmentCreate,
    DepartmentResponse,
    DepartmentUpdate,
)
from .service import GeoService

__all__ = [
    "Address",
    "Block",
    "Community",
    "Department",
    "District",
    "Province",
    "Zone",
    "DepartmentRepository",
    "CommunityRepository",
    "GeoService",
    "DepartmentCreate",
    "DepartmentUpdate",
    "DepartmentResponse",
    "CommunityCreate",
    "CommunityUpdate",
    "CommunityResponse",
    "geo_router",
]
