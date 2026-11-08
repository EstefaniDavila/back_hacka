from typing import Optional, Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.geo.models import Department, Community
from app.modules.geo.schemas import DepartmentCreate, DepartmentUpdate, CommunityCreate, CommunityUpdate
from app.shared.repository import BaseRepository


class DepartmentRepository(BaseRepository[Department, DepartmentCreate, DepartmentUpdate]):
    """Repositorio para operaciones sobre departamentos geográficos."""

    def __init__(self, session: AsyncSession):
        super().__init__(Department, session)

    async def get_by_ubigeo(self, ubigeo: str) -> Optional[Department]:
        """Busca un departamento por su código UBIGEO."""
        stmt = select(self.model).where(self.model.ubigeo == ubigeo)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Department]:
        """Busca un departamento por coincidencia exacta de nombre."""
        stmt = select(self.model).where(self.model.name.ilike(name))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class CommunityRepository(BaseRepository[Community, CommunityCreate, CommunityUpdate]):
    """Repositorio para operaciones sobre comunidades vecinales."""

    def __init__(self, session: AsyncSession):
        super().__init__(Community, session)

    async def get_by_district(self, district_id: int) -> Sequence[Community]:
        """Retorna las comunidades pertenecientes a un distrito específico."""
        stmt = select(self.model).where(self.model.district_id == district_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_active(self, skip: int = 0, limit: int = 50) -> Sequence[Community]:
        """Retorna comunidades con estado activo."""
        stmt = (
            select(self.model)
            .where(self.model.status == "active")
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()


class MapRepository:
    """Repositorio especializado en consultar puntos geoespaciales para el mapa."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_services_markers(self) -> Sequence[dict]:
        """Obtiene servicios activos con datos de su proveedor y coordenadas."""
        from app.modules.commerce.models import Service, ServiceCategory
        from app.modules.users.models import Profile, UserAddress
        from app.modules.geo.models import Address

        stmt = (
            select(
                Service,
                Profile,
                ServiceCategory,
                Address
            )
            .join(Profile, Service.provider_id == Profile.id)
            .outerjoin(ServiceCategory, Service.category_id == ServiceCategory.id)
            .outerjoin(UserAddress, (UserAddress.user_id == Profile.id) & (UserAddress.is_primary == True))
            .outerjoin(Address, UserAddress.address_id == Address.id)
            .where(Service.status == "active")
        )
        result = await self.session.execute(stmt)
        rows = result.all()

        markers = []
        base_lat = -12.046374
        base_lng = -77.042793

        for idx, (srv, prof, cat, addr) in enumerate(rows):
            lat = float(addr.latitude) if (addr and addr.latitude) else (base_lat + (idx % 7) * 0.0018 - 0.005)
            lng = float(addr.longitude) if (addr and addr.longitude) else (base_lng + (idx % 5) * 0.0022 - 0.004)
            addr_ref = (
                f"{addr.street_address or ''} {addr.lot_number or ''}".strip()
                if addr else "Zona Vecinal Comunitaria"
            )

            markers.append({
                "id": srv.id,
                "title": srv.title,
                "description": srv.description,
                "price": float(srv.price) if srv.price is not None else None,
                "category_name": cat.name if cat else "Servicios",
                "category_icon": cat.icon if (cat and cat.icon) else "🔧",
                "provider_id": prof.id,
                "provider_name": prof.full_name,
                "provider_avatar": prof.avatar_url,
                "provider_phone": prof.phone,
                "latitude": round(lat, 6),
                "longitude": round(lng, 6),
                "address_reference": addr_ref or "Zona A - Manzana 2",
                "status": srv.status or "active"
            })
        return markers

    async def get_emergencies_markers(self) -> Sequence[dict]:
        """Obtiene emergencias activas con coordenadas para marcadores en el mapa."""
        from app.modules.emergencies.models import Emergency
        from app.modules.geo.models import Address

        stmt = (
            select(Emergency, Address)
            .outerjoin(Address, Emergency.address_id == Address.id)
            .where(Emergency.status != "resolved")
        )
        result = await self.session.execute(stmt)
        rows = result.all()

        markers = []
        base_lat = -12.045500
        base_lng = -77.041500

        for idx, (emg, addr) in enumerate(rows):
            lat = float(addr.latitude) if (addr and addr.latitude) else (base_lat + (idx % 4) * 0.0012)
            lng = float(addr.longitude) if (addr and addr.longitude) else (base_lng + (idx % 3) * 0.0015)
            addr_ref = (
                f"{addr.street_address or ''} {addr.reference or ''}".strip()
                if addr else "Sector de Emergencia Vecinal"
            )

            markers.append({
                "id": emg.id,
                "title": emg.title,
                "description": emg.description,
                "severity": emg.severity or "high",
                "status": emg.status or "active",
                "latitude": round(lat, 6),
                "longitude": round(lng, 6),
                "address_reference": addr_ref or "Punto de Alerta Comunitaria",
                "alert_type_name": emg.emergency_type or "Emergencia",
                "created_at": emg.created_at
            })
        return markers
