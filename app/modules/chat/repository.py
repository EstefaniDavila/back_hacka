"""Repositorio asíncrono para el módulo de chat comunitario de VeciRed IA."""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chat.models import ChatConversation, ChatMessage, ChatParticipant
from app.modules.geo.models import Community
from app.modules.users.models import Profile


class ChatRepository:
    """Acceso a datos para conversaciones, mensajes y participantes de chat."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_conversation_by_id(self, conversation_id: uuid.UUID) -> Optional[ChatConversation]:
        stmt = select(ChatConversation).where(ChatConversation.id == conversation_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_conversation_by_emergency_id(self, emergency_id: uuid.UUID) -> Optional[ChatConversation]:
        """Obtiene la sala grupal de chat vinculada a una emergencia específica."""
        stmt = select(ChatConversation).where(ChatConversation.emergency_id == emergency_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def create_emergency_coordination_chat(
        self,
        emergency_id: uuid.UUID,
        reporter_id: uuid.UUID,
        community_id: Optional[uuid.UUID] = None,
        title: Optional[str] = None,
    ) -> ChatConversation:
        """Crea o recupera la sala grupal de coordinación asociada a una emergencia."""
        existing = await self.get_conversation_by_emergency_id(emergency_id)
        if existing:
            return existing

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        conv = ChatConversation(
            id=uuid.uuid4(),
            community_id=community_id,
            title=title or "🚨 Coordinación de Emergencia",
            is_group=True,
            emergency_id=emergency_id,
            initiator_id=reporter_id,
            status="active",
            created_at=now,
            updated_at=now,
        )
        self.session.add(conv)
        await self.session.flush()

        # Agregar al reportante como administrador de la sala
        admin_part = ChatParticipant(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            user_id=reporter_id,
            role="admin",
            is_active=True,
            joined_at=now,
        )
        self.session.add(admin_part)
        await self.session.flush()

        # Mensaje de sistema inicial
        system_msg = ChatMessage(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            sender_id=reporter_id,
            text="🚨 Sala de coordinación activada para esta emergencia. El reporte fue registrado por el vecino administrador. Los brigadistas inscritos se unirán aquí.",
            created_at=now,
        )
        self.session.add(system_msg)
        await self.session.flush()
        await self.session.refresh(conv)
        return conv

    async def add_or_reactivate_participant(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        role: str = "brigadista",
    ) -> Tuple[ChatParticipant, bool]:
        """Incorpora o reactiva un brigadista en la sala grupal, evitando duplicados."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        stmt = select(ChatParticipant).where(
            ChatParticipant.conversation_id == conversation_id,
            ChatParticipant.user_id == user_id,
        )
        res = await self.session.execute(stmt)
        existing = res.scalar_one_or_none()

        if existing:
            if not existing.is_active:
                existing.is_active = True
                existing.left_at = None
                existing.role = role
                await self.session.flush()
                return existing, True
            return existing, False

        new_part = ChatParticipant(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            user_id=user_id,
            role=role,
            is_active=True,
            joined_at=now,
        )
        self.session.add(new_part)
        await self.session.flush()
        return new_part, True

    async def deactivate_participant(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Marca al participante como inactivo al retirarse de la brigada, preservando su historial."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        stmt = select(ChatParticipant).where(
            ChatParticipant.conversation_id == conversation_id,
            ChatParticipant.user_id == user_id,
        )
        res = await self.session.execute(stmt)
        part = res.scalar_one_or_none()
        if part:
            part.is_active = False
            part.left_at = now
            await self.session.flush()
            return True
        return False

    async def close_emergency_chat(self, emergency_id: uuid.UUID) -> Optional[ChatConversation]:
        """Cierra la sala grupal de la emergencia y publica mensaje de sistema."""
        conv = await self.get_conversation_by_emergency_id(emergency_id)
        if not conv:
            return None

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        conv.status = "closed"
        conv.updated_at = now

        # Mensaje de sistema de cierre
        close_msg = ChatMessage(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            sender_id=conv.initiator_id,
            text="🏁 La emergencia ha sido atendida y la coordinación ha finalizado. La sala se encuentra cerrada (modo solo lectura).",
            created_at=now,
        )
        self.session.add(close_msg)
        await self.session.flush()
        await self.session.refresh(conv)
        return conv

    async def list_participants(self, conversation_id: uuid.UUID) -> List[Dict[str, Any]]:
        """Lista los participantes de una sala con nombre, avatar y rol."""
        stmt = (
            select(
                ChatParticipant.user_id,
                Profile.full_name,
                Profile.avatar_url,
                ChatParticipant.role,
                ChatParticipant.is_active,
                ChatParticipant.joined_at,
            )
            .join(Profile, Profile.id == ChatParticipant.user_id)
            .where(ChatParticipant.conversation_id == conversation_id)
            .order_by(ChatParticipant.joined_at.asc())
        )
        res = await self.session.execute(stmt)
        items = []
        for row in res.fetchall():
            items.append({
                "user_id": row[0],
                "name": row[1] or "Vecino",
                "avatar": row[2],
                "role": row[3] or "member",
                "is_active": row[4],
                "joined_at": row[5],
            })
        return items

    async def list_user_conversations(self, user_id: uuid.UUID) -> List[Dict[str, Any]]:
        """Lista las conversaciones donde el usuario participa, con el último mensaje."""
        from app.modules.commerce.models import Service

        # Subconsulta para conversaciones del usuario
        user_convs_subq = (
            select(ChatParticipant.conversation_id)
            .where(ChatParticipant.user_id == user_id)
            .subquery()
        )

        stmt = (
            select(ChatConversation)
            .where(ChatConversation.id.in_(select(user_convs_subq)))
            .order_by(desc(ChatConversation.updated_at))
        )
        res = await self.session.execute(stmt)
        convs = res.scalars().all()

        results = []
        for conv in convs:
            # Obtener el otro participante si es chat 1-a-1
            other_part_stmt = (
                select(Profile)
                .join(ChatParticipant, ChatParticipant.user_id == Profile.id)
                .where(
                    ChatParticipant.conversation_id == conv.id,
                    ChatParticipant.user_id != user_id,
                )
                .limit(1)
            )
            other_part_res = await self.session.execute(other_part_stmt)
            other_user = other_part_res.scalar_one_or_none()

            # Servicio asociado si existe
            svc = None
            if conv.service_id:
                svc = await self.session.get(Service, conv.service_id)

            # Emergencia asociada si existe
            emg = None
            if conv.emergency_id:
                from app.modules.emergencies.models import Emergency
                emg = await self.session.get(Emergency, conv.emergency_id)

            # Contar participantes activos
            part_count_stmt = (
                select(func.count(ChatParticipant.id))
                .where(
                    ChatParticipant.conversation_id == conv.id,
                    ChatParticipant.is_active.is_(True),
                )
            )
            part_count_res = await self.session.execute(part_count_stmt)
            part_count = part_count_res.scalar() or 2

            # Último mensaje
            last_msg_stmt = (
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conv.id)
                .order_by(desc(ChatMessage.created_at))
                .limit(1)
            )
            last_msg_res = await self.session.execute(last_msg_stmt)
            last_msg = last_msg_res.scalar_one_or_none()

            is_emergency = bool(conv.emergency_id)
            is_admin = bool(conv.initiator_id == user_id)
            if is_emergency:
                display_title = conv.title or (f"🚨 Coordinación: {emg.title}" if emg else "🚨 Coordinación de Emergencia")
            else:
                display_title = (other_user.full_name if other_user and other_user.full_name else conv.title) or "Chat Comunitario"

            is_provider = (svc and svc.provider_id == user_id)
            my_role = "provider" if is_provider else ("client" if svc else None)
            is_completed = (conv.service_status == "completed")

            results.append({
                "id": conv.id,
                "title": display_title,
                "other_user_id": other_user.id if other_user else None,
                "other_user_name": other_user.full_name if other_user else ("Brigada de Coordinación" if is_emergency else "Comunidad Vecinal"),
                "other_user_avatar": other_user.avatar_url if other_user else ("🚨" if is_emergency else None),
                "other_user_phone": other_user.phone if other_user else None,
                "is_group": conv.is_group,
                "emergency_id": conv.emergency_id,
                "emergency_type": emg.emergency_type if emg else None,
                "emergency_status": emg.status if emg else None,
                "status": conv.status or "active",
                "participants_count": part_count,
                "is_admin": is_admin,
                "is_emergency": is_emergency,
                "service_id": conv.service_id,
                "service_title": svc.title if svc else None,
                "service_status": conv.service_status or ("contacted" if conv.service_id else None),
                "initiator_id": conv.initiator_id,
                "client_confirmed_at": conv.client_confirmed_at,
                "provider_confirmed_at": conv.provider_confirmed_at,
                "is_service_completed": is_completed,
                "can_review": (is_completed and my_role == "client"),
                "my_role": my_role,
                "last_message": last_msg.text if last_msg else "Conversación iniciada",
                "last_message_time": last_msg.created_at.strftime("%H:%M") if last_msg and last_msg.created_at else "Ahora",
                "unread_count": 0,
                "updated_at": conv.updated_at,
            })

        return results

    async def get_or_create_direct_chat(
        self,
        user1_id: uuid.UUID,
        user2_id: uuid.UUID,
        community_id: Optional[uuid.UUID] = None,
        title: Optional[str] = None,
        service_id: Optional[uuid.UUID] = None,
        initiator_id: Optional[uuid.UUID] = None,
    ) -> ChatConversation:
        """Busca una conversación existente entre dos vecinos para un servicio (o general) o crea una nueva."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Buscar si ya existe una conversación 1-a-1 entre ambos para este servicio específico (o chat general)
        stmt = (
            select(ChatConversation.id)
            .join(ChatParticipant, ChatParticipant.conversation_id == ChatConversation.id)
            .where(
                ChatConversation.is_group.is_(False),
                ChatConversation.service_id == service_id if service_id else ChatConversation.service_id.is_(None),
                ChatParticipant.user_id.in_([user1_id, user2_id]),
            )
            .group_by(ChatConversation.id)
            .having(func.count(ChatParticipant.user_id) == 2)
        )
        res = await self.session.execute(stmt)
        existing_id = res.scalar_one_or_none()
        if existing_id:
            conv = await self.get_conversation_by_id(existing_id)
            if conv:
                return conv

        # Si no existe, crear conversación y participantes
        conv = ChatConversation(
            id=uuid.uuid4(),
            community_id=community_id,
            title=title,
            is_group=False,
            service_id=service_id,
            initiator_id=initiator_id or user1_id,
            service_status="contacted" if service_id else None,
            created_at=now,
            updated_at=now,
        )
        self.session.add(conv)
        await self.session.flush()

        p1 = ChatParticipant(id=uuid.uuid4(), conversation_id=conv.id, user_id=user1_id, joined_at=now)
        p2 = ChatParticipant(id=uuid.uuid4(), conversation_id=conv.id, user_id=user2_id, joined_at=now)
        self.session.add_all([p1, p2])
        await self.session.flush()
        await self.session.refresh(conv)
        return conv

    async def get_or_create_community_general_chat(
        self,
        community_id: uuid.UUID,
    ) -> ChatConversation:
        """Obtiene o crea la sala de chat general comunitaria de la zona."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        stmt = (
            select(ChatConversation)
            .where(
                ChatConversation.community_id == community_id,
                ChatConversation.is_group.is_(True),
                ChatConversation.title == "Coordinación Vecinal Comunitaria",
            )
            .limit(1)
        )
        res = await self.session.execute(stmt)
        conv = res.scalar_one_or_none()
        if conv:
            return conv

        conv = ChatConversation(
            id=uuid.uuid4(),
            community_id=community_id,
            title="Coordinación Vecinal Comunitaria",
            is_group=True,
            created_at=now,
            updated_at=now,
        )
        self.session.add(conv)
        await self.session.flush()
        await self.session.refresh(conv)
        return conv

    async def list_messages(
        self,
        conversation_id: uuid.UUID,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Obtiene el historial de mensajes ordenados cronológicamente con rol del remitente."""
        stmt = (
            select(
                ChatMessage.id,
                ChatMessage.conversation_id,
                ChatMessage.sender_id,
                Profile.full_name.label("sender_name"),
                Profile.avatar_url.label("sender_avatar"),
                ChatParticipant.role.label("sender_role"),
                ChatMessage.text,
                ChatMessage.created_at,
            )
            .outerjoin(Profile, Profile.id == ChatMessage.sender_id)
            .outerjoin(
                ChatParticipant,
                (ChatParticipant.conversation_id == ChatMessage.conversation_id)
                & (ChatParticipant.user_id == ChatMessage.sender_id)
            )
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.asc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        items = []
        for row in res.mappings().all():
            row_dict = dict(row)
            if not row_dict.get("sender_name"):
                row_dict["sender_name"] = "Vecino"
            role = row_dict.get("sender_role")
            if role == "admin":
                row_dict["sender_role"] = "Reportante / Admin"
            elif role == "brigadista":
                row_dict["sender_role"] = "Brigadista"
            else:
                row_dict["sender_role"] = "Vecino"
            row_dict["time"] = row_dict["created_at"].strftime("%H:%M") if row_dict.get("created_at") else "Ahora"
            items.append(row_dict)
        return items

    async def create_message(
        self,
        conversation_id: uuid.UUID,
        sender_id: uuid.UUID,
        text: str,
    ) -> ChatMessage:
        """Guarda un mensaje en la base de datos y actualiza la fecha de la conversación."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        msg = ChatMessage(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            sender_id=sender_id,
            text=text.strip(),
            created_at=now,
        )
        self.session.add(msg)

        # Actualizar updated_at de la conversación
        stmt = (
            update(ChatConversation)
            .where(ChatConversation.id == conversation_id)
            .values(updated_at=now)
        )
        await self.session.execute(stmt)
        await self.session.flush()
        await self.session.refresh(msg)
        return msg
