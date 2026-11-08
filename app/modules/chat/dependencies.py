"""Inyección de dependencias para el módulo de chat comunitario."""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.dependencies import get_db_session
from app.modules.chat.service import ChatService


async def get_chat_service(
    session: AsyncSession = Depends(get_db_session),
) -> ChatService:
    """Provee la instancia del servicio de chat con sesión inyectada."""
    return ChatService(session)
