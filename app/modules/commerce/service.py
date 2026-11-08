"""Lógica de negocio y servicios para el módulo de comercio (servicios y productos) de VeciRed IA."""
import math
import uuid
from typing import List, Optional, Sequence
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundException, ValidationException, VeciRedException
from app.modules.commerce.models import Product, Service, ServiceCategory
from app.modules.commerce.repository import CommerceRepository
from app.modules.commerce.schemas import (
    ProductCategoryResponse,
    ProductCreate,
    ProductDetailResponse,
    ProductListItemResponse,
    ProductStatusUpdate,
    ProductUpdate,
    ReviewCreate,
    ReviewResponse,
    ServiceCategoryResponse,
    ServiceCreate,
    ServiceDetailResponse,
    ServiceListItemResponse,
    ServiceStatusUpdate,
    ServiceUpdate,
)
from app.shared.pagination import PageMeta, PaginatedResponse


class CommerceService:
    """Capa de reglas de negocio para servicios, productos barriales, categorías y reseñas."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = CommerceRepository(session)

    # -------------------------------------------------------------
    # Categorías de Servicios
    # -------------------------------------------------------------
    async def list_categories(self) -> List[ServiceCategoryResponse]:
        """Retorna todas las categorías de servicios disponibles para los vecinos."""
        categories = await self.repository.list_categories()
        return [ServiceCategoryResponse.model_validate(c) for c in categories]

    # -------------------------------------------------------------
    # Servicios: Búsqueda y Listado
    # -------------------------------------------------------------
    async def list_services(
        self,
        query: Optional[str] = None,
        category_id: Optional[uuid.UUID] = None,
        community_id: Optional[uuid.UUID] = None,
        sort_by: str = "newest",
        page: int = 1,
        limit: int = 20,
    ) -> PaginatedResponse[ServiceListItemResponse]:
        """Consulta servicios públicos activos con filtros de búsqueda, categoría y orden."""
        skip = (page - 1) * limit
        items_data, total = await self.repository.list_services(
            query=query,
            category_id=category_id,
            community_id=community_id,
            status="active",
            sort_by=sort_by,
            skip=skip,
            limit=limit,
        )

        total_pages = math.ceil(total / limit) if total > 0 else 1
        items = [ServiceListItemResponse(**item) for item in items_data]

        return PaginatedResponse(
            items=items,
            meta=PageMeta(total=total, page=page, limit=limit, total_pages=total_pages),
        )

    async def get_service_detail(self, service_id: uuid.UUID) -> ServiceDetailResponse:
        """Obtiene la ficha técnica completa de un servicio, su proveedor y valoraciones."""
        detail = await self.repository.get_service_detail(service_id)
        if not detail:
            raise EntityNotFoundException("Servicio", service_id)
        return ServiceDetailResponse(**detail)

    # -------------------------------------------------------------
    # Servicios: Publicación y Administración (Vecino Oferente)
    # -------------------------------------------------------------
    async def create_service(
        self,
        user_id: uuid.UUID,
        data: ServiceCreate,
    ) -> ServiceDetailResponse:
        """Crea una nueva publicación de servicio asignada al vecino autenticado."""
        cat_id = data.category_id
        if not cat_id:
            all_cats = await self.repository.list_categories()
            if all_cats:
                cat_id = all_cats[0].id if hasattr(all_cats[0], 'id') else all_cats[0]['id']
        category = await self.repository.get_category_by_id(cat_id) if cat_id else None
        if not category:
            raise EntityNotFoundException("Categoría de servicio", cat_id or data.category_id)

        community_id = data.community_id
        if not community_id:
            community_id = await self.repository.get_first_active_community_id()
            if not community_id:
                raise ValidationException("No hay una comunidad vecinal activa configurada en el sistema.")

        service = await self.repository.create_service(
            provider_id=user_id,
            category_id=cat_id,
            community_id=community_id,
            address_id=data.address_id,
            title=data.title,
            description=data.description,
            price_from=data.price_from,
            price_unit=data.price_unit,
            availability=data.availability,
        )
        await self.session.commit()
        return await self.get_service_detail(service.id)

    async def update_service(
        self,
        service_id: uuid.UUID,
        user_id: uuid.UUID,
        data: ServiceUpdate,
    ) -> ServiceDetailResponse:
        """Permite al vecino autor modificar la información de su publicación."""
        service = await self.repository.get_service_by_id(service_id)
        if not service:
            raise EntityNotFoundException("Servicio", service_id)

        if service.provider_id != user_id:
            raise VeciRedException(
                message="No tienes permiso para modificar este servicio.",
                code="SERVICE_NOT_OWNED",
                status_code=403,
            )

        if data.category_id is not None:
            category = await self.repository.get_category_by_id(data.category_id)
            if not category:
                raise EntityNotFoundException("Categoría de servicio", data.category_id)

        await self.repository.update_service(
            service=service,
            title=data.title,
            description=data.description,
            category_id=cat_id,
            price_from=data.price_from,
            price_unit=data.price_unit,
            availability=data.availability,
        )
        await self.session.commit()
        return await self.get_service_detail(service.id)

    async def update_service_status(
        self,
        service_id: uuid.UUID,
        user_id: uuid.UUID,
        status_update: ServiceStatusUpdate,
    ) -> ServiceDetailResponse:
        """Pausa, reactiva o desactiva un servicio propio."""
        service = await self.repository.get_service_by_id(service_id)
        if not service:
            raise EntityNotFoundException("Servicio", service_id)

        if service.provider_id != user_id:
            raise VeciRedException(
                message="No tienes permiso para cambiar el estado de este servicio.",
                code="SERVICE_NOT_OWNED",
                status_code=403,
            )

        await self.repository.update_status(service, status_update.status)
        await self.session.commit()
        return await self.get_service_detail(service.id)

    async def delete_service(
        self,
        service_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Desactiva lógicamente una publicación de servicio propia."""
        service = await self.repository.get_service_by_id(service_id)
        if not service:
            raise EntityNotFoundException("Servicio", service_id)

        if service.provider_id != user_id:
            raise VeciRedException(
                message="No tienes permiso para eliminar este servicio.",
                code="SERVICE_NOT_OWNED",
                status_code=403,
            )

        await self.repository.delete_service(service, soft_delete=True)
        await self.session.commit()

    async def list_my_services(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        limit: int = 20,
    ) -> PaginatedResponse[ServiceListItemResponse]:
        """Lista todos los servicios (activos y pausados) publicados por el usuario actual."""
        skip = (page - 1) * limit
        items_data, total = await self.repository.list_services(
            provider_id=user_id,
            status=None,
            skip=skip,
            limit=limit,
        )
        total_pages = math.ceil(total / limit) if total > 0 else 1
        items = [ServiceListItemResponse(**item) for item in items_data]

        return PaginatedResponse(
            items=items,
            meta=PageMeta(total=total, page=page, limit=limit, total_pages=total_pages),
        )

    async def list_user_services(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        limit: int = 20,
    ) -> PaginatedResponse[ServiceListItemResponse]:
        """Lista los servicios públicos activos de un vecino específico."""
        skip = (page - 1) * limit
        items_data, total = await self.repository.list_services(
            provider_id=user_id,
            status="active",
            skip=skip,
            limit=limit,
        )
        total_pages = math.ceil(total / limit) if total > 0 else 1
        items = [ServiceListItemResponse(**item) for item in items_data]

        return PaginatedResponse(
            items=items,
            meta=PageMeta(total=total, page=page, limit=limit, total_pages=total_pages),
        )

    async def add_service_review(
        self,
        service_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        data: ReviewCreate,
    ) -> ReviewResponse:
        """Registra una valoración y comentario para un servicio prestado."""
        service = await self.repository.get_service_by_id(service_id)
        if not service:
            raise EntityNotFoundException("Servicio", service_id)

        if service.provider_id == reviewer_id:
            raise VeciRedException(
                message="No puedes calificar tu propio servicio.",
                code="SELF_REVIEW_NOT_ALLOWED",
                status_code=400,
            )

        review = await self.repository.add_review(
            service_id=service_id,
            reviewer_id=reviewer_id,
            reviewed_user_id=service.provider_id,
            rating=data.rating,
            comment=data.comment,
        )
        await self.session.commit()

        reviews = await self.repository.get_service_reviews(service_id, limit=1)
        if reviews:
            return ReviewResponse(**reviews[0])

        return ReviewResponse(
            id=review.id,
            reviewer_id=review.reviewer_id,
            reviewed_user_id=review.reviewed_user_id,
            service_id=review.service_id,
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
        """Consulta el listado de reseñas de un servicio."""
        service = await self.repository.get_service_by_id(service_id)
        if not service:
            raise EntityNotFoundException("Servicio", service_id)

        skip = (page - 1) * limit
        reviews_data = await self.repository.get_service_reviews(service_id, skip=skip, limit=limit)
        return [ReviewResponse(**r) for r in reviews_data]

    # =============================================================
    # PRODUCTOS BARRIALES (COMERCIO LOCAL)
    # =============================================================
    async def list_product_categories(self) -> List[ProductCategoryResponse]:
        """Obtiene todas las categorías de productos."""
        cats = await self.repository.list_product_categories()
        return [ProductCategoryResponse.model_validate(c) for c in cats]

    async def list_products(
        self,
        query: Optional[str] = None,
        category_id: Optional[uuid.UUID] = None,
        business_id: Optional[uuid.UUID] = None,
        seller_id: Optional[uuid.UUID] = None,
        status: Optional[str] = "active",
        page: int = 1,
        limit: int = 20,
    ) -> PaginatedResponse[ProductListItemResponse]:
        """Lista productos con filtros y paginación."""
        skip = (page - 1) * limit
        items_data, total = await self.repository.list_products(
            query=query,
            category_id=category_id,
            business_id=business_id,
            seller_id=seller_id,
            status=status,
            skip=skip,
            limit=limit,
        )
        total_pages = math.ceil(total / limit) if total > 0 else 1
        items = [ProductListItemResponse(**item) for item in items_data]

        return PaginatedResponse(
            items=items,
            meta=PageMeta(total=total, page=page, limit=limit, total_pages=total_pages),
        )

    async def get_product_detail(self, product_id: uuid.UUID) -> ProductDetailResponse:
        """Obtiene la ficha técnica completa del producto."""
        detail = await self.repository.get_product_detail(product_id)
        if not detail:
            raise EntityNotFoundException("Producto", product_id)
        return ProductDetailResponse(**detail)

    async def create_product(
        self,
        user_id: uuid.UUID,
        data: ProductCreate,
    ) -> ProductDetailResponse:
        """Crea un nuevo producto asignado al negocio del usuario."""
        business_id = data.business_id
        if not business_id:
            community_id = await self.repository.get_first_active_community_id()
            if not community_id:
                raise ValidationException("No hay una comunidad vecinal activa para vincular la tienda.")
            biz = await self.repository.get_or_create_user_business(owner_id=user_id, community_id=community_id)
            business_id = biz.id

        prod = await self.repository.create_product(
            name=data.name,
            price=data.price,
            business_id=business_id,
            category_id=cat_id,
            description=data.description,
            stock=data.stock,
            image_url=data.image_url,
        )
        await self.session.commit()
        return await self.get_product_detail(prod.id)

    async def update_product(
        self,
        product_id: uuid.UUID,
        user_id: uuid.UUID,
        data: ProductUpdate,
    ) -> ProductDetailResponse:
        """Actualiza un producto propio."""
        prod = await self.repository.get_product_by_id(product_id)
        if not prod:
            raise EntityNotFoundException("Producto", product_id)

        await self.repository.update_product(
            product=prod,
            name=data.name,
            description=data.description,
            price=data.price,
            stock=data.stock,
            category_id=cat_id,
            image_url=data.image_url,
        )
        await self.session.commit()
        return await self.get_product_detail(prod.id)

    async def update_product_status(
        self,
        product_id: uuid.UUID,
        user_id: uuid.UUID,
        status_update: ProductStatusUpdate,
    ) -> ProductDetailResponse:
        """Actualiza el estado de disponibilidad del producto."""
        prod = await self.repository.get_product_by_id(product_id)
        if not prod:
            raise EntityNotFoundException("Producto", product_id)

        await self.repository.update_product_status(prod, status_update.status)
        await self.session.commit()
        return await self.get_product_detail(prod.id)

    async def delete_product(
        self,
        product_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Elimina un producto del catálogo."""
        prod = await self.repository.get_product_by_id(product_id)
        if not prod:
            raise EntityNotFoundException("Producto", product_id)

        await self.repository.delete_product(product_id)
        await self.session.commit()
