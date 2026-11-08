from typing import List
from fastapi import APIRouter, Depends, Query, status
from app.modules.geo.dependencies import get_geo_service
from app.modules.geo.schemas import (
    CommunityCreate,
    CommunityResponse,
    DepartmentCreate,
    DepartmentResponse,
    DepartmentUpdate,
    ServiceMapMarker,
    EmergencyMapMarker,
    MapOverviewResponse,
)
from app.modules.geo.service import GeoService
from app.shared.pagination import PaginatedResponse

router = APIRouter(prefix="/geo", tags=["Geo / Territorio"])


# --- Endpoints de Departamentos ---

@router.get(
    "/departments",
    response_model=PaginatedResponse[DepartmentResponse],
    summary="Listar departamentos paginados",
)
async def list_departments(
    page: int = Query(1, ge=1, description="Número de página"),
    limit: int = Query(25, ge=1, le=100, description="Elementos por página"),
    service: GeoService = Depends(get_geo_service),
):
    return await service.list_departments(page=page, limit=limit)


@router.post(
    "/departments",
    response_model=DepartmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un departamento",
)
async def create_department(
    data: DepartmentCreate,
    service: GeoService = Depends(get_geo_service),
):
    return await service.create_department(data)


@router.get(
    "/departments/{department_id}",
    response_model=DepartmentResponse,
    summary="Obtener detalle de un departamento",
)
async def get_department(
    department_id: int,
    service: GeoService = Depends(get_geo_service),
):
    return await service.get_department(department_id)


@router.put(
    "/departments/{department_id}",
    response_model=DepartmentResponse,
    summary="Actualizar un departamento",
)
async def update_department(
    department_id: int,
    data: DepartmentUpdate,
    service: GeoService = Depends(get_geo_service),
):
    return await service.update_department(department_id, data)


@router.delete(
    "/departments/{department_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un departamento",
)
async def delete_department(
    department_id: int,
    service: GeoService = Depends(get_geo_service),
):
    await service.delete_department(department_id)


# --- Endpoints de Comunidades ---

@router.get(
    "/communities",
    response_model=List[CommunityResponse],
    summary="Listar comunidades activas",
)
async def list_communities(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    service: GeoService = Depends(get_geo_service),
):
    return await service.list_communities(skip=skip, limit=limit)


@router.post(
    "/communities",
    response_model=CommunityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una nueva comunidad",
)
async def create_community(
    data: CommunityCreate,
    service: GeoService = Depends(get_geo_service),
):
    return await service.create_community(data)


# --- Endpoints de Mapa Vecinal e Interactivo ---

@router.get(
    "/map/services",
    response_model=List[ServiceMapMarker],
    summary="Obtener marcadores de servicios en el mapa",
)
async def get_services_map(
    service: GeoService = Depends(get_geo_service),
):
    """Retorna las personas y negocios que ofrecen servicios con sus coordenadas para el mapa."""
    return await service.get_services_map_markers()


@router.get(
    "/map/emergencies",
    response_model=List[EmergencyMapMarker],
    summary="Obtener marcadores de emergencias activas en el mapa",
)
async def get_emergencies_map(
    service: GeoService = Depends(get_geo_service),
):
    """Retorna los puntos geográficos donde se encuentran activadas emergencias vecinales."""
    return await service.get_emergencies_map_markers()


@router.get(
    "/map/all",
    response_model=MapOverviewResponse,
    summary="Obtener vista integral del mapa (servicios y emergencias)",
)
async def get_map_all(
    service: GeoService = Depends(get_geo_service),
):
    """Retorna de manera unificada servicios y emergencias para la renderización del mapa."""
    return await service.get_map_overview()
