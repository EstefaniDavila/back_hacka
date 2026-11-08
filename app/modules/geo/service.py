import math
from typing import Sequence
from app.core.exceptions import EntityNotFoundException, VeciRedException
from app.modules.geo.models import Department, Community
from app.modules.geo.repository import DepartmentRepository, CommunityRepository, MapRepository
from app.modules.geo.schemas import (
    CommunityCreate,
    CommunityUpdate,
    DepartmentCreate,
    DepartmentResponse,
    DepartmentUpdate,
    ServiceMapMarker,
    EmergencyMapMarker,
    MapOverviewResponse,
)
from app.shared.pagination import PageMeta, PaginatedResponse


class GeoService:
    """Capa de lógica de negocio para entidades territoriales y comunidades."""

    def __init__(
        self,
        dept_repo: DepartmentRepository,
        comm_repo: CommunityRepository,
        map_repo: MapRepository = None,
    ):
        self.dept_repo = dept_repo
        self.comm_repo = comm_repo
        self.map_repo = map_repo or MapRepository(comm_repo.session)

    # --- Departamentos ---

    async def list_departments(
        self, page: int = 1, limit: int = 50
    ) -> PaginatedResponse[DepartmentResponse]:
        """Obtiene departamentos paginados serializados con DepartmentResponse."""
        skip = (page - 1) * limit
        total = await self.dept_repo.count()
        items = await self.dept_repo.get_multi(skip=skip, limit=limit, order_by=Department.name)
        total_pages = math.ceil(total / limit) if total > 0 else 1

        dept_items = [DepartmentResponse.model_validate(item) for item in items]

        return PaginatedResponse(
            items=dept_items,
            meta=PageMeta(total=total, page=page, limit=limit, total_pages=total_pages),
        )

    async def get_department(self, department_id: int) -> Department:
        """Obtiene un departamento por su ID o lanza 404."""
        dept = await self.dept_repo.get_by_id(department_id)
        if not dept:
            raise EntityNotFoundException("Departamento", department_id)
        return dept

    async def create_department(self, data: DepartmentCreate) -> Department:
        """Crea un nuevo departamento validando duplicados de nombre o UBIGEO."""
        if data.ubigeo:
            existing_ubigeo = await self.dept_repo.get_by_ubigeo(data.ubigeo)
            if existing_ubigeo:
                raise VeciRedException(
                    message=f"Ya existe un departamento con UBIGEO '{data.ubigeo}'",
                    code="UBIGEO_ALREADY_EXISTS",
                    status_code=409,
                )

        existing_name = await self.dept_repo.get_by_name(data.name)
        if existing_name:
            raise VeciRedException(
                message=f"Ya existe un departamento con nombre '{data.name}'",
                code="DEPARTMENT_NAME_EXISTS",
                status_code=409,
            )

        return await self.dept_repo.create(data)

    async def update_department(
        self, department_id: int, data: DepartmentUpdate
    ) -> Department:
        """Actualiza un departamento existente."""
        dept = await self.get_department(department_id)
        return await self.dept_repo.update(dept, data)

    async def delete_department(self, department_id: int) -> None:
        """Elimina un departamento existente."""
        await self.get_department(department_id)
        await self.dept_repo.delete(department_id)

    # --- Comunidades ---

    async def list_communities(self, skip: int = 0, limit: int = 50) -> Sequence[Community]:
        """Lista comunidades activas."""
        return await self.comm_repo.get_active(skip=skip, limit=limit)

    async def create_community(self, data: CommunityCreate) -> Community:
        """Crea una comunidad."""
        return await self.comm_repo.create(data)

    # --- Marcadores para el Mapa ---

    async def get_services_map_markers(self) -> list[ServiceMapMarker]:
        """Retorna la lista de servicios activos para ubicarlos en el mapa."""
        raw_services = await self.map_repo.get_services_markers()
        return [ServiceMapMarker(**s) for s in raw_services]

    async def get_emergencies_map_markers(self) -> list[EmergencyMapMarker]:
        """Retorna la lista de emergencias activas para el mapa."""
        raw_emergencies = await self.map_repo.get_emergencies_markers()
        return [EmergencyMapMarker(**e) for e in raw_emergencies]

    async def get_map_overview(self) -> MapOverviewResponse:
        """Retorna vista consolidada de servicios y emergencias en el mapa."""
        services = await self.get_services_map_markers()
        emergencies = await self.get_emergencies_map_markers()
        return MapOverviewResponse(services=services, emergencies=emergencies)
