"""Esquemas Pydantic v2 para el módulo de chat comunitario."""
import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChatMessageCreate(BaseModel):
    """Payload para enviar un nuevo mensaje en el chat."""
    text: Optional[str] = Field(None, max_length=2000, description="Contenido del mensaje")
    content: Optional[str] = Field(None, max_length=2000, description="Contenido del mensaje alternativo")

    @model_validator(mode="after")
    def validate_content(self):
        if not self.text and not self.content:
            raise ValueError("El mensaje no puede estar vacío.")
        if not self.text:
            self.text = self.content
        return self


class ChatMessageResponse(BaseModel):
    """Ficha descriptiva de un mensaje de chat."""
    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_id: uuid.UUID
    sender_name: str
    sender_avatar: Optional[str] = None
    text: Optional[str] = "Mensaje"
    content: Optional[str] = None
    time: Optional[str] = "Ahora"
    created_at: Optional[datetime] = None
    is_me: bool = False
    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def sync_content_and_text(self):
        if self.content and not self.text:
            self.text = self.content
        elif self.text and not self.content:
            self.content = self.text
        return self


class ConversationCreate(BaseModel):
    """Payload para iniciar una conversación con un vecino o grupo comunitario."""
    recipient_id: Optional[uuid.UUID] = Field(None, description="ID del vecino destinatario (para chat 1 a 1)")
    title: Optional[str] = Field(None, max_length=150, description="Título o tema del chat (ej: Servicio Eléctrico)")
    initial_message: Optional[str] = Field(None, max_length=1000, description="Mensaje inicial opcional")


class ConversationListItem(BaseModel):
    """Ficha resumida de una conversación para la bandeja de chats."""
    id: uuid.UUID
    title: str
    other_user_id: Optional[uuid.UUID] = None
    other_user_name: Optional[str] = None
    other_user_avatar: Optional[str] = None
    other_user_phone: Optional[str] = None
    is_group: bool = False
    last_message: Optional[str] = None
    last_message_time: Optional[str] = None
    unread_count: int = 0
    updated_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)


class ConversationDetailResponse(ConversationListItem):
    messages: List[ChatMessageResponse] = Field(default_factory=list)
