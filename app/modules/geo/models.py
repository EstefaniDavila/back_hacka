"""Modelos SQLAlchemy 2.0 para el módulo geo de VeciRed IA."""
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

class Department(Base):
    """Modelo de persistencia para la tabla `departments`."""
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    ubigeo: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)

class Province(Base):
    """Modelo de persistencia para la tabla `provinces`."""
    __tablename__ = "provinces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    department_id: Mapped[int] = mapped_column(Integer, ForeignKey('departments.id'), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    ubigeo: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)

class District(Base):
    """Modelo de persistencia para la tabla `districts`."""
    __tablename__ = "districts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    province_id: Mapped[int] = mapped_column(Integer, ForeignKey('provinces.id'), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    ubigeo: Mapped[Optional[str]] = mapped_column(String(6), nullable=True)

class Community(Base):
    """Modelo de persistencia para la tabla `communities`."""
    __tablename__ = "communities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    district_id: Mapped[int] = mapped_column(Integer, ForeignKey('districts.id'), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

class Zone(Base):
    """Modelo de persistencia para la tabla `zones`."""
    __tablename__ = "zones"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    community_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('communities.id'), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

class Block(Base):
    """Modelo de persistencia para la tabla `blocks`."""
    __tablename__ = "blocks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    zone_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('zones.id'), nullable=False)
    code: Mapped[str] = mapped_column(String(30), nullable=False)

class Address(Base):
    """Modelo de persistencia para la tabla `addresses`."""
    __tablename__ = "addresses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    district_id: Mapped[int] = mapped_column(Integer, ForeignKey('districts.id'), nullable=False)
    zone_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey('zones.id'), nullable=True)
    block_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey('blocks.id'), nullable=True)
    street_address: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    lot_number: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 7), nullable=True)
    maps_place_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

