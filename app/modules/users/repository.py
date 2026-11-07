"""Repositorios de persistencia para el módulo users."""
import uuid
from typing import Optional, Sequence
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import (
    CommunityMembership,
    IdentityVerification,
    Profile,
    ResidenceVerification,
    UserAddress,
    UserAvailability,
)
from app.modules.users.schemas import (
    CommunityMembershipCreate,
    IdentityVerificationCreate,
    ProfileCreate,
    ProfileUpdate,
    UserAddressCreate,
)
from app.shared.repository import BaseRepository


class ProfileRepository(BaseRepository[Profile, ProfileCreate, ProfileUpdate]):
    """Repositorio para gestionar perfiles de usuario."""

    def __init__(self, session: AsyncSession):
        super().__init__(Profile, session)

    async def get_by_id(self, user_id: uuid.UUID) -> Optional[Profile]:
        stmt = select(Profile).where(Profile.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_profile(self, profile_data: dict) -> Profile:
        """Crea el perfil si no existe o lo actualiza si ya existe."""
        user_id = profile_data.get("id")
        existing = await self.get_by_id(user_id)
        if existing:
            for k, v in profile_data.items():
                if v is not None and hasattr(existing, k):
                    setattr(existing, k, v)
            self.session.add(existing)
            await self.session.flush()
            await self.session.refresh(existing)
            return existing
        else:
            new_profile = Profile(**profile_data)
            self.session.add(new_profile)
            await self.session.flush()
            await self.session.refresh(new_profile)
            return new_profile


class IdentityVerificationRepository(BaseRepository[IdentityVerification, IdentityVerificationCreate, IdentityVerificationCreate]):
    """Repositorio para verificaciones de identidad."""

    def __init__(self, session: AsyncSession):
        super().__init__(IdentityVerification, session)

    async def get_latest_by_user_id(self, user_id: uuid.UUID) -> Optional[IdentityVerification]:
        stmt = (
            select(IdentityVerification)
            .where(IdentityVerification.user_id == user_id)
            .order_by(desc(IdentityVerification.created_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class UserAddressRepository(BaseRepository[UserAddress, UserAddressCreate, UserAddressCreate]):
    """Repositorio para direcciones de usuario."""

    def __init__(self, session: AsyncSession):
        super().__init__(UserAddress, session)

    async def get_primary_by_user(self, user_id: uuid.UUID) -> Optional[UserAddress]:
        stmt = (
            select(UserAddress)
            .where(UserAddress.user_id == user_id, UserAddress.is_primary == True)  # noqa: E712
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class CommunityMembershipRepository(BaseRepository[CommunityMembership, CommunityMembershipCreate, CommunityMembershipCreate]):
    """Repositorio para membresías en comunidades."""

    def __init__(self, session: AsyncSession):
        super().__init__(CommunityMembership, session)

    async def get_by_user(self, user_id: uuid.UUID) -> Sequence[CommunityMembership]:
        stmt = select(CommunityMembership).where(CommunityMembership.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_active_by_user(self, user_id: uuid.UUID) -> Optional[CommunityMembership]:
        stmt = (
            select(CommunityMembership)
            .where(
                CommunityMembership.user_id == user_id,
                CommunityMembership.membership_status == "active",
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
