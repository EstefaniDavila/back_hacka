"""Modelos SQLAlchemy 2.0 para el módulo solidarity de VeciRed IA."""
import uuid
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, ForeignKey, Integer,
    Numeric, SmallInteger, String, Text, UUID, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class SolidarityPost(Base):
    """Modelo de persistencia para la tabla `solidarity_posts`."""
    __tablename__ = "solidarity_posts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('profiles.id'), nullable=False)
    community_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('communities.id'), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    post_type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class SolidarityResponse(Base):
    """Modelo de persistencia para la tabla `solidarity_responses`."""
    __tablename__ = "solidarity_responses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    post_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('solidarity_posts.id'), nullable=False)
    responder_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('profiles.id'), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    handshake_qr_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    return_due_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

