"""Lógica de negocio y servicios para el módulo de emergencias de VeciRed IA."""
import math
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundException, ValidationException, VeciRedException
from app.modules.emergencies.models import Emergency, EmergencyNeed
from app.modules.emergencies.repository import EmergencyRepository
from app.modules.emergencies.schemas import (
    VolunteerResponse,
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

    async def list_active_emergencies(
        self,
        community_id: Optional[uuid.UUID] = None,
        limit: int = 50,
    ) -> List[EmergencyListItemResponse]:
        """Obtiene todas las emergencias activas de la comunidad."""
        items = await self.repository.list_active_emergencies(community_id=community_id, limit=limit)
        return [EmergencyListItemResponse(**item) for item in items]

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

        addr = await self.repository.get_address_by_id(emg.address_id)
        lat = float(addr.latitude) if addr and addr.latitude is not None else None
        lng = float(addr.longitude) if addr and addr.longitude is not None else None
        loc_str = addr.street_address if addr else None

        # Sala de coordinación de chat asociada a la emergencia
        from app.modules.chat.models import ChatConversation
        conv_stmt = select(ChatConversation.id).where(ChatConversation.emergency_id == emergency_id)
        conv_res = await self.session.execute(conv_stmt)
        conv_id = conv_res.scalar_one_or_none()

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
            image_url=emg.image_url,
            latitude=lat,
            longitude=lng,
            location=loc_str,
            conversation_id=conv_id,
            can_access_chat=bool(conv_id),
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
            image_url=data.image_url,
            latitude=data.latitude,
            longitude=data.longitude,
            location=data.location,
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

        # Crear sala grupal de coordinación asociada a la emergencia en chat
        try:
            from app.modules.chat.repository import ChatRepository
            chat_repo = ChatRepository(self.session)
            await chat_repo.create_emergency_coordination_chat(
                emergency_id=emg.id,
                reporter_id=user_id,
                community_id=community_id,
                title=f"🚨 Coordinación: {emg.title}",
            )
        except Exception:
            pass

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

        # Si se resuelve o cierra la emergencia, cerrar la sala grupal de chat
        if status_update.status in ["atendida", "cerrada"]:
            try:
                from app.modules.chat.repository import ChatRepository
                chat_repo = ChatRepository(self.session)
                await chat_repo.close_emergency_chat(emergency_id)
            except Exception:
                pass

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

    
    async def delete_emergency(self, emergency_id: uuid.UUID, user_id: uuid.UUID) -> dict:
        """Elimina la emergencia si el usuario es quien la reportó o dev."""
        emg = await self.repository.get_emergency_by_id(emergency_id)
        if not emg:
            raise EntityNotFoundException("Emergencia", emergency_id)

        dev_uid = uuid.UUID("a0000000-0000-0000-0000-000000000001")
        if emg.reported_by != user_id and user_id != dev_uid:
            raise ValidationException("Solo el vecino que reportó la alerta puede eliminarla.")

        await self.repository.delete_emergency(emergency_id)
        return {"success": True, "message": "Alerta eliminada correctamente."}

    async def get_emergency_volunteers(self, emergency_id: Optional[uuid.UUID] = None) -> List[VolunteerResponse]:
        """Retorna todos los brigadistas registrados persistentes para esta emergencia."""
        db_volunteers = await self.repository.list_volunteers(emergency_id)
        return [VolunteerResponse(**v) for v in db_volunteers]

    async def register_volunteer(
        self,
        emergency_id: Optional[uuid.UUID],
        user_id: uuid.UUID,
        data: VolunteerRegister,
    ) -> List[VolunteerResponse]:
        """Registra a un vecino real en la brigada de guardia con distancia en metros."""
        # Obtener datos del perfil del usuario si no fueron enviados
        from app.modules.users.models import Profile
        stmt = select(Profile).where(Profile.id == user_id)
        res = await self.session.execute(stmt)
        profile = res.scalar_one_or_none()
        
        vol_name = data.name or (profile.full_name if profile else "Vecino Solidario")
        vol_skill = data.skill or (profile.skill if (profile and profile.skill) else "Apoyo Comunitario")
        vol_avatar = data.avatar or (profile.avatar_url if (profile and profile.avatar_url and len(profile.avatar_url) <= 10) else "👤")
        dist = data.distance_m if data.distance_m is not None else 45

        # Guardar en base de datos
        await self.repository.add_volunteer(
            emergency_id=emergency_id,
            user_id=user_id,
            name=vol_name,
            skill=vol_skill,
            avatar=vol_avatar,
            distance_m=dist,
            status=data.status or "En camino"
        )

        # Incorporar automáticamente al brigadista en la sala grupal de chat de la emergencia
        if emergency_id:
            try:
                from app.modules.chat.repository import ChatRepository
                chat_repo = ChatRepository(self.session)
                conv = await chat_repo.get_conversation_by_emergency_id(emergency_id)
                if conv:
                    part, freshly_added = await chat_repo.add_or_reactivate_participant(
                        conversation_id=conv.id,
                        user_id=user_id,
                        role="brigadista",
                    )
                    if freshly_added:
                        await chat_repo.create_message(
                            conversation_id=conv.id,
                            sender_id=user_id,
                            text=f"🤝 {vol_name} se ha unido a la brigada de guardia vecinal.",
                        )
            except Exception:
                pass
        
        return await self.get_emergency_volunteers(emergency_id)


    async def list_community_reports(self, emergency_id: uuid.UUID) -> List[Dict[str, Any]]:
        """Obtiene la lista de evidencias fotográficas y comentarios de la comunidad para la alerta."""
        return await self.repository.list_community_reports(emergency_id)

    async def create_community_report(
        self,
        emergency_id: uuid.UUID,
        user_id: Optional[uuid.UUID],
        author_name: str,
        author_avatar: Optional[str],
        message: str,
        image_url: Optional[str],
        distance_m: Optional[int],
        role_badge: Optional[str]
    ) -> Dict[str, Any]:
        """Registra un nuevo reporte fotográfico o situacional de la brigada."""
        return await self.repository.add_community_report(
            emergency_id=emergency_id,
            user_id=user_id,
            author_name=author_name,
            author_avatar=author_avatar,
            message=message,
            image_url=image_url,
            distance_m=distance_m,
            role_badge=role_badge
        )

    async def delete_community_report(self, report_id: uuid.UUID) -> bool:
        return await self.repository.delete_community_report(report_id)

    async def update_community_report(
        self,
        report_id: uuid.UUID,
        message: Optional[str],
        image_url: Optional[str]
    ) -> Dict[str, Any]:
        res = await self.repository.update_community_report(report_id, message, image_url)
        if not res:
            raise EntityNotFoundException("Reporte de Emergencia", report_id)
        return res
