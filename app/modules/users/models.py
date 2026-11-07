"""Modelos SQLAlchemy 2.0 para el módulo users de VeciRed IA."""
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

class AuthUser(Base):
    """Referencia a la tabla auth.users de Supabase."""
    __tablename__ = "users"
    __table_args__ = {"schema": "auth"}
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)

class Profile(Base):
    """Modelo de persistencia para la tabla `profiles`."""
    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('auth.users.id'), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    birth_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    account_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    font_scale_preference: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    solidarity_helped_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    solidarity_received_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class IdentityVerification(Base):
    """Modelo de persistencia para la tabla `identity_verifications`."""
    __tablename__ = "identity_verifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('profiles.id'), nullable=False)
    document_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    document_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    document_last4: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    identity_provider: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    identity_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class UserAddress(Base):
    """Modelo de persistencia para la tabla `user_addresses`."""
    __tablename__ = "user_addresses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('profiles.id'), nullable=False)
    address_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('addresses.id'), nullable=False)
    address_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    is_primary: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    residence_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class ResidenceVerification(Base):
    """Modelo de persistencia para la tabla `residence_verifications`."""
    __tablename__ = "residence_verifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_address_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('user_addresses.id'), nullable=False)
    verification_method: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    reviewed_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey('profiles.id'), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class CommunityMembership(Base):
    """Modelo de persistencia para la tabla `community_memberships`."""
    __tablename__ = "community_memberships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('profiles.id'), nullable=False)
    community_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('communities.id'), nullable=False)
    zone_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey('zones.id'), nullable=True)
    block_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey('blocks.id'), nullable=True)
    role: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    membership_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    joined_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class UserAvailability(Base):
    """Modelo de persistencia para la tabla `user_availability`."""
    __tablename__ = "user_availability"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('profiles.id'), nullable=False)
    community_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('communities.id'), nullable=False)
    help_category: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_available: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

