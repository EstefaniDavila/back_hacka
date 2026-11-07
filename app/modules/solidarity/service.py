"""Lógica de negocio y servicios para el módulo de solidaridad y muro vecinal."""
import math
import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundException, ValidationException, VeciRedException
from app.modules.solidarity.models import SolidarityPost, SolidarityResponse
from app.modules.solidarity.repository import SolidarityRepository
from app.modules.solidarity.schemas import (
    SolidarityPostCreate,
    SolidarityPostDetail,
    SolidarityPostListItem,
    SolidarityPostStatusUpdate,
    SolidarityPostUpdate,
    SolidarityResponseCreate,
    SolidarityResponseItem,
    SolidarityResponseStatusUpdate,
)
from app.shared.pagination import PageMeta, PaginatedResponse


class SolidarityService:
    """Capa de servicios para el muro de solidaridad y favores comunitarios."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = SolidarityRepository(session)

    # -------------------------------------------------------------
    # Muro Solidario: Listado y Búsqueda
    # -------------------------------------------------------------
    async def list_posts(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        post_type: Optional[str] = None,
        community_id: Optional[uuid.UUID] = None,
        status: Optional[str] = "active",
        author_id: Optional[uuid.UUID] = None,
        page: int = 1,
        limit: int = 20,
    ) -> PaginatedResponse[SolidarityPostListItem]:
        """Consulta publicaciones solidarias activas con paginación y filtros."""
        skip = (page - 1) * limit
        items_data, total = await self.repository.list_posts(
            query=query,
            category=category,
            post_type=post_type,
            community_id=community_id,
            status=status,
            author_id=author_id,
            skip=skip,
            limit=limit,
        )

        total_pages = math.ceil(total / limit) if total > 0 else 1
        items = [SolidarityPostListItem(**item) for item in items_data]

        return PaginatedResponse(
            items=items,
            meta=PageMeta(total=total, page=page, limit=limit, total_pages=total_pages),
        )

    async def get_post_detail(self, post_id: uuid.UUID) -> SolidarityPostDetail:
        """Obtiene la ficha descriptiva completa de una publicación del muro."""
        detail = await self.repository.get_post_detail(post_id)
        if not detail:
            raise EntityNotFoundException("Publicación solidaria", post_id)
        return SolidarityPostDetail(**detail)

    # -------------------------------------------------------------
    # Muro Solidario: Creación, Modificación y Eliminación
    # -------------------------------------------------------------
    async def create_post(
        self,
        user_id: uuid.UUID,
        data: SolidarityPostCreate,
    ) -> SolidarityPostDetail:
        """Crea una nueva publicación en el muro solidario de la comunidad."""
        community_id = data.community_id
        if not community_id:
            community_id = await self.repository.get_first_active_community_id()
            if not community_id:
                raise ValidationException("No existe una comunidad vecinal activa para asociar la publicación.")

        post = await self.repository.create_post(
            author_id=user_id,
            community_id=community_id,
            title=data.title,
            description=data.description,
            category=data.category,
            post_type=data.post_type,
        )
        await self.session.commit()
        return await self.get_post_detail(post.id)

    async def update_post(
        self,
        post_id: uuid.UUID,
        user_id: uuid.UUID,
        data: SolidarityPostUpdate,
    ) -> SolidarityPostDetail:
        """Permite al autor editar la información de su publicación."""
        post = await self.repository.get_post_by_id(post_id)
        if not post:
            raise EntityNotFoundException("Publicación solidaria", post_id)

        if post.author_id != user_id:
            raise VeciRedException(
                message="No tienes permiso para modificar esta publicación solidaria.",
                code="SOLIDARITY_POST_NOT_OWNED",
                status_code=403,
            )

        await self.repository.update_post(
            post=post,
            title=data.title,
            description=data.description,
            category=data.category,
            post_type=data.post_type,
        )
        await self.session.commit()
        return await self.get_post_detail(post.id)

    async def update_post_status(
        self,
        post_id: uuid.UUID,
        user_id: uuid.UUID,
        status_update: SolidarityPostStatusUpdate,
    ) -> SolidarityPostDetail:
        """Permite al autor cambiar el estado de la publicación (ej: completado, cancelado)."""
        post = await self.repository.get_post_by_id(post_id)
        if not post:
            raise EntityNotFoundException("Publicación solidaria", post_id)

        if post.author_id != user_id:
            raise VeciRedException(
                message="No tienes permiso para cambiar el estado de esta publicación.",
                code="SOLIDARITY_POST_NOT_OWNED",
                status_code=403,
            )

        await self.repository.update_status(post, status_update.status)
        await self.session.commit()
        return await self.get_post_detail(post.id)

    async def delete_post(self, post_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Elimina una publicación propia del muro solidario."""
        post = await self.repository.get_post_by_id(post_id)
        if not post:
            raise EntityNotFoundException("Publicación solidaria", post_id)

        if post.author_id != user_id:
            raise VeciRedException(
                message="No tienes permiso para eliminar esta publicación solidaria.",
                code="SOLIDARITY_POST_NOT_OWNED",
                status_code=403,
            )

        await self.repository.delete_post(post_id)
        await self.session.commit()

    # -------------------------------------------------------------
    # Respuestas / Mano Amiga y Cadena de Favores
    # -------------------------------------------------------------
    async def respond_to_post(
        self,
        post_id: uuid.UUID,
        user_id: uuid.UUID,
        data: SolidarityResponseCreate,
    ) -> SolidarityResponseItem:
        """Permite a un vecino ofrecer su ayuda o responder a un favor publicado."""
        post = await self.repository.get_post_by_id(post_id)
        if not post:
            raise EntityNotFoundException("Publicación solidaria", post_id)

        if post.author_id == user_id:
            raise ValidationException("No puedes responder a tu propia publicación solidaria.")

        if post.status != "active":
            raise ValidationException("Esta publicación no está activa para recibir respuestas.")

        response = await self.repository.create_response(
            post_id=post_id,
            responder_id=user_id,
            message=data.message,
            return_due_date=data.return_due_date,
        )
        await self.session.commit()

        # Obtener ficha con datos del vecino
        responses = await self.repository.list_responses_for_post(post_id)
        for r in responses:
            if r["id"] == response.id:
                return SolidarityResponseItem(**r)

        return SolidarityResponseItem.model_validate(response)

    async def list_responses(self, post_id: uuid.UUID) -> List[SolidarityResponseItem]:
        """Consulta todas las respuestas y vecinos postulados para un favor."""
        post = await self.repository.get_post_by_id(post_id)
        if not post:
            raise EntityNotFoundException("Publicación solidaria", post_id)

        items = await self.repository.list_responses_for_post(post_id)
        return [SolidarityResponseItem(**item) for item in items]

    async def update_response_status(
        self,
        response_id: uuid.UUID,
        user_id: uuid.UUID,
        status_update: SolidarityResponseStatusUpdate,
    ) -> SolidarityResponseItem:
        """Permite al autor del post o al postulante actualizar el estado del intercambio."""
        response = await self.repository.get_response_by_id(response_id)
        if not response:
            raise EntityNotFoundException("Respuesta solidaria", response_id)

        post = await self.repository.get_post_by_id(response.post_id)
        if not post:
            raise EntityNotFoundException("Publicación solidaria", response.post_id)

        # Solo el autor del post o el que respondió pueden modificar el estado
        if post.author_id != user_id and response.responder_id != user_id:
            raise VeciRedException(
                message="No tienes permiso para modificar esta respuesta solidaria.",
                code="SOLIDARITY_RESPONSE_NOT_AUTHORIZED",
                status_code=403,
            )

        await self.repository.update_response_status(response, status_update.response_status)
        await self.session.commit()

        responses = await self.repository.list_responses_for_post(post.id)
        for r in responses:
            if r["id"] == response.id:
                return SolidarityResponseItem(**r)

        return SolidarityResponseItem.model_validate(response)
