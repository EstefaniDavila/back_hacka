from typing import List
from fastapi import APIRouter, Depends, Query, status
from app.modules.geo.dependencies import get_geo_service
from app.modules.geo.schemas import (
    CommunityCreate,
    CommunityResponse,
    DepartmentCreate,
    DepartmentResponse,
    DepartmentUpdate,
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
