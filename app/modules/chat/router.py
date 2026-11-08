"""Rutas de API v1 para el módulo de chat comunitario y mensajería vecinal."""
import uuid
from typing import List
from fastapi import APIRouter, Depends, status

from app.core.security import CurrentUser, get_current_user
from app.modules.chat.dependencies import get_chat_service
from app.modules.chat.schemas import (
    ChatMessageCreate,
    ChatMessageResponse,
    ConversationCreate,
    ConversationDetailResponse,
    ConversationListItem,
)
from app.modules.chat.service import ChatService

router = APIRouter(prefix="/chats", tags=["Chat Comunitario y Mensajería"])


@router.get(
    "",
    response_model=List[ConversationListItem],
    summary="Listar mis conversaciones y chats comunitarios",
)
async def list_chats(
    current_user: CurrentUser = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
):
    """Retorna todas las conversaciones activas del usuario con su último mensaje."""
    return await service.list_conversations(current_user.id)


@router.post(
    "",
    response_model=ConversationDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Iniciar o abrir una conversación con un vecino",
)
async def create_chat(
    data: ConversationCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
):
    """Inicia una conversación directa entre dos vecinos (o recupera la existente si ya chatearon)."""
    return await service.get_or_create_conversation(current_user.id, data)


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetailResponse,
    summary="Obtener detalle de la conversación con historial completo",
)
async def get_chat_detail(
    conversation_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
):
    """Retorna el historial completo de mensajes para no perder el contexto al salir del chat."""
    return await service.get_conversation_detail(conversation_id, current_user.id)


@router.get(
    "/{conversation_id}/messages",
    response_model=List[ChatMessageResponse],
    summary="Listar mensajes de una conversación",
)
async def list_messages(
    conversation_id: uuid.UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
):
    """Consulta la lista de mensajes persistidos de esta conversación."""
    detail = await service.get_conversation_detail(conversation_id, current_user.id)
    return detail.messages


@router.post(
    "/{conversation_id}/messages",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enviar mensaje a la conversación",
)
async def send_message(
    conversation_id: uuid.UUID,
    data: ChatMessageCreate,
    current_user: CurrentUser = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
):
    """Persiste y envía un mensaje al chat comunitario."""
    return await service.send_message(
        conversation_id=conversation_id,
        sender_id=current_user.id,
        data=data,
    )
