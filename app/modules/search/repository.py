"""Repositorio de acceso a datos para el motor de búsqueda inteligente geolocalizada."""
import math
import unicodedata
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Tuple
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.models import AIRecommendation
from app.modules.commerce.models import (
    Business,
    Order,
    Product,
    ProductCategory,
    Service,
    ServiceCategory,
)
from app.modules.emergencies.models import Emergency
from app.modules.geo.models import Address, Community, District
from app.modules.interactions.models import Review
from app.modules.solidarity.models import SolidarityPost
from app.modules.users.models import Profile, UserAddress


# Diccionario barrial de sinónimos y afinidad semántica
SYNONYM_MAP: Dict[str, List[str]] = {
    "gasfitero": ["gasfiteria", "plomero", "plomeria", "tuberia", "fuga", "desague", "cano"],
    "gasfiteria": ["gasfitero", "plomero", "plomeria", "tuberia", "fuga", "desague", "cano"],
    "plomero": ["gasfitero", "gasfiteria", "plomeria", "tuberia", "fuga"],
    "electricista": ["electricidad", "cableado", "luz", "corto", "tablero", "tomacorriente", "enchufe"],
    "electricidad": ["electricista", "cableado", "luz", "corto", "tablero"],
    "enfermera": ["enfermeria", "inyectable", "primeros auxilios", "salud", "presion", "curacion"],
    "enfermeria": ["enfermera", "inyectable", "primeros auxilios", "salud", "presion"],
    "profesor": ["docente", "clases", "apoyo escolar", "tutor", "ensenanza", "colegio", "tareas", "matematicas"],
    "docente": ["profesor", "clases", "apoyo escolar", "tutor", "ensenanza"],
    "costura": ["costurera", "confeccion", "sastre", "reparacion de ropa", "basta", "cremallera"],
    "costurera": ["costura", "confeccion", "sastre", "reparacion de ropa", "basta"],
    "comida": ["reposteria", "cocina", "menu", "almuerzo", "postres", "tortas", "queques", "panaderia"],
    "reposteria": ["comida", "cocina", "postres", "tortas", "queques", "pasteleria"],
    "albanil": ["albanileria", "construccion", "cemento", "pintura", "tarrajeo", "pared", "piso", "ceramico"],
    "albanileria": ["albanil", "construccion", "cemento", "pintura", "tarrajeo"],
    "mascotas": ["veterinaria", "perro", "gato", "paseador", "bano de perro", "vacunacion"],
    "veterinaria": ["mascotas", "perro", "gato", "vacunacion", "salud animal"],
    "medico": ["doctor", "ambulancia", "emergencia", "primeros auxilios", "salud", "posta"],
    "seguridad": ["alarma", "serenazgo", "policia", "sos", "asalto", "sospechoso", "camara", "vigilancia"],
    "robo": ["seguridad", "alarma", "serenazgo", "policia", "sos", "asalto"],
    "incendio": ["bomberos", "fuego", "humo", "evacuacion", "urgencia", "emergencia"],
    "herramientas": ["taladro", "escalera", "martillo", "prestamo", "llaves", "pala"],
    "cerrajero": ["cerrajeria", "cerrajería", "cerradura", "llave", "llaves", "candado"],
    "cerrajeria": ["cerrajero", "cerrajería", "cerradura", "llave", "llaves", "candado"],
    "cerrajería": ["cerrajero", "cerrajeria", "cerradura", "llave", "llaves", "candado"],
}


