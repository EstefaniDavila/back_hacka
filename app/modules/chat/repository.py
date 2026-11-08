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

    async def list_user_conversations(self, user_id: uuid.UUID) -> List[Dict[str, Any]]:
        """Lista las conversaciones donde el usuario participa, con el último mensaje."""
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

            # Último mensaje
            last_msg_stmt = (
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conv.id)
                .order_by(desc(ChatMessage.created_at))
                .limit(1)
            )
            last_msg_res = await self.session.execute(last_msg_stmt)
            last_msg = last_msg_res.scalar_one_or_none()

            display_title = (other_user.full_name if other_user and other_user.full_name else conv.title) or "Chat Comunitario"

            results.append({
                "id": conv.id,
                "title": display_title,
                "other_user_id": other_user.id if other_user else None,
                "other_user_name": other_user.full_name if other_user else "Comunidad Vecinal",
                "other_user_avatar": other_user.avatar_url if other_user else None,
                "other_user_phone": other_user.phone if other_user else None,
                "is_group": conv.is_group,
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
    ) -> ChatConversation:
        """Busca una conversación existente entre dos vecinos o crea una nueva."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Buscar si ya existe una conversación 1-a-1 entre ambos
        stmt = (
            select(ChatConversation.id)
            .join(ChatParticipant, ChatParticipant.conversation_id == ChatConversation.id)
            .where(
                ChatConversation.is_group.is_(False),
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
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Obtiene el historial de mensajes ordenados cronológicamente."""
        stmt = (
            select(
                ChatMessage.id,
                ChatMessage.conversation_id,
                ChatMessage.sender_id,
                Profile.full_name.label("sender_name"),
                Profile.avatar_url.label("sender_avatar"),
                ChatMessage.text,
                ChatMessage.created_at,
            )
            .outerjoin(Profile, Profile.id == ChatMessage.sender_id)
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
