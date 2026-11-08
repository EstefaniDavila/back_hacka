"""Módulo de chat comunitario para VeciRed IA."""
from .models import ChatConversation, ChatMessage, ChatParticipant
from .router import router

__all__ = ["ChatConversation", "ChatParticipant", "ChatMessage", "router"]
