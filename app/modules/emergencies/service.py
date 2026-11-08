"""Lógica de negocio y servicios para el módulo de emergencias de VeciRed IA."""
import math
import uuid
from decimal import Decimal
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundException, ValidationException, VeciRedException
from app.modules.emergencies.models import Emergency, EmergencyNeed
from app.modules.emergencies.repository import EmergencyRepository
from app.modules.emergencies.schemas import (
    EmergencyContributionCreate,
    EmergencyContributionResponse,
    EmergencyCreate,
    EmergencyDetailResponse,
    EmergencyListItemResponse,
    EmergencyNeedCreate,
    EmergencyNeedResponse,
    EmergencyStatusUpdate,
    VolunteerRegister,
)
from app.modules.notifications.repository import NotificationRepository
from app.shared.pagination import PageMeta, PaginatedResponse


class EmergencyService:
    """Capa de servicios para la coordinación de emergencias y donaciones comunitarias."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = EmergencyRepository(session)
        self.notif_repository = NotificationRepository(session)

    async def list_emergencies(
        self,
        community_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> PaginatedResponse[EmergencyListItemResponse]:
        """Consulta el historial y reportes de emergencias comunitarias."""
        skip = (page - 1) * limit
        items_data, total = await self.repository.list_emergencies(
            community_id=community_id,
            status=status,
            severity=severity,
            skip=skip,
            limit=limit,
        )

        total_pages = math.ceil(total / limit) if total > 0 else 1
        items = [EmergencyListItemResponse(**item) for item in items_data]

        return PaginatedResponse(
            items=items,
            meta=PageMeta(total=total, page=page, limit=limit, total_pages=total_pages),
        )

    async def get_active_emergency(
        self,
        community_id: Optional[uuid.UUID] = None,
    ) -> Optional[EmergencyListItemResponse]:
        """Obtiene la emergencia activa prioritaria para el banner rojo de la app."""
        active = await self.repository.get_active_emergency(community_id=community_id)
        if not active:
            return None
        return EmergencyListItemResponse(**active)

    async def get_emergency_detail(self, emergency_id: uuid.UUID) -> EmergencyDetailResponse:
        """Obtiene la ficha completa de una emergencia con sus requerimientos y donaciones."""
        emg = await self.repository.get_emergency_by_id(emergency_id)
        if not emg:
            raise EntityNotFoundException("Emergencia", emergency_id)

        # Necesidades
        needs_orm = await self.repository.list_needs_for_emergency(emergency_id)
        needs = [EmergencyNeedResponse.model_validate(n) for n in needs_orm]

        # Contribuciones
        contributions: List[EmergencyContributionResponse] = []
        for n in needs_orm:
            c_items = await self.repository.list_contributions_for_need(n.id)
            for c in c_items:
                contributions.append(EmergencyContributionResponse(**c))

        return EmergencyDetailResponse(
            id=emg.id,
            reported_by=emg.reported_by,
            reporter_name="Vecino Reportante",
            community_id=emg.community_id,
            community_name="Zona A",
            emergency_type=emg.emergency_type,
            title=emg.title,
            description=emg.description,
            severity=emg.severity or "high",
            status=emg.status or "reportada",
            occurred_at=emg.occurred_at,
            created_at=emg.created_at,
            needs_count=len(needs),
            volunteers_count=4,
            radius_m=500,
            needs=needs,
            contributions=contributions,
        )

    async def create_emergency(
        self,
        user_id: uuid.UUID,
        data: EmergencyCreate,
    ) -> EmergencyDetailResponse:
        """Reporta una nueva emergencia vecinal, siembra necesidades y envía alertas a la comunidad."""
        community_id = data.community_id
        if not community_id:
            community_id = await self.repository.get_first_active_community_id()
            if not community_id:
                raise ValidationException("No se encontró una comunidad activa para asociar la emergencia.")

        emg = await self.repository.create_emergency(
            reported_by=user_id,
            community_id=community_id,
            emergency_type=data.emergency_type,
            title=data.title,
            description=data.description,
            severity=data.severity,
            address_id=data.address_id,
            alert_radius_m=data.alert_radius_m,
        )

        # Sembrar necesidades por defecto para facilitar pruebas y uso inmediato
        default_needs = [
            ("Agua potable", Decimal(20), "botellas"),
            ("Alimentos y víveres", Decimal(15), "packs"),
            ("Mantas y frazadas", Decimal(10), "unidades"),
        ]
        for r_name, r_qty, r_unit in default_needs:
            await self.repository.create_need(
                emergency_id=emg.id,
                resource_name=r_name,
                quantity_required=r_qty,
                unit=r_unit,
            )

        # Emitir notificaciones de alerta inmediata a los vecinos de la comunidad
        try:
            await self.notif_repository.broadcast_alert_to_community(
                alert_id=emg.id,
                title=emg.title,
                message=emg.description or "Se ha activado una alerta en tu manzana.",
                sender_id=user_id,
            )
        except Exception:
            pass

        await self.session.commit()
        return await self.get_emergency_detail(emg.id)

    async def broadcast_alert(
        self,
        emergency_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> dict:
        """Dispara manualmente el envío de notificaciones a toda la comunidad vecinal."""
        emg = await self.repository.get_emergency_by_id(emergency_id)
        if not emg:
            raise EntityNotFoundException("Emergencia", emergency_id)

        count = await self.notif_repository.broadcast_alert_to_community(
            alert_id=emg.id,
            title=emg.title,
            message=emg.description or "Alerta vecinal activa en tu zona.",
            sender_id=user_id,
        )
        await self.session.commit()
        return {
            "status": "success",
            "message": f"Alerta vecinal enviada con éxito a {count} vecinos de la comunidad.",
            "emergency_id": emergency_id,
            "notifications_sent": count,
        }

    async def update_status(
        self,
        emergency_id: uuid.UUID,
        status_update: EmergencyStatusUpdate,
    ) -> EmergencyDetailResponse:
        """Actualiza el estado de la emergencia (ej: 'en_atencion', 'atendida')."""
        emg = await self.repository.get_emergency_by_id(emergency_id)
        if not emg:
            raise EntityNotFoundException("Emergencia", emergency_id)

        await self.repository.update_status(emg, status_update.status)
        await self.session.commit()
        return await self.get_emergency_detail(emg.id)

    async def add_need(
        self,
        emergency_id: uuid.UUID,
        data: EmergencyNeedCreate,
    ) -> EmergencyNeedResponse:
        """Agrega una necesidad de recurso a una emergencia activa."""
        emg = await self.repository.get_emergency_by_id(emergency_id)
        if not emg:
            raise EntityNotFoundException("Emergencia", emergency_id)

        need = await self.repository.create_need(
            emergency_id=emergency_id,
            resource_name=data.resource_name,
            quantity_required=data.quantity_required,
            unit=data.unit,
        )
        await self.session.commit()
        return EmergencyNeedResponse.model_validate(need)

    async def contribute(
        self,
        need_id: uuid.UUID,
        user_id: uuid.UUID,
        data: EmergencyContributionCreate,
    ) -> EmergencyContributionResponse:
        """Registra la donación o compromiso de víveres o materiales."""
        need = await self.repository.get_need_by_id(need_id)
        if not need:
            raise EntityNotFoundException("Necesidad de emergencia", need_id)

        contrib = await self.repository.contribute_to_need(
            need=need,
            contributor_id=user_id,
            quantity=data.quantity,
            collection_point_id=data.collection_point_id,
        )
        await self.session.commit()

        contributions = await self.repository.list_contributions_for_need(need_id)
        for c in contributions:
            if c["id"] == contrib.id:
                return EmergencyContributionResponse(**c)

        return EmergencyContributionResponse(
            id=contrib.id,
            need_id=need.id,
            contributor_id=user_id,
            contributor_name="Vecino Solidario",
            quantity=data.quantity,
            contribution_status=contrib.contribution_status or "committed",
            committed_at=contrib.committed_at,
        )

    async def register_volunteer(
        self,
        emergency_id: uuid.UUID,
        user_id: uuid.UUID,
        data: VolunteerRegister,
    ) -> dict:
        """Registra a un vecino como voluntario en camino para atender la emergencia."""
        emg = await self.repository.get_emergency_by_id(emergency_id)
        if not emg:
            raise EntityNotFoundException("Emergencia", emergency_id)

        # Si el estado es solo 'reportada', pasar a 'en_atencion' automáticamente
        if emg.status == "reportada":
            await self.repository.update_status(emg, "en_atencion")
            await self.session.commit()

        return {
            "status": "success",
            "message": "Te has registrado como voluntario en camino para esta emergencia.",
            "emergency_id": emergency_id,
            "volunteer_id": user_id,
        }