def strip_accents(text: str) -> str:
    """Elimina tildes y diacríticos preservando caracteres alfanuméricos."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def expand_query_terms(query: Optional[str]) -> List[str]:
    """Expande la búsqueda con variantes con/sin acentos y sinónimos contextuales peruanos."""
    if not query or not query.strip():
        return []

    q_lower = query.strip().lower()
    clean = strip_accents(query.strip())
    
    raw_tokens = [t for t in q_lower.split() if len(t) > 1]
    clean_tokens = [t for t in clean.split() if len(t) > 1]
    
    expanded = set(raw_tokens) | set(clean_tokens)

    # Agregar el término completo si es de varias palabras
    if len(clean_tokens) > 1:
        expanded.add(clean)
        expanded.add(q_lower)

    # Generar variantes fonéticas comunes de acentuación en español
    accent_replacements = [
        ("ia", "ía"), ("ía", "ia"),
        ("on", "ón"), ("ón", "on"),
        ("eria", "ería"), ("ería", "eria"),
        ("acion", "ación"), ("ación", "acion")
    ]
    variants = set()
    for tok in list(expanded):
        for old, new in accent_replacements:
            if old in tok:
                variants.add(tok.replace(old, new))
    expanded.update(variants)

    for token in list(expanded):
        if token in SYNONYM_MAP:
            for syn in SYNONYM_MAP[token]:
                expanded.add(syn)
        stripped = strip_accents(token)
        if stripped in SYNONYM_MAP:
            for syn in SYNONYM_MAP[stripped]:
                expanded.add(syn)

    return list(expanded)


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcula la distancia real en metros usando la fórmula del semiverseno (Haversine)."""
    R = 6371000.0  # Radio terrestre medio en metros
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(min(1.0, max(0.0, a))), math.sqrt(min(1.0, max(0.0, 1.0 - a))))
    return round(R * c, 1)


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcula la distancia real en kilómetros con resolución métrica."""
    meters = haversine_distance_meters(lat1, lon1, lat2, lon2)
    return round(meters / 1000.0, 3)


class SearchRepository:
    """Acceso a datos para búsqueda en servicios, productos, solidaridad y emergencias."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------
    # SERVICIOS
    # ------------------------------------------------------------------
    async def search_services_raw(
        self,
        query: Optional[str] = None,
        category_id: Optional[uuid.UUID] = None,
        community_id: Optional[uuid.UUID] = None,
    ) -> List[Dict[str, Any]]:
        """Recupera candidatos de servicios con métricas de reputación, experiencia y geolocalización."""
        # 1. Subconsulta de reseñas de servicios aprobadas
        review_sub = (
            select(
                Review.service_id,
                func.count(Review.id).label("reviews_count"),
                func.coalesce(func.avg(Review.rating), 0.0).label("rating_avg"),
            )
            .where(
                or_(
                    Review.moderation_status.in_(["approved", "active"]),
                    Review.moderation_status.is_(None),
                )
            )
            .group_by(Review.service_id)
            .subquery()
        )

        # 2. Subconsulta de recomendaciones IA precalculadas
        ai_sub = (
            select(
                AIRecommendation.service_id,
                func.max(AIRecommendation.score).label("ai_score"),
            )
            .where(AIRecommendation.service_id.is_not(None))
            .group_by(AIRecommendation.service_id)
            .subquery()
        )

        # 3. Consulta principal
        addr_svc = Address.__table__.alias("addr_svc")
        addr_usr = Address.__table__.alias("addr_usr")
        district_alias = District.__table__.alias("dist_svc")

        stmt = (
            select(
                Service,
                ServiceCategory.name.label("category_name"),
                ServiceCategory.icon.label("category_icon"),
                Profile.full_name.label("provider_name"),
                Profile.avatar_url.label("provider_avatar"),
                Profile.phone.label("provider_phone"),
                Profile.account_status.label("provider_status"),
                Profile.solidarity_helped_count.label("provider_helped_count"),
                Profile.created_at.label("provider_created_at"),
                Community.name.label("community_name"),
                district_alias.c.name.label("district_name"),
                func.coalesce(addr_svc.c.latitude, addr_usr.c.latitude).label("latitude"),
                func.coalesce(addr_svc.c.longitude, addr_usr.c.longitude).label("longitude"),
                func.coalesce(addr_svc.c.street_address, addr_usr.c.street_address).label("street_address"),
                func.coalesce(review_sub.c.reviews_count, 0).label("reviews_count"),
                func.coalesce(review_sub.c.rating_avg, 0.0).label("rating_avg"),
                ai_sub.c.ai_score.label("ai_score"),
            )
            .select_from(Service)
            .join(ServiceCategory, Service.category_id == ServiceCategory.id)
            .join(Profile, Service.provider_id == Profile.id)
            .join(Community, Service.community_id == Community.id)
            .outerjoin(addr_svc, Service.address_id == addr_svc.c.id)
            .outerjoin(
                UserAddress,
                (UserAddress.user_id == Profile.id) & (UserAddress.is_primary.is_(True)),
            )
            .outerjoin(addr_usr, UserAddress.address_id == addr_usr.c.id)
            .outerjoin(
                district_alias,
                func.coalesce(addr_svc.c.district_id, addr_usr.c.district_id) == district_alias.c.id,
            )
            .outerjoin(review_sub, Service.id == review_sub.c.service_id)
            .outerjoin(ai_sub, Service.id == ai_sub.c.service_id)
            .where(or_(Service.status.is_(None), Service.status.in_(["active", "published"])))
        )

        if category_id:
            stmt = stmt.where(Service.category_id == category_id)
        if community_id:
            stmt = stmt.where(Service.community_id == community_id)

        # Filtro de texto inicial amplio (se refina y rankea en Python)
        tokens = expand_query_terms(query)
        if tokens:
            conditions = []
            for t in tokens:
                pattern = f"%{t}%"
                conditions.extend([
                    Service.title.ilike(pattern),
                    Service.description.ilike(pattern),
                    ServiceCategory.name.ilike(pattern),
                    Profile.full_name.ilike(pattern),
                ])
            stmt = stmt.where(or_(*conditions))

        stmt = stmt.order_by(desc(Service.created_at)).limit(150)

        result = await self.session.execute(stmt)
        rows = result.all()

        candidates = []
        for row in rows:
            svc = row[0]
            lat = float(row.latitude) if row.latitude is not None else None
            lon = float(row.longitude) if row.longitude is not None else None

            candidates.append({
                "id": svc.id,
                "title": svc.title,
                "description": svc.description,
                "category_id": svc.category_id,
                "category_name": row.category_name,
                "category_icon": row.category_icon,
                "price_from": svc.price_from,
                "price_unit": svc.price_unit,
                "availability": svc.availability,
                "provider_id": svc.provider_id,
                "provider_name": row.provider_name or "Vecino Prestador",
                "provider_avatar": row.provider_avatar,
                "provider_phone": row.provider_phone,
                "provider_status": row.provider_status,
                "provider_helped_count": int(row.provider_helped_count or 0),
                "provider_created_at": row.provider_created_at,
                "community_id": svc.community_id,
                "community_name": row.community_name,
                "district_name": row.district_name,
                "latitude": lat,
                "longitude": lon,
                "street_address": row.street_address,
                "reviews_count": int(row.reviews_count),
                "rating_avg": round(float(row.rating_avg), 2),
                "ai_score": float(row.ai_score) if row.ai_score is not None else None,
                "created_at": svc.created_at,
            })

        return candidates

    # ------------------------------------------------------------------
    # PRODUCTOS
    # ------------------------------------------------------------------
    async def search_products_raw(
        self,
        query: Optional[str] = None,
        category_id: Optional[uuid.UUID] = None,
        community_id: Optional[uuid.UUID] = None,
    ) -> List[Dict[str, Any]]:
        """Recupera candidatos de productos y negocios barriales con sus coordenadas y reputación."""
        review_sub = (
            select(
                Review.reviewed_user_id,
                func.count(Review.id).label("reviews_count"),
                func.coalesce(func.avg(Review.rating), 0.0).label("rating_avg"),
            )
            .where(
                or_(
                    Review.moderation_status.in_(["approved", "active"]),
                    Review.moderation_status.is_(None),
                )
            )
            .group_by(Review.reviewed_user_id)
            .subquery()
        )

        ai_sub = (
            select(
                AIRecommendation.product_id,
                func.max(AIRecommendation.score).label("ai_score"),
            )
            .where(AIRecommendation.product_id.is_not(None))
            .group_by(AIRecommendation.product_id)
            .subquery()
        )

        addr_biz = Address.__table__.alias("addr_biz")
        district_alias = District.__table__.alias("dist_biz")

        stmt = (
            select(
                Product,
                ProductCategory.name.label("category_name"),
                Business.id.label("business_id"),
                Business.business_name.label("business_name"),
                Business.owner_id.label("owner_id"),
                Profile.full_name.label("owner_name"),
                Profile.account_status.label("owner_status"),
                Profile.created_at.label("owner_created_at"),
                Community.name.label("community_name"),
                district_alias.c.name.label("district_name"),
                addr_biz.c.latitude.label("latitude"),
                addr_biz.c.longitude.label("longitude"),
                addr_biz.c.street_address.label("street_address"),
                func.coalesce(review_sub.c.reviews_count, 0).label("reviews_count"),
                func.coalesce(review_sub.c.rating_avg, 0.0).label("rating_avg"),
                ai_sub.c.ai_score.label("ai_score"),
            )
            .select_from(Product)
            .outerjoin(ProductCategory, Product.category_id == ProductCategory.id)
            .outerjoin(Business, Product.business_id == Business.id)
            .outerjoin(Profile, Business.owner_id == Profile.id)
            .outerjoin(Community, Business.community_id == Community.id)
            .outerjoin(addr_biz, Business.address_id == addr_biz.c.id)
            .outerjoin(district_alias, addr_biz.c.district_id == district_alias.c.id)
            .outerjoin(review_sub, Business.owner_id == review_sub.c.reviewed_user_id)
            .outerjoin(ai_sub, Product.id == ai_sub.c.product_id)
            .where(or_(Product.status.is_(None), Product.status.in_(["active", "available"])))
        )

        if category_id:
            stmt = stmt.where(Product.category_id == category_id)
        if community_id:
            stmt = stmt.where(Business.community_id == community_id)

        tokens = expand_query_terms(query)
        if tokens:
            conditions = []
            for t in tokens:
                pattern = f"%{t}%"
                conditions.extend([
                    Product.name.ilike(pattern),
                    Product.description.ilike(pattern),
                    ProductCategory.name.ilike(pattern),
                    Business.business_name.ilike(pattern),
                ])
            stmt = stmt.where(or_(*conditions))

        stmt = stmt.order_by(desc(Product.created_at)).limit(150)

        result = await self.session.execute(stmt)
        rows = result.all()

        candidates = []
        for row in rows:
            prod = row[0]
            lat = float(row.latitude) if row.latitude is not None else None
            lon = float(row.longitude) if row.longitude is not None else None

            candidates.append({
                "id": prod.id,
                "name": prod.name,
                "description": prod.description,
                "price": prod.price,
                "stock": prod.stock,
                "image_url": prod.image_url,
                "category_id": prod.category_id,
                "category_name": row.category_name,
                "business_id": row.business_id,
                "business_name": row.business_name or "Comercio Vecinal",
                "owner_id": row.owner_id,
                "owner_name": row.owner_name or "Vecino Emprendedor",
                "owner_status": row.owner_status,
                "owner_created_at": row.owner_created_at,
                "community_name": row.community_name,
                "district_name": row.district_name,
                "latitude": lat,
                "longitude": lon,
                "street_address": row.street_address,
                "reviews_count": int(row.reviews_count),
                "rating_avg": round(float(row.rating_avg), 2),
                "ai_score": float(row.ai_score) if row.ai_score is not None else None,
                "created_at": prod.created_at,
            })

        return candidates

    # ------------------------------------------------------------------
    # AYUDA SOLIDARIA
    # ------------------------------------------------------------------
    async def search_solidarity_raw(
        self,
        query: Optional[str] = None,
        post_type: Optional[str] = None,
        community_id: Optional[uuid.UUID] = None,
    ) -> List[Dict[str, Any]]:
        """Recupera publicaciones solidarias priorizando necesidades urgentes."""
        addr_alias = Address.__table__.alias("addr_sol")
        dist_alias = District.__table__.alias("dist_sol")

        stmt = (
            select(
                SolidarityPost,
                Profile.full_name.label("author_name"),
                Profile.avatar_url.label("author_avatar"),
                Profile.account_status.label("author_status"),
                Profile.solidarity_helped_count.label("author_helped_count"),
                Community.name.label("community_name"),
                dist_alias.c.name.label("district_name"),
                addr_alias.c.latitude.label("latitude"),
                addr_alias.c.longitude.label("longitude"),
            )
            .select_from(SolidarityPost)
            .join(Profile, SolidarityPost.author_id == Profile.id)
            .join(Community, SolidarityPost.community_id == Community.id)
            .outerjoin(
                UserAddress,
                (UserAddress.user_id == Profile.id) & (UserAddress.is_primary.is_(True)),
            )
            .outerjoin(addr_alias, UserAddress.address_id == addr_alias.c.id)
            .outerjoin(dist_alias, addr_alias.c.district_id == dist_alias.c.id)
            .where(or_(SolidarityPost.status.is_(None), SolidarityPost.status.in_(["active", "open", "in_progress"])))
        )

        if post_type:
            stmt = stmt.where(SolidarityPost.post_type == post_type)
        if community_id:
            stmt = stmt.where(SolidarityPost.community_id == community_id)

        tokens = expand_query_terms(query)
        if tokens:
            conditions = []
            for t in tokens:
                pattern = f"%{t}%"
                conditions.extend([
                    SolidarityPost.title.ilike(pattern),
                    SolidarityPost.description.ilike(pattern),
                    SolidarityPost.category.ilike(pattern),
                ])
            stmt = stmt.where(or_(*conditions))

        stmt = stmt.order_by(desc(SolidarityPost.created_at)).limit(100)

        result = await self.session.execute(stmt)
        rows = result.all()

        candidates = []
        for row in rows:
            post = row[0]
            lat = float(row.latitude) if row.latitude is not None else None
            lon = float(row.longitude) if row.longitude is not None else None

            candidates.append({
                "id": post.id,
                "title": post.title,
                "description": post.description,
                "category": post.category,
                "post_type": post.post_type,
                "status": post.status or "open",
                "author_id": post.author_id,
                "author_name": row.author_name or "Vecino Solidario",
                "author_avatar": row.author_avatar,
                "author_status": row.author_status,
                "author_helped_count": int(row.author_helped_count or 0),
                "community_id": post.community_id,
                "community_name": row.community_name,
                "district_name": row.district_name,
                "latitude": lat,
                "longitude": lon,
                "created_at": post.created_at,
            })

        return candidates

    # ------------------------------------------------------------------
    # EMERGENCIAS
    # ------------------------------------------------------------------
    async def search_emergencies_raw(
        self,
        query: Optional[str] = None,
        severity: Optional[str] = None,
        community_id: Optional[uuid.UUID] = None,
    ) -> List[Dict[str, Any]]:
        """Recupera emergencias barriales priorizando gravedad y cercanía."""
        addr_alias = Address.__table__.alias("addr_emg")
        dist_alias = District.__table__.alias("dist_emg")

        stmt = (
            select(
                Emergency,
                Profile.full_name.label("reporter_name"),
                Profile.phone.label("reporter_phone"),
                Community.name.label("community_name"),
                dist_alias.c.name.label("district_name"),
                addr_alias.c.latitude.label("latitude"),
                addr_alias.c.longitude.label("longitude"),
                addr_alias.c.street_address.label("street_address"),
            )
            .select_from(Emergency)
            .join(Profile, Emergency.reported_by == Profile.id)
            .join(Community, Emergency.community_id == Community.id)
            .outerjoin(addr_alias, Emergency.address_id == addr_alias.c.id)
            .outerjoin(dist_alias, addr_alias.c.district_id == dist_alias.c.id)
            .where(or_(Emergency.status.is_(None), Emergency.status.in_(["active", "reported", "reportada", "in_progress", "en_atencion"])))
        )

        if severity:
            stmt = stmt.where(Emergency.severity == severity)
        if community_id:
            stmt = stmt.where(Emergency.community_id == community_id)

        tokens = expand_query_terms(query)
        if tokens:
            conditions = []
            for t in tokens:
                pattern = f"%{t}%"
                conditions.extend([
                    Emergency.title.ilike(pattern),
                    Emergency.description.ilike(pattern),
                    Emergency.emergency_type.ilike(pattern),
                ])
            stmt = stmt.where(or_(*conditions))

        stmt = stmt.order_by(desc(Emergency.created_at)).limit(100)

        result = await self.session.execute(stmt)
        rows = result.all()

        candidates = []
        for row in rows:
            emg = row[0]
            lat = float(row.latitude) if row.latitude is not None else None
            lon = float(row.longitude) if row.longitude is not None else None

            candidates.append({
                "id": emg.id,
                "title": emg.title,
                "description": emg.description,
                "emergency_type": emg.emergency_type,
                "severity": emg.severity or "medium",
                "status": emg.status or "active",
                "reported_by": emg.reported_by,
                "reporter_name": row.reporter_name or "Vecino Alerta",
                "reporter_phone": row.reporter_phone,
                "community_id": emg.community_id,
                "community_name": row.community_name,
                "district_name": row.district_name,
                "street_address": row.street_address,
                "image_url": emg.image_url,
                "latitude": lat,
                "longitude": lon,
                "occurred_at": emg.occurred_at,
                "created_at": emg.created_at,
            })

        return candidates

