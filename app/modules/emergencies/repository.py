"""Repositorio asíncrono para el módulo de emergencias de VeciRed IA."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.emergencies.models import (
    EmergencyVolunteer,
    Emergency,
    EmergencyAlert,
    EmergencyContribution,
    EmergencyNeed,
)
from app.modules.geo.models import Community
from app.modules.users.models import Profile


class EmergencyRepository:
    """Acceso a datos para emergencias comunitarias, necesidades y voluntariado."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_first_active_community_id(self) -> Optional[uuid.UUID]:
        """Obtiene la primera comunidad activa."""
        stmt = select(Community.id).where(Community.status == "active").limit(1)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    # ------------------------------------------------------------------
    # GESTIÓN Y LISTADO DE EMERGENCIAS
    # ------------------------------------------------------------------
    async def list_emergencies(
        self,
        community_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Lista emergencias comunitarias con contadores de necesidades."""
        needs_count_subq = (
            select(
                EmergencyNeed.emergency_id,
                func.count(EmergencyNeed.id).label("needs_count"),
            )
            .group_by(EmergencyNeed.emergency_id)
            .subquery()
        )

        stmt = (
            select(
                Emergency.id,
                Emergency.reported_by,
                Profile.full_name.label("reporter_name"),
                Profile.avatar_url.label("reporter_avatar"),
                Emergency.community_id,
                Community.name.label("community_name"),
                Emergency.emergency_type,
                Emergency.title,
                Emergency.description,
                Emergency.severity,
                Emergency.status,
                Emergency.occurred_at,
                Emergency.created_at,
                func.coalesce(needs_count_subq.c.needs_count, 0).label("needs_count"),
            )
            .outerjoin(Profile, Profile.id == Emergency.reported_by)
            .outerjoin(Community, Community.id == Emergency.community_id)
            .outerjoin(needs_count_subq, needs_count_subq.c.emergency_id == Emergency.id)
        )

        count_stmt = (
            select(func.count(Emergency.id))
            .outerjoin(Profile, Profile.id == Emergency.reported_by)
            .outerjoin(Community, Community.id == Emergency.community_id)
        )

        conditions = []
        if community_id:
            conditions.append(Emergency.community_id == community_id)
        if status:
            conditions.append(Emergency.status == status)
        if severity:
            conditions.append(Emergency.severity == severity)

        if conditions:
            stmt = stmt.where(*conditions)
            count_stmt = count_stmt.where(*conditions)

        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar() or 0

        stmt = stmt.order_by(desc(Emergency.created_at)).offset(skip).limit(limit)
        results = await self.session.execute(stmt)

        items = []
        for row in results.mappings().all():
            item_dict = dict(row)
            item_dict["volunteers_count"] = 0
            item_dict["radius_m"] = 500
            items.append(item_dict)

        return items, total

    async def list_active_emergencies(self, community_id: Optional[uuid.UUID] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Retorna todas las emergencias activas de la comunidad en orden cronológico."""
        stmt = (
            select(
                Emergency.id,
                Emergency.reported_by,
                Profile.full_name.label("reporter_name"),
                Profile.avatar_url.label("reporter_avatar"),
                Emergency.community_id,
                Community.name.label("community_name"),
                Emergency.emergency_type,
                Emergency.title,
                Emergency.description,
                Emergency.severity,
                Emergency.status,
                Emergency.occurred_at,
                Emergency.created_at,
            )
            .outerjoin(Profile, Profile.id == Emergency.reported_by)
            .outerjoin(Community, Community.id == Emergency.community_id)
            .where(Emergency.status.in_(["en_atencion", "reportada"]))
        )
        if community_id:
            stmt = stmt.where(Emergency.community_id == community_id)

        stmt = stmt.order_by(
            desc(Emergency.severity == "critical"),
            desc(Emergency.created_at),
        ).limit(limit)

        res = await self.session.execute(stmt)
        items = []
        for row in res.mappings().all():
            d = dict(row)
            if not d.get("reporter_name"):
                d["reporter_name"] = "Vecino de la zona"
            if not d.get("community_name"):
                d["community_name"] = "Zona A"
            d["volunteers_count"] = 0
            d["radius_m"] = 500
            items.append(d)
        return items

    async def get_active_emergency(self, community_id: Optional[uuid.UUID] = None) -> Optional[Dict[str, Any]]:
        """
        Retorna la emergencia activa más prioritaria para el banner de la aplicación.
        Busca estados 'en_atencion' o 'reportada'.
        """
        stmt = (
            select(
                Emergency.id,
                Emergency.reported_by,
                Profile.full_name.label("reporter_name"),
                Profile.avatar_url.label("reporter_avatar"),
                Emergency.community_id,
                Community.name.label("community_name"),
                Emergency.emergency_type,
                Emergency.title,
                Emergency.description,
                Emergency.severity,
                Emergency.status,
                Emergency.occurred_at,
                Emergency.created_at,
            )
            .outerjoin(Profile, Profile.id == Emergency.reported_by)
            .outerjoin(Community, Community.id == Emergency.community_id)
            .where(Emergency.status.in_(["en_atencion", "reportada"]))
        )
        if community_id:
            stmt = stmt.where(Emergency.community_id == community_id)

        stmt = stmt.order_by(
            desc(Emergency.severity == "critical"),
            desc(Emergency.severity == "high"),
            desc(Emergency.created_at),
        ).limit(1)

        res = await self.session.execute(stmt)
        row = res.mappings().one_or_none()
        if not row:
            return None

        result = dict(row)
        if not result.get("reporter_name"):
            result["reporter_name"] = "Vecino de la zona"
        if not result.get("community_name"):
            result["community_name"] = "Zona A"
        result["volunteers_count"] = 4
        result["radius_m"] = 500
        result["needs_count"] = 0
        return result

    async def get_emergency_by_id(self, emergency_id: uuid.UUID) -> Optional[Emergency]:
        """Obtiene la entidad ORM de la emergencia."""
        stmt = select(Emergency).where(Emergency.id == emergency_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def create_emergency(
        self,
        reported_by: uuid.UUID,
        community_id: uuid.UUID,
        emergency_type: str,
        title: str,
        description: Optional[str] = None,
        severity: str = "high",
        address_id: Optional[uuid.UUID] = None,
        alert_radius_m: Optional[int] = 500,
    ) -> Emergency:
        """Crea un nuevo reporte de emergencia comunitaria y genera la alerta barrial."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        emg = Emergency(
            id=uuid.uuid4(),
            reported_by=reported_by,
            community_id=community_id,
            address_id=address_id,
            emergency_type=emergency_type.strip(),
            title=title.strip(),
            description=description.strip() if description else None,
            severity=severity,
            status="reportada",
            occurred_at=now,
            created_at=now,
        )
        self.session.add(emg)
        await self.session.flush()

        # Alerta vinculada
        alert = EmergencyAlert(
            id=uuid.uuid4(),
            emergency_id=emg.id,
            created_by=reported_by,
            alert_radius_m=alert_radius_m or 500,
            message=f"🚨 ALERTA: {title}",
            created_at=now,
        )
        self.session.add(alert)
        await self.session.flush()
        await self.session.refresh(emg)
        return emg

    async def update_status(self, emergency: Emergency, status: str) -> Emergency:
        """Actualiza el estado de atención de la emergencia."""
        emergency.status = status
        self.session.add(emergency)
        await self.session.flush()
        await self.session.refresh(emergency)
        return emergency

    # ------------------------------------------------------------------
    # NECESIDADES DE RECURSOS (AGUA, VÍVERES, FRAZADAS)
    # ------------------------------------------------------------------
    async def create_need(
        self,
        emergency_id: uuid.UUID,
        resource_name: str,
        quantity_required: Decimal,
        unit: str,
    ) -> EmergencyNeed:
        """Registra un nuevo requerimiento de ayuda para la emergencia."""
        need = EmergencyNeed(
            id=uuid.uuid4(),
            emergency_id=emergency_id,
            resource_name=resource_name.strip(),
            quantity_required=quantity_required,
            quantity_committed=Decimal(0),
            quantity_delivered=Decimal(0),
            unit=unit.strip(),
            status="active",
        )
        self.session.add(need)
        await self.session.flush()
        await self.session.refresh(need)
        return need

    async def list_needs_for_emergency(self, emergency_id: uuid.UUID) -> List[EmergencyNeed]:
        """Obtiene la lista de necesidades asociadas a la emergencia."""
        stmt = select(EmergencyNeed).where(EmergencyNeed.emergency_id == emergency_id)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_need_by_id(self, need_id: uuid.UUID) -> Optional[EmergencyNeed]:
        """Obtiene una necesidad de emergencia por su ID."""
        stmt = select(EmergencyNeed).where(EmergencyNeed.id == need_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def contribute_to_need(
        self,
        need: EmergencyNeed,
        contributor_id: uuid.UUID,
        quantity: Decimal,
        collection_point_id: Optional[uuid.UUID] = None,
    ) -> EmergencyContribution:
        """Registra el compromiso de un vecino de donar o llevar recursos."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        contrib = EmergencyContribution(
            id=uuid.uuid4(),
            need_id=need.id,
            contributor_id=contributor_id,
            collection_point_id=collection_point_id,
            quantity=quantity,
            contribution_status="committed",
            committed_at=now,
        )
        self.session.add(contrib)

        # Actualizar cantidad comprometida
        current_committed = need.quantity_committed or Decimal(0)
        need.quantity_committed = current_committed + quantity
        self.session.add(need)

        await self.session.flush()
        await self.session.refresh(contrib)
        return contrib

    async def list_contributions_for_need(self, need_id: uuid.UUID) -> List[Dict[str, Any]]:
        """Lista los aportes y vecinos que están contribuyendo con este recurso."""
        stmt = (
            select(
                EmergencyContribution.id,
                EmergencyContribution.need_id,
                EmergencyContribution.contributor_id,
                Profile.full_name.label("contributor_name"),
                Profile.avatar_url.label("contributor_avatar"),
                EmergencyContribution.quantity,
                EmergencyContribution.contribution_status,
                EmergencyContribution.committed_at,
            )
            .join(Profile, Profile.id == EmergencyContribution.contributor_id)
            .where(EmergencyContribution.need_id == need_id)
            .order_by(desc(EmergencyContribution.committed_at))
        )
        res = await self.session.execute(stmt)
        return [dict(r) for r in res.mappings().all()]

    async def delete_emergency(self, emergency_id: uuid.UUID) -> bool:
        """Elimina una emergencia y sus registros asociados."""
        from sqlalchemy import text
        await self.session.execute(text("DELETE FROM emergency_volunteers WHERE emergency_id = :eid"), {"eid": emergency_id})
        await self.session.execute(text("DELETE FROM emergency_contributions WHERE need_id IN (SELECT id FROM emergency_needs WHERE emergency_id = :eid)"), {"eid": emergency_id})
        await self.session.execute(text("DELETE FROM emergency_needs WHERE emergency_id = :eid"), {"eid": emergency_id})
        await self.session.execute(text("DELETE FROM emergency_alerts WHERE emergency_id = :eid"), {"eid": emergency_id})
        await self.session.execute(text("DELETE FROM collection_points WHERE emergency_id = :eid"), {"eid": emergency_id})
        await self.session.execute(text("DELETE FROM vulnerability_reports WHERE emergency_id = :eid"), {"eid": emergency_id})
        res = await self.session.execute(text("DELETE FROM emergencies WHERE id = :eid"), {"eid": emergency_id})
        await self.session.commit()
        return res.rowcount > 0

    # ------------------------------------------------------------------
    # GESTIÓN DE VOLUNTARIOS Y BRIGADA VECINAL
    # ------------------------------------------------------------------
    async def list_volunteers(self, emergency_id: Optional[uuid.UUID] = None) -> List[Dict[str, Any]]:
        """Lista los voluntarios registrados para una emergencia específica o general."""
        from sqlalchemy import text
        if emergency_id:
            stmt = text("""
                SELECT id, emergency_id, user_id, name, skill, avatar, distance_m, status, created_at
                FROM emergency_volunteers
                WHERE emergency_id = :eid
                ORDER BY created_at DESC
            """)
            res = await self.session.execute(stmt, {"eid": emergency_id})
        else:
            stmt = text("""
                SELECT id, emergency_id, user_id, name, skill, avatar, distance_m, status, created_at
                FROM emergency_volunteers
                ORDER BY created_at DESC
            """)
            res = await self.session.execute(stmt)
        rows = res.fetchall()
        result = []
        for r in rows:
            dist = r[6] or 50
            result.append({
                "id": str(r[0]),
                "emergency_id": str(r[1]) if r[1] else None,
                "user_id": str(r[2]) if r[2] else None,
                "name": r[3],
                "skill": r[4] or "Apoyo Comunitario",
                "avatar": r[5] or "👤",
                "distance": f"{dist}m",
                "distance_m": dist,
                "status": r[7] or "En camino"
            })
        return result

    async def add_volunteer(
        self,
        emergency_id: Optional[uuid.UUID],
        user_id: uuid.UUID,
        name: str,
        skill: Optional[str],
        avatar: Optional[str],
        distance_m: Optional[int],
        status: Optional[str] = "En camino"
    ) -> Dict[str, Any]:
        """Registra o actualiza a un vecino en la brigada de guardia."""
        from sqlalchemy import text
        vol_id = uuid.uuid4()
        dist = distance_m if distance_m is not None else 50
        
        dev_uid = uuid.UUID("a0000000-0000-0000-0000-000000000001")
        clean_name = name.strip() if name else "Vecino Solidario"

        # Eliminar registro previo de este vecino para evitar duplicados dentro de ESTA misma emergencia
        if emergency_id:
            if user_id == dev_uid:
                await self.session.execute(
                    text("DELETE FROM emergency_volunteers WHERE emergency_id = :eid AND LOWER(name) = LOWER(:name)"),
                    {"eid": emergency_id, "name": clean_name}
                )
                assigned_user_id = uuid.uuid5(uuid.NAMESPACE_DNS, clean_name.lower())
            else:
                await self.session.execute(
                    text("DELETE FROM emergency_volunteers WHERE emergency_id = :eid AND (user_id = :uid OR LOWER(name) = LOWER(:name))"),
                    {"eid": emergency_id, "uid": user_id, "name": clean_name}
                )
                assigned_user_id = user_id
        else:
            if user_id == dev_uid:
                await self.session.execute(
                    text("DELETE FROM emergency_volunteers WHERE LOWER(name) = LOWER(:name)"),
                    {"name": clean_name}
                )
                assigned_user_id = uuid.uuid5(uuid.NAMESPACE_DNS, clean_name.lower())
            else:
                await self.session.execute(
                    text("DELETE FROM emergency_volunteers WHERE user_id = :uid OR LOWER(name) = LOWER(:name)"),
                    {"uid": user_id, "name": clean_name}
                )
                assigned_user_id = user_id

        await self.session.execute(
            text("""
                INSERT INTO emergency_volunteers (id, emergency_id, user_id, name, skill, avatar, distance_m, status, created_at)
                VALUES (:id, :eid, :uid, :name, :skill, :avatar, :dist, :status, NOW())
            """),
            {
                "id": vol_id,
                "eid": emergency_id,
                "uid": assigned_user_id,
                "name": name,
                "skill": skill or "Apoyo Comunitario",
                "avatar": avatar or "👤",
                "dist": dist,
                "status": status or "En camino"
            }
        )
        await self.session.commit()
        return {
            "id": str(vol_id),
            "emergency_id": str(emergency_id) if emergency_id else None,
            "user_id": str(user_id),
            "name": name,
            "skill": skill or "Apoyo Comunitario",
            "avatar": avatar or "👤",
            "distance": f"{dist}m",
            "distance_m": dist,
            "status": status or "En camino"
        }
