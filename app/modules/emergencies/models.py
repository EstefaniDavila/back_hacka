"""Modelos SQLAlchemy 2.0 para el módulo emergencies de VeciRed IA."""
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

class Emergency(Base):
    """Modelo de persistencia para la tabla `emergencies`."""
    __tablename__ = "emergencies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    reported_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('profiles.id'), nullable=False)
    community_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('communities.id'), nullable=False)
    address_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey('addresses.id'), nullable=True)
    emergency_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    occurred_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class EmergencyNeed(Base):
    """Modelo de persistencia para la tabla `emergency_needs`."""
    __tablename__ = "emergency_needs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    emergency_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('emergencies.id'), nullable=False)
    resource_name: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity_required: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity_committed: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    quantity_delivered: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

class EmergencyContribution(Base):
    """Modelo de persistencia para la tabla `emergency_contributions`."""
    __tablename__ = "emergency_contributions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    need_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('emergency_needs.id'), nullable=False)
    contributor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('profiles.id'), nullable=False)
    collection_point_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey('collection_points.id'), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    contribution_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    committed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    confirmed_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey('profiles.id'), nullable=True)

class CollectionPoint(Base):
    """Modelo de persistencia para la tabla `collection_points`."""
    __tablename__ = "collection_points"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    emergency_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('emergencies.id'), nullable=False)
    address_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('addresses.id'), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

class VulnerabilityReport(Base):
    """Modelo de persistencia para la tabla `vulnerability_reports`."""
    __tablename__ = "vulnerability_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    emergency_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('emergencies.id'), nullable=False)
    reported_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('profiles.id'), nullable=False)
    address_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey('addresses.id'), nullable=True)
    assistance_type: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    priority: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    report_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class EmergencyAlert(Base):
    """Modelo de persistencia para la tabla `emergency_alerts`."""
    __tablename__ = "emergency_alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    emergency_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('emergencies.id'), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('profiles.id'), nullable=False)
    alert_radius_m: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class AlertDelivery(Base):
    """Modelo de persistencia para la tabla `alert_deliveries`."""
    __tablename__ = "alert_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    alert_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('emergency_alerts.id'), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('profiles.id'), nullable=False)
    delivery_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class EmergencyVolunteer(Base):
    """Modelo de persistencia para la tabla `emergency_volunteers`."""
    __tablename__ = "emergency_volunteers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    emergency_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    skill: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    avatar: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    distance_m: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=50)
    status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default="En camino")
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=datetime.utcnow)

