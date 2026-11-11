"""Servicio de lógica de negocio para valoraciones y reputación comunitaria."""
import uuid
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.interactions.repository import ReviewRepository
from app.modules.interactions.schemas import (
    ReviewCreate,
    ReviewResponse,
    UserReputationSummary,
)
from app.modules.users.repository import ProfileRepository


class ReviewService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.review_repo = ReviewRepository(session)
        self.profile_repo = ProfileRepository(session)

    async def create_review(
        self,
        reviewer_id: uuid.UUID,
        data: ReviewCreate,
    ) -> ReviewResponse:
        """Crea o actualiza una reseña validando la interacción completada bilateralmente."""
        from sqlalchemy import select
        from app.core.exceptions import EntityNotFoundException, ValidationException
        from app.modules.commerce.models import Service
        from app.modules.chat.models import ChatConversation, ChatParticipant

        if data.service_id:
            service = await self.session.get(Service, data.service_id)
            if not service:
                raise EntityNotFoundException("Servicio", data.service_id)
            if service.provider_id == reviewer_id:
                raise ValidationException("No puedes calificar tu propio servicio.")

            stmt_completed = (
                select(ChatConversation.id)
                .join(ChatParticipant, ChatParticipant.conversation_id == ChatConversation.id)
                .where(
                    ChatConversation.service_id == data.service_id,
                    ChatConversation.service_status == "completed",
                    ChatParticipant.user_id == reviewer_id,
                )
                .limit(1)
            )
            completed_res = await self.session.execute(stmt_completed)
            if not completed_res.scalar_one_or_none():
                raise ValidationException(
                    "Para calificar este servicio, debes haber completado la interacción bilateralmente a través del chat de VeciRed."
                )

        review = await self.review_repo.create_review(reviewer_id, data)
        reviewer_profile = await self.profile_repo.get_by_id(reviewer_id)
        await self.session.commit()

        return ReviewResponse(
            id=review.id,
            reviewer_id=review.reviewer_id,
            reviewer_name=reviewer_profile.full_name if reviewer_profile else "Vecino de la comunidad",
            reviewer_avatar=reviewer_profile.avatar_url if reviewer_profile else None,
            reviewed_user_id=review.reviewed_user_id,
            service_id=review.service_id,
            order_id=review.order_id,
            solidarity_response_id=review.solidarity_response_id,
            rating=review.rating,
            comment=review.comment,
            moderation_status=review.moderation_status,
            created_at=review.created_at,
        )

    async def list_service_reviews(
        self,
        service_id: uuid.UUID,
        page: int = 1,
        limit: int = 20,
    ) -> List[ReviewResponse]:
        """Consulta las reseñas asociadas a un servicio específico."""
        skip = (page - 1) * limit
        rows = await self.review_repo.list_by_service(service_id=service_id, skip=skip, limit=limit)

        return [
            ReviewResponse(
                id=review.id,
                reviewer_id=review.reviewer_id,
                reviewer_name=profile.full_name if profile else "Vecino de la comunidad",
                reviewer_avatar=profile.avatar_url if profile else None,
                reviewed_user_id=review.reviewed_user_id,
                service_id=review.service_id,
                order_id=review.order_id,
                solidarity_response_id=review.solidarity_response_id,
                rating=review.rating,
                comment=review.comment,
                moderation_status=review.moderation_status,
                created_at=review.created_at,
            )
            for review, profile in rows
        ]

    async def get_user_reputation(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        limit: int = 20,
    ) -> UserReputationSummary:
        """Calcula y retorna el resumen de reputación y las reseñas recibidas por un vecino."""
        skip = (page - 1) * limit
        rows, avg_rating, total_count = await self.review_repo.list_by_user(
            user_id=user_id,
            skip=skip,
            limit=limit,
        )
        user_profile = await self.profile_repo.get_by_id(user_id)

        reviews_list = [
            ReviewResponse(
                id=review.id,
                reviewer_id=review.reviewer_id,
                reviewer_name=profile.full_name if profile else "Vecino de la comunidad",
                reviewer_avatar=profile.avatar_url if profile else None,
                reviewed_user_id=review.reviewed_user_id,
                service_id=review.service_id,
                order_id=review.order_id,
                solidarity_response_id=review.solidarity_response_id,
                rating=review.rating,
                comment=review.comment,
                moderation_status=review.moderation_status,
                created_at=review.created_at,
            )
            for review, profile in rows
        ]

        return UserReputationSummary(
            user_id=user_id,
            full_name=user_profile.full_name if user_profile else "Vecino",
            avatar_url=user_profile.avatar_url if user_profile else None,
            average_rating=round(avg_rating, 1),
            total_reviews=total_count,
            reviews=reviews_list,
        )
