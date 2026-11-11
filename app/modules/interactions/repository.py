"""Repositorio de persistencia para el módulo de interacciones y reseñas."""
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.interactions.models import Review
from app.modules.interactions.schemas import ReviewCreate
from app.modules.users.models import Profile


class ReviewRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_review(
        self,
        reviewer_id: uuid.UUID,
        data: ReviewCreate,
    ) -> Review:
        """Crea y persiste una nueva calificación vecinal."""
        reviewed_user_id = data.reviewed_user_id

        # Si no se pasó reviewed_user_id pero sí service_id, buscamos el provider_id del servicio
        if not reviewed_user_id and data.service_id:
            from app.modules.commerce.models import Service
            svc_stmt = select(Service.provider_id).where(Service.id == data.service_id)
            res = await self.session.execute(svc_stmt)
            reviewed_user_id = res.scalar_one_or_none()

        if not reviewed_user_id:
            reviewed_user_id = reviewer_id  # Fallback

        if data.service_id:
            stmt_existing = select(Review).where(
                Review.reviewer_id == reviewer_id,
                Review.service_id == data.service_id,
            )
            res_existing = await self.session.execute(stmt_existing)
            existing_review = res_existing.scalar_one_or_none()
            if existing_review:
                existing_review.rating = data.rating
                existing_review.comment = data.comment
                existing_review.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
                await self.session.flush()
                await self.session.refresh(existing_review)
                return existing_review

        review = Review(
            id=uuid.uuid4(),
            reviewer_id=reviewer_id,
            reviewed_user_id=reviewed_user_id,
            service_id=data.service_id,
            order_id=data.order_id,
            solidarity_response_id=data.solidarity_response_id,
            rating=data.rating,
            comment=data.comment,
            moderation_status="approved",
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        self.session.add(review)
        await self.session.flush()
        await self.session.refresh(review)
        return review

    async def list_by_service(
        self,
        service_id: uuid.UUID,
        skip: int = 0,
        limit: int = 20,
    ) -> List[Tuple[Review, Optional[Profile]]]:
        """Retorna las valoraciones de un servicio junto con el perfil del autor."""
        stmt = (
            select(Review, Profile)
            .outerjoin(Profile, Review.reviewer_id == Profile.id)
            .where(Review.service_id == service_id)
            .order_by(desc(Review.created_at))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.all()

    async def list_by_user(
        self,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[Tuple[Review, Optional[Profile]]], float, int]:
        """Retorna las reseñas recibidas por un usuario, su calificación promedio y total."""
        stmt = (
            select(Review, Profile)
            .outerjoin(Profile, Review.reviewer_id == Profile.id)
            .where(Review.reviewed_user_id == user_id)
            .order_by(desc(Review.created_at))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        rows = result.all()

        stats_stmt = (
            select(
                func.coalesce(func.avg(Review.rating), 5.0),
                func.count(Review.id)
            )
            .where(Review.reviewed_user_id == user_id)
        )
        stats_result = await self.session.execute(stats_stmt)
        avg_rating, total_count = stats_result.one()

        return rows, float(avg_rating or 5.0), int(total_count or 0)
