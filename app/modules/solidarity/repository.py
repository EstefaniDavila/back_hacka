"""Repositorio asíncrono para el módulo de solidaridad y muro vecinal."""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from sqlalchemy import delete, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.geo.models import Address, Community
from app.modules.solidarity.models import SolidarityPost, SolidarityResponse
from app.modules.users.models import Profile, UserAddress


class SolidarityRepository:
    """Acceso a datos para publicaciones del muro solidario y respuestas/favores."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_first_active_community_id(self) -> Optional[uuid.UUID]:
        """Obtiene el ID de la primera comunidad activa disponible."""
        stmt = select(Community.id).where(Community.status == "active").limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # PUBLICACIONES EN EL MURO SOLIDARIO (CRUD & BÚSQUEDA)
    # ------------------------------------------------------------------
    async def list_posts(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        post_type: Optional[str] = None,
        community_id: Optional[uuid.UUID] = None,
        status: Optional[str] = "active",
        author_id: Optional[uuid.UUID] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Lista publicaciones del muro con conteo de respuestas e información del autor."""
        # Subconsulta para contar respuestas por publicación
        resp_count_subq = (
            select(
                SolidarityResponse.post_id,
                func.count(SolidarityResponse.id).label("responses_count"),
            )
            .group_by(SolidarityResponse.post_id)
            .subquery()
        )

        # Query base
        stmt = (
            select(
                SolidarityPost.id,
                SolidarityPost.author_id,
                Profile.full_name.label("author_name"),
                Profile.avatar_url.label("author_avatar"),
                SolidarityPost.community_id,
                Community.name.label("community_name"),
                SolidarityPost.category,
                SolidarityPost.post_type,
                SolidarityPost.title,
                SolidarityPost.description,
                SolidarityPost.status,
                SolidarityPost.created_at,
                func.coalesce(resp_count_subq.c.responses_count, 0).label("responses_count"),
            )
            .join(Profile, Profile.id == SolidarityPost.author_id)
            .join(Community, Community.id == SolidarityPost.community_id)
            .outerjoin(resp_count_subq, resp_count_subq.c.post_id == SolidarityPost.id)
        )

        count_stmt = (
            select(func.count(SolidarityPost.id))
            .join(Profile, Profile.id == SolidarityPost.author_id)
            .join(Community, Community.id == SolidarityPost.community_id)
        )

        conditions = []
        if status:
            conditions.append(SolidarityPost.status == status)
        if category:
            conditions.append(SolidarityPost.category.ilike(f"%{category.strip()}%"))
        if post_type:
            conditions.append(SolidarityPost.post_type == post_type.strip())
        if community_id:
            conditions.append(SolidarityPost.community_id == community_id)
        if author_id:
            conditions.append(SolidarityPost.author_id == author_id)
        if query:
            q_pattern = f"%{query.strip()}%"
            conditions.append(
                or_(
                    SolidarityPost.title.ilike(q_pattern),
                    SolidarityPost.description.ilike(q_pattern),
                    Profile.full_name.ilike(q_pattern),
                    SolidarityPost.category.ilike(q_pattern),
                )
            )

        if conditions:
            stmt = stmt.where(*conditions)
            count_stmt = count_stmt.where(*conditions)

        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar() or 0

        stmt = stmt.order_by(desc(SolidarityPost.created_at)).offset(skip).limit(limit)
        results = await self.session.execute(stmt)

        items = []
        for row in results.mappings().all():
            items.append(dict(row))

        return items, total

    async def get_post_by_id(self, post_id: uuid.UUID) -> Optional[SolidarityPost]:
        """Obtiene la entidad ORM del post por su ID."""
        stmt = select(SolidarityPost).where(SolidarityPost.id == post_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_post_detail(self, post_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Obtiene el detalle completo de la publicación con datos del autor y ubicación."""
        resp_count_subq = (
            select(
                SolidarityResponse.post_id,
                func.count(SolidarityResponse.id).label("responses_count"),
            )
            .group_by(SolidarityResponse.post_id)
            .subquery()
        )

        stmt = (
            select(
                SolidarityPost.id,
                SolidarityPost.author_id,
                Profile.full_name.label("author_name"),
                Profile.avatar_url.label("author_avatar"),
                Profile.phone.label("author_phone"),
                SolidarityPost.community_id,
                Community.name.label("community_name"),
                SolidarityPost.category,
                SolidarityPost.post_type,
                SolidarityPost.title,
                SolidarityPost.description,
                SolidarityPost.status,
                SolidarityPost.created_at,
                func.coalesce(resp_count_subq.c.responses_count, 0).label("responses_count"),
            )
            .join(Profile, Profile.id == SolidarityPost.author_id)
            .join(Community, Community.id == SolidarityPost.community_id)
            .outerjoin(resp_count_subq, resp_count_subq.c.post_id == SolidarityPost.id)
            .where(SolidarityPost.id == post_id)
        )
        res = await self.session.execute(stmt)
        row = res.mappings().one_or_none()
        if not row:
            return None
        return dict(row)

    async def create_post(
        self,
        author_id: uuid.UUID,
        community_id: uuid.UUID,
        title: str,
        description: Optional[str],
        category: Optional[str],
        post_type: str,
    ) -> SolidarityPost:
        """Crea una nueva publicación en el muro solidario."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        post = SolidarityPost(
            id=uuid.uuid4(),
            author_id=author_id,
            community_id=community_id,
            category=category or "Herramientas",
            post_type=post_type,
            title=title.strip(),
            description=description.strip() if description else None,
            status="active",
            created_at=now,
        )
        self.session.add(post)
        await self.session.flush()
        await self.session.refresh(post)
        return post

    async def update_post(
        self,
        post: SolidarityPost,
        title: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        post_type: Optional[str] = None,
    ) -> SolidarityPost:
        """Actualiza campos editables de la publicación."""
        if title is not None:
            post.title = title.strip()
        if description is not None:
            post.description = description.strip()
        if category is not None:
            post.category = category.strip()
        if post_type is not None:
            post.post_type = post_type.strip()
        self.session.add(post)
        await self.session.flush()
        await self.session.refresh(post)
        return post

    async def update_status(self, post: SolidarityPost, status: str) -> SolidarityPost:
        """Cambia el estado de la publicación (active, in_progress, completed, cancelled)."""
        post.status = status
        self.session.add(post)
        await self.session.flush()
        await self.session.refresh(post)
        return post

    async def delete_post(self, post_id: uuid.UUID) -> bool:
        """Elimina lógicamente o físicamente la publicación."""
        stmt = delete(SolidarityPost).where(SolidarityPost.id == post_id)
        result = await self.session.execute(stmt)
        return (result.rowcount or 0) > 0

    # ------------------------------------------------------------------
    # RESPUESTAS A PUBLICACIONES (CADENA DE FAVORES / VOLUNTARIADO)
    # ------------------------------------------------------------------
    async def create_response(
        self,
        post_id: uuid.UUID,
        responder_id: uuid.UUID,
        message: Optional[str] = None,
        return_due_date: Optional[datetime] = None,
    ) -> SolidarityResponse:
        """Crea una respuesta vecinal a una solicitud u oferta."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        response_id = uuid.uuid4()
        qr_code = f"QR-FAVOR-{response_id.hex[:10].upper()}"

        resp = SolidarityResponse(
            id=response_id,
            post_id=post_id,
            responder_id=responder_id,
            message=message.strip() if message else None,
            response_status="pending",
            handshake_qr_code=qr_code,
            return_due_date=return_due_date,
            created_at=now,
        )
        self.session.add(resp)
        await self.session.flush()
        await self.session.refresh(resp)
        return resp

    async def list_responses_for_post(self, post_id: uuid.UUID) -> List[Dict[str, Any]]:
        """Lista todas las respuestas/postulaciones de ayuda para una publicación."""
        stmt = (
            select(
                SolidarityResponse.id,
                SolidarityResponse.post_id,
                SolidarityResponse.responder_id,
                Profile.full_name.label("responder_name"),
                Profile.avatar_url.label("responder_avatar"),
                Profile.phone.label("responder_phone"),
                SolidarityResponse.message,
                SolidarityResponse.response_status,
                SolidarityResponse.handshake_qr_code,
                SolidarityResponse.return_due_date,
                SolidarityResponse.created_at,
            )
            .join(Profile, Profile.id == SolidarityResponse.responder_id)
            .where(SolidarityResponse.post_id == post_id)
            .order_by(desc(SolidarityResponse.created_at))
        )
        res = await self.session.execute(stmt)
        return [dict(r) for r in res.mappings().all()]

    async def get_response_by_id(self, response_id: uuid.UUID) -> Optional[SolidarityResponse]:
        """Obtiene la respuesta por su ID."""
        stmt = select(SolidarityResponse).where(SolidarityResponse.id == response_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def update_response_status(self, response: SolidarityResponse, status: str) -> SolidarityResponse:
        """Actualiza el estado de una respuesta (accepted, completed, cancelled)."""
        response.response_status = status
        self.session.add(response)
        await self.session.flush()
        await self.session.refresh(response)
        return response
