"""Lógica de negocio y servicios para el módulo de chat comunitario."""
import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundException, ValidationException
from app.modules.chat.repository import ChatRepository
from app.modules.chat.schemas import (
    ChatMessageCreate,
    ChatMessageResponse,
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListItem,
)
from app.modules.commerce.repository import CommerceRepository


class ChatService:
    """Capa de servicios para conversaciones y mensajes comunitarios."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = ChatRepository(session)
        self.commerce_repo = CommerceRepository(session)

    async def list_conversations(self, user_id: uuid.UUID) -> List[ConversationListItem]:
        """Obtiene todas las conversaciones activas del usuario."""
        items = await self.repository.list_user_conversations(user_id)
        return [ConversationListItem(**item) for item in items]

    async def get_or_create_conversation(
        self,
        user_id: uuid.UUID,
        data: ConversationCreate,
    ) -> ConversationDetailResponse:
        """Inicia una conversación directa con un vecino o retorna la existente."""
        if not data.recipient_id:
            raise ValidationException("Se requiere el ID del vecino destinatario para iniciar el chat.")

        if user_id == data.recipient_id:
            raise ValidationException("No puedes iniciar una conversación contigo mismo.")

        community_id = await self.commerce_repo.get_first_active_community_id()

        conv = await self.repository.get_or_create_direct_chat(
            user1_id=user_id,
            user2_id=data.recipient_id,
            community_id=community_id,
            title=data.title,
        )

        # Si viene un mensaje inicial, guardarlo
        if data.initial_message:
            await self.repository.create_message(
                conversation_id=conv.id,
                sender_id=user_id,
                text=data.initial_message,
            )

        await self.session.commit()
        return await self.get_conversation_detail(conv.id, user_id)

    async def get_conversation_detail(
        self,
        conversation_id: uuid.UUID,
        current_user_id: uuid.UUID,
    ) -> ConversationDetailResponse:
        """Obtiene el historial de mensajes de la conversación."""
        conv = await self.repository.get_conversation_by_id(conversation_id)
        if not conv:
            raise EntityNotFoundException("Conversación de chat", conversation_id)

        raw_messages = await self.repository.list_messages(conversation_id, limit=100)
        messages = [
            ChatMessageResponse(
                id=m["id"],
                conversation_id=m["conversation_id"],
                sender_id=m["sender_id"],
                sender_name=m["sender_name"],
                sender_avatar=m["sender_avatar"],
                text=m["text"],
                time=m["time"],
                created_at=m["created_at"],
                is_me=(m["sender_id"] == current_user_id),
            )
            for m in raw_messages
        ]

        last_msg = messages[-1].text if messages else "Sin mensajes aún"
        last_time = messages[-1].time if messages else "Ahora"

        return ConversationDetailResponse(
            id=conv.id,
            title=conv.title or "Chat Comunitario",
            is_group=conv.is_group,
            last_message=last_msg,
            last_message_time=last_time,
            unread_count=0,
            updated_at=conv.updated_at,
            messages=messages,
        )

    async def send_message(
        self,
        conversation_id: uuid.UUID,
        sender_id: uuid.UUID,
        data: ChatMessageCreate,
    ) -> ChatMessageResponse:
        """Envía y guarda un mensaje en la conversación."""
        conv = await self.repository.get_conversation_by_id(conversation_id)
        if not conv:
            raise EntityNotFoundException("Conversación de chat", conversation_id)

        msg = await self.repository.create_message(
            conversation_id=conversation_id,
            sender_id=sender_id,
            text=data.text,
        )
        await self.session.commit()

        return ChatMessageResponse(
            id=msg.id,
            conversation_id=conversation_id,
            sender_id=sender_id,
            sender_name="Yo",
            text=msg.text,
            time="Ahora",
            created_at=msg.created_at,
            is_me=True,
        )
