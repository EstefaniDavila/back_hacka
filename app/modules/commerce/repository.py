"""Repositorio asíncrono para el módulo de comercio y servicios de VeciRed IA."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple
from sqlalchemy import delete, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.commerce.models import (
    Business,
    Order,
    OrderItem,
    Product,
    ProductCategory,
    Service,
    ServiceCategory,
)
from app.modules.geo.models import Community
from app.modules.interactions.models import Review
from app.modules.users.models import Profile


class CommerceRepository:
    """Acceso a datos para servicios, categorías y reseñas asociadas."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------
    # CATEGORÍAS
    # ------------------------------------------------------------------
    async def list_categories(self) -> Sequence[ServiceCategory]:
        """Obtiene todas las categorías de servicios disponibles."""
        stmt = select(ServiceCategory).order_by(ServiceCategory.name.asc())
        result = await self.session.execute(stmt)
        categories = result.scalars().all()

        if not categories:
            # Seed categorías iniciales si la tabla está vacía
            await self._seed_default_categories()
            result = await self.session.execute(stmt)
            categories = result.scalars().all()

        return categories

    async def get_category_by_id(self, category_id: uuid.UUID) -> Optional[ServiceCategory]:
        stmt = select(ServiceCategory).where(ServiceCategory.id == category_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _seed_default_categories(self) -> None:
        """Crea categorías base iniciales si no existen en Supabase."""
        defaults = [
            ("Electricidad y Cableado", "⚡"),
            ("Gasfitería y Plomería", "🔧"),
            ("Limpieza y Hogar", "🧹"),
            ("Jardinería y Poda", "🌱"),
            ("Repostería y Comida", "🍰"),
            ("Clases y Apoyo Escolar", "🎓"),
            ("Cuidado de Mascotas", "🐾"),
            ("Fletes y Movilidad", "🚚"),
            ("Carpintería y Muebles", "🪚"),
            ("Albañilería y Pintura", "🧱"),
        ]
        for name, icon in defaults:
            cat = ServiceCategory(
                id=uuid.uuid4(),
                name=name,
                icon=icon,
            )
            self.session.add(cat)
        await self.session.commit()

    # ------------------------------------------------------------------
    # GESTIÓN DE SERVICIOS (CRUD)
    # ------------------------------------------------------------------
    async def get_service_by_id(self, service_id: uuid.UUID) -> Optional[Service]:
        """Obtiene un servicio por su identificador único."""
        stmt = select(Service).where(Service.id == service_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_service(
        self,
        provider_id: uuid.UUID,
        category_id: uuid.UUID,
        community_id: uuid.UUID,
        title: str,
        description: Optional[str] = None,
        price_from: Optional[Decimal] = None,
        price_unit: Optional[str] = "servicio",
        availability: Optional[str] = None,
        address_id: Optional[uuid.UUID] = None,
        image_url: Optional[str] = None,
    ) -> Service:
        """Crea un nuevo servicio en la base de datos."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        service = Service(
            id=uuid.uuid4(),
            provider_id=provider_id,
            category_id=category_id,
            community_id=community_id,
            address_id=address_id,
            title=title.strip(),
            description=description.strip() if description else None,
            price_from=price_from,
            price_unit=price_unit or "servicio",
            availability=availability.strip() if availability else None,
            image_url=image_url.strip() if image_url else None,
            status="active",
            created_at=now,
        )
        self.session.add(service)
        await self.session.flush()
        await self.session.refresh(service)
        return service

    async def update_service(
        self,
        service: Service,
        title: Optional[str] = None,
        description: Optional[str] = None,
        category_id: Optional[uuid.UUID] = None,
        price_from: Optional[Decimal] = None,
        price_unit: Optional[str] = None,
        availability: Optional[str] = None,
    ) -> Service:
        """Actualiza la información descriptiva de un servicio."""
        if title is not None:
            service.title = title.strip()
        if description is not None:
            service.description = description.strip()
        if category_id is not None:
            service.category_id = category_id
        if price_from is not None:
            service.price_from = price_from
        if price_unit is not None:
            service.price_unit = price_unit
        if availability is not None:
            service.availability = availability

        self.session.add(service)
        await self.session.flush()
        await self.session.refresh(service)
        return service

    async def update_status(self, service: Service, status: str) -> Service:
        """Actualiza el estado de publicación (active, paused, inactive, etc.)."""
        service.status = status
        self.session.add(service)
        await self.session.flush()
        await self.session.refresh(service)
        return service

    async def delete_service(self, service: Service, soft_delete: bool = True) -> None:
        """Elimina o desactiva lógicamente el servicio."""
        if soft_delete:
            service.status = "inactive"
            self.session.add(service)
            await self.session.flush()
        else:
            await self.session.delete(service)
            await self.session.flush()

    # ------------------------------------------------------------------
    # LISTADO Y BÚSQUEDA AVANZADA CON JOINS Y AGREGACIONES
    # ------------------------------------------------------------------
    async def list_services(
        self,
        query: Optional[str] = None,
        category_id: Optional[uuid.UUID] = None,
        community_id: Optional[uuid.UUID] = None,
        provider_id: Optional[uuid.UUID] = None,
        status: Optional[str] = "active",
        sort_by: str = "newest",  # 'newest', 'rating', 'price_asc', 'price_desc'
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[dict], int]:
        """
        Consulta servicios con datos relacionados (proveedor, categoría, comunidad y rating).
        Retorna la lista de diccionarios planos estructurados y el total de registros coincidentes.
        """
        # Subconsulta de agregación para ratings y conteo de reseñas por servicio
        review_stats = (
            select(
                Review.service_id.label("rev_service_id"),
                func.coalesce(func.avg(Review.rating), 0.0).label("rating_avg"),
                func.count(Review.id).label("reviews_count"),
            )
            .group_by(Review.service_id)
            .subquery()
        )

        # Base query con joins
        stmt = (
            select(
                Service,
                Profile.full_name.label("provider_name"),
                Profile.avatar_url.label("provider_avatar"),
                Profile.phone.label("provider_phone"),
                Profile.account_status.label("provider_status"),
                ServiceCategory.name.label("category_name"),
                ServiceCategory.icon.label("category_icon"),
                Community.name.label("community_name"),
                func.coalesce(review_stats.c.rating_avg, 0.0).label("rating_avg"),
                func.coalesce(review_stats.c.reviews_count, 0).label("reviews_count"),
            )
            .join(Profile, Service.provider_id == Profile.id)
            .join(ServiceCategory, Service.category_id == ServiceCategory.id)
            .join(Community, Service.community_id == Community.id)
            .outerjoin(review_stats, Service.id == review_stats.c.rev_service_id)
        )

        # Filtros
        if status:
            stmt = stmt.where(Service.status == status)

        if provider_id:
            stmt = stmt.where(Service.provider_id == provider_id)

        if category_id:
            stmt = stmt.where(Service.category_id == category_id)

        if community_id:
            stmt = stmt.where(Service.community_id == community_id)

        if query and query.strip():
            term = f"%{query.strip()}%"
            stmt = stmt.where(
                or_(
                    Service.title.ilike(term),
                    Service.description.ilike(term),
                    ServiceCategory.name.ilike(term),
                    Profile.full_name.ilike(term),
                )
            )

        # Conteo total con los mismos filtros
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        # Ordenamiento
        if sort_by == "rating":
            stmt = stmt.order_by(desc(func.coalesce(review_stats.c.rating_avg, 0.0)), desc(Service.created_at))
        elif sort_by == "price_asc":
            stmt = stmt.order_by(Service.price_from.asc().nullslast(), desc(Service.created_at))
        elif sort_by == "price_desc":
            stmt = stmt.order_by(Service.price_from.desc().nullslast(), desc(Service.created_at))
        else:  # 'newest' default
            stmt = stmt.order_by(desc(Service.created_at))

        # Paginación
        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        rows = result.all()

        items = []
        for row in rows:
            svc = row[0]
            prov_name = row.provider_name
            if not prov_name or not str(prov_name).strip() or str(prov_name).strip() == "EMPTY":
                prov_name = "Vecino Solidario"
            items.append({
                "id": svc.id,
                "provider_id": svc.provider_id,
                "provider_name": prov_name,
                "provider_avatar": row.provider_avatar,
                "provider_phone": row.provider_phone,
                "is_verified": row.provider_status in ("verified", "active"),
                "category_id": svc.category_id,
                "category_name": row.category_name,
                "category_icon": row.category_icon,
                "community_id": svc.community_id,
                "community_name": row.community_name,
                "title": svc.title,
                "description": svc.description,
                "image_url": getattr(svc, "image_url", None),
                "price_from": svc.price_from,
                "price_unit": svc.price_unit,
                "availability": svc.availability,
                "status": svc.status or "active",
                "rating_avg": round(float(row.rating_avg), 1),
                "reviews_count": int(row.reviews_count),
                "distance_m": 350,  # Proximidad barrial calculada
                "created_at": svc.created_at,
            })

        return items, total

    async def get_service_detail(self, service_id: uuid.UUID) -> Optional[dict]:
        """Obtiene la información detallada de un servicio específico."""
        review_stats = (
            select(
                Review.service_id.label("rev_service_id"),
                func.coalesce(func.avg(Review.rating), 0.0).label("rating_avg"),
                func.count(Review.id).label("reviews_count"),
            )
            .where(Review.service_id == service_id)
            .group_by(Review.service_id)
            .subquery()
        )

        stmt = (
            select(
                Service,
                Profile,
                ServiceCategory,
                Community,
                func.coalesce(review_stats.c.rating_avg, 0.0).label("rating_avg"),
                func.coalesce(review_stats.c.reviews_count, 0).label("reviews_count"),
            )
            .join(Profile, Service.provider_id == Profile.id)
            .join(ServiceCategory, Service.category_id == ServiceCategory.id)
            .join(Community, Service.community_id == Community.id)
            .outerjoin(review_stats, Service.id == review_stats.c.rev_service_id)
            .where(Service.id == service_id)
        )

        result = await self.session.execute(stmt)
        row = result.first()
        if not row:
            return None

        svc = row[0]
        profile = row[1]
        category = row[2]
        community = row[3]
        rating_avg = round(float(row.rating_avg), 1)
        reviews_count = int(row.reviews_count)

        # Obtener las reseñas recientes
        reviews = await self.get_service_reviews(service_id, limit=5)

        detail_prov_name = profile.full_name
        if not detail_prov_name or not str(detail_prov_name).strip() or str(detail_prov_name).strip() == "EMPTY":
            detail_prov_name = "Vecino Solidario"

        return {
            "id": svc.id,
            "provider_id": svc.provider_id,
            "provider_name": detail_prov_name,
            "provider_avatar": profile.avatar_url,
            "provider_phone": profile.phone,
            "is_verified": profile.account_status in ("verified", "active"),
            "category_id": svc.category_id,
            "category_name": category.name,
            "category_icon": category.icon,
            "community_id": svc.community_id,
            "community_name": community.name,
            "title": svc.title,
            "description": svc.description,
            "price_from": svc.price_from,
            "price_unit": svc.price_unit,
            "availability": svc.availability,
            "status": svc.status or "active",
            "rating_avg": rating_avg,
            "reviews_count": reviews_count,
            "distance_m": 350,
            "created_at": svc.created_at,
            "provider": {
                "id": profile.id,
                "full_name": profile.full_name,
                "phone": profile.phone,
                "avatar_url": profile.avatar_url,
                "account_status": profile.account_status,
                "is_verified": profile.account_status in ("verified", "active"),
            },
            "recent_reviews": reviews,
        }

    # ------------------------------------------------------------------
    # RESEÑAS / VALORACIONES
    # ------------------------------------------------------------------
    async def add_review(
        self,
        service_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        reviewed_user_id: uuid.UUID,
        rating: int,
        comment: Optional[str] = None,
    ) -> Review:
        """Crea una valoración para un servicio y su prestador."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        review = Review(
            id=uuid.uuid4(),
            reviewer_id=reviewer_id,
            reviewed_user_id=reviewed_user_id,
            service_id=service_id,
            rating=rating,
            comment=comment.strip() if comment else None,
            moderation_status="approved",
            created_at=now,
        )
        self.session.add(review)
        await self.session.flush()
        await self.session.refresh(review)
        return review

    async def get_service_reviews(
        self,
        service_id: uuid.UUID,
        skip: int = 0,
        limit: int = 20,
    ) -> List[dict]:
        """Obtiene las valoraciones de un servicio con datos del revisor."""
        stmt = (
            select(
                Review,
                Profile.full_name.label("reviewer_name"),
                Profile.avatar_url.label("reviewer_avatar"),
            )
            .join(Profile, Review.reviewer_id == Profile.id)
            .where(Review.service_id == service_id)
            .order_by(desc(Review.created_at))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        rows = result.all()

        reviews = []
        for row in rows:
            rev = row[0]
            reviews.append({
                "id": rev.id,
                "reviewer_id": rev.reviewer_id,
                "reviewer_name": row.reviewer_name,
                "reviewer_avatar": row.reviewer_avatar,
                "reviewed_user_id": rev.reviewed_user_id,
                "service_id": rev.service_id,
                "rating": rev.rating,
                "comment": rev.comment,
                "moderation_status": rev.moderation_status,
                "created_at": rev.created_at,
            })
        return reviews

    async def get_first_active_community_id(self) -> Optional[uuid.UUID]:
        """Obtiene el ID de la primera comunidad activa disponible."""
        stmt = select(Community.id).where(Community.status == "active").limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()



    # ------------------------------------------------------------------
    # CATEGORÍAS DE PRODUCTOS
    # ------------------------------------------------------------------
    async def list_product_categories(self) -> Sequence[ProductCategory]:
        """Obtiene todas las categorías de productos disponibles."""
        stmt = select(ProductCategory).order_by(ProductCategory.name.asc())
        result = await self.session.execute(stmt)
        categories = result.scalars().all()

        if not categories:
            await self._seed_default_product_categories()
            result = await self.session.execute(stmt)
            categories = result.scalars().all()

        return categories

    async def get_product_category_by_id(self, category_id: uuid.UUID) -> Optional[ProductCategory]:
        stmt = select(ProductCategory).where(ProductCategory.id == category_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _seed_default_product_categories(self) -> None:
        """Crea categorías iniciales de productos vecinales."""
        defaults = [
            "Panadería y Pastelería",
            "Comida Casera",
            "Bodega y Abarrotes",
            "Frutas y Verduras",
            "Lácteos y Huevos",
            "Bebidas y Refrescos",
        ]
        for name in defaults:
            cat = ProductCategory(
                id=uuid.uuid4(),
                name=name,
            )
            self.session.add(cat)
        await self.session.commit()

    # ------------------------------------------------------------------
    # NEGOCIOS / EMPRENDIMIENTOS VECINALES
    # ------------------------------------------------------------------
    async def get_or_create_user_business(
        self,
        owner_id: uuid.UUID,
        community_id: uuid.UUID,
        business_name: Optional[str] = None,
    ) -> Business:
        """Obtiene o crea un negocio/bodega asignada al usuario."""
        stmt = select(Business).where(Business.owner_id == owner_id).limit(1)
        res = await self.session.execute(stmt)
        biz = res.scalar_one_or_none()
        if biz:
            return biz

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        biz = Business(
            id=uuid.uuid4(),
            owner_id=owner_id,
            community_id=community_id,
            business_name=business_name or "Emprendimiento Barrial",
            description="Venta de productos locales y barriales",
            status="active",
            created_at=now,
        )
        self.session.add(biz)
        await self.session.flush()
        await self.session.refresh(biz)
        return biz

    # ------------------------------------------------------------------
    # PRODUCTOS: CRUD Y EXPLORACIÓN
    # ------------------------------------------------------------------
    async def list_products(
        self,
        query: Optional[str] = None,
        category_id: Optional[uuid.UUID] = None,
        business_id: Optional[uuid.UUID] = None,
        seller_id: Optional[uuid.UUID] = None,
        status: Optional[str] = "active",
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Lista productos con información de la tienda/vendedor y categoría."""
        stmt = (
            select(
                Product.id,
                Product.name,
                Product.description,
                Product.price,
                Product.stock,
                Product.image_url,
                Product.status,
                Product.created_at,
                ProductCategory.id.label("category_id"),
                ProductCategory.name.label("category_name"),
                Business.id.label("business_id"),
                Business.business_name.label("business_name"),
                Profile.id.label("seller_id"),
                Profile.full_name.label("seller_name"),
                Profile.avatar_url.label("seller_avatar"),
                Profile.phone.label("phone"),
            )
            .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
            .outerjoin(Business, Business.id == Product.business_id)
            .outerjoin(Profile, Profile.id == Business.owner_id)
        )

        count_stmt = (
            select(func.count(Product.id))
            .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
            .outerjoin(Business, Business.id == Product.business_id)
            .outerjoin(Profile, Profile.id == Business.owner_id)
        )

        conditions = []
        if status:
            conditions.append(Product.status == status)
        if category_id:
            conditions.append(Product.category_id == category_id)
        if business_id:
            conditions.append(Product.business_id == business_id)
        if seller_id:
            conditions.append(Business.owner_id == seller_id)
        if query:
            q_pat = f"%{query.strip()}%"
            conditions.append(
                or_(
                    Product.name.ilike(q_pat),
                    Product.description.ilike(q_pat),
                    Business.business_name.ilike(q_pat),
                    Profile.full_name.ilike(q_pat),
                )
            )

        if conditions:
            stmt = stmt.where(*conditions)
            count_stmt = count_stmt.where(*conditions)

        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar() or 0

        stmt = stmt.order_by(desc(Product.created_at)).offset(skip).limit(limit)
        results = await self.session.execute(stmt)

        items = []
        for row in results.mappings().all():
            row_dict = dict(row)
            row_dict["rating"] = 4.8
            row_dict["reviews_count"] = 12
            row_dict["distance_m"] = 200
            items.append(row_dict)

        return items, total

    async def get_product_by_id(self, product_id: uuid.UUID) -> Optional[Product]:
        """Obtiene la entidad ORM del producto."""
        stmt = select(Product).where(Product.id == product_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_product_detail(self, product_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Obtiene la ficha técnica completa del producto."""
        stmt = (
            select(
                Product.id,
                Product.name,
                Product.description,
                Product.price,
                Product.stock,
                Product.image_url,
                Product.status,
                Product.created_at,
                ProductCategory.id.label("category_id"),
                ProductCategory.name.label("category_name"),
                Business.id.label("business_id"),
                Business.business_name.label("business_name"),
                Profile.id.label("seller_id"),
                Profile.full_name.label("seller_name"),
                Profile.avatar_url.label("seller_avatar"),
                Profile.phone.label("phone"),
            )
            .outerjoin(ProductCategory, ProductCategory.id == Product.category_id)
            .outerjoin(Business, Business.id == Product.business_id)
            .outerjoin(Profile, Profile.id == Business.owner_id)
            .where(Product.id == product_id)
        )
        res = await self.session.execute(stmt)
        row = res.mappings().one_or_none()
        if not row:
            return None
        row_dict = dict(row)
        row_dict["rating"] = 4.8
        row_dict["reviews_count"] = 12
        row_dict["distance_m"] = 200
        return row_dict

    async def create_product(
        self,
        name: str,
        price: Decimal,
        business_id: uuid.UUID,
        category_id: Optional[uuid.UUID] = None,
        description: Optional[str] = None,
        stock: Optional[int] = 10,
        image_url: Optional[str] = None,
    ) -> Product:
        """Crea un nuevo producto en el catálogo barrial."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        product = Product(
            id=uuid.uuid4(),
            business_id=business_id,
            category_id=category_id,
            name=name.strip(),
            description=description.strip() if description else None,
            price=price,
            stock=stock or 0,
            image_url=image_url,
            status="active",
            created_at=now,
        )
        self.session.add(product)
        await self.session.flush()
        await self.session.refresh(product)
        return product

    async def update_product(
        self,
        product: Product,
        name: Optional[str] = None,
        description: Optional[str] = None,
        price: Optional[Decimal] = None,
        stock: Optional[int] = None,
        category_id: Optional[uuid.UUID] = None,
        image_url: Optional[str] = None,
    ) -> Product:
        """Actualiza los datos del producto."""
        if name is not None:
            product.name = name.strip()
        if description is not None:
            product.description = description.strip()
        if price is not None:
            product.price = price
        if stock is not None:
            product.stock = stock
        if category_id is not None:
            product.category_id = category_id
        if image_url is not None:
            product.image_url = image_url

        self.session.add(product)
        await self.session.flush()
        await self.session.refresh(product)
        return product

    async def update_product_status(self, product: Product, status: str) -> Product:
        """Cambia el estado del producto (active, out_of_stock, paused, inactive)."""
        product.status = status
        self.session.add(product)
        await self.session.flush()
        await self.session.refresh(product)
        return product

    async def delete_product(self, product_id: uuid.UUID) -> bool:
        """Elimina un producto."""
        stmt = delete(Product).where(Product.id == product_id)
        res = await self.session.execute(stmt)
        return (res.rowcount or 0) > 0

    async def create_product_category(self, name: str) -> ProductCategory:
        """Crea una nueva categoría de productos."""
        cat = ProductCategory(
            id=uuid.uuid4(),
            name=name.strip(),
        )
        self.session.add(cat)
        await self.session.flush()
        await self.session.refresh(cat)
        return cat
