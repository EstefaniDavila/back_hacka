"""Servicio de lógica de negocio y ranking para el motor de búsqueda inteligente."""
import difflib
import math
import uuid
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.search.repository import (
    SearchRepository,
    expand_query_terms,
    haversine_distance_km,
    haversine_distance_meters,
    strip_accents,
)
from app.modules.search.schemas import (
    EmergencySearchResult,
    GlobalSearchResponse,
    PaginatedEmergenciesSearch,
    PaginatedProductsSearch,
    PaginatedServicesSearch,
    PaginatedSolidaritySearch,
    ProductSearchResult,
    SearchLocationMeta,
    SearchPaginationMeta,
    SearchSort,
    ServiceSearchResult,
    SolidaritySearchResult,
    UnifiedSearchResultItem,
)


class SearchService:
    """
    Servicio de búsqueda inteligente geolocalizada con ranking multidimensional ponderado:
    - Coincidencia textual (40%)
    - Proximidad barrial (25%)
    - Reputación bayesiana (25%)
    - Experiencia comprobada (10%)
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = SearchRepository(session)

    # ------------------------------------------------------------------
    # MÉTODOS AUXILIARES DE RANKING Y PUNTUACIÓN
    # ------------------------------------------------------------------
    def _calculate_text_match_score(
        self,
        query: Optional[str],
        title: str,
        description: Optional[str] = None,
        category: Optional[str] = None,
        extra: Optional[str] = None,
    ) -> float:
        """Calcula la coincidencia semántica y difusa entre 0.0 y 1.0 sin llamadas externas."""
        if not query or not query.strip():
            return 1.0

        q_clean = strip_accents(query.strip())
        t_clean = strip_accents(title or "")
        c_clean = strip_accents(category or "")
        d_clean = strip_accents(description or "")
        e_clean = strip_accents(extra or "")

        # 1. Coincidencia exacta de frase en título
        if q_clean == t_clean:
            return 1.0
        if q_clean in t_clean:
            return 0.95

        # 2. Coincidencia exacta de frase en categoría
        if q_clean == c_clean or q_clean in c_clean:
            return 0.90

        # 3. Tokenización y búsqueda expandida con sinónimos
        q_tokens = [t for t in q_clean.split() if len(t) > 1]
        expanded_tokens = expand_query_terms(query)

        token_hits = 0
        total_tokens = max(1, len(q_tokens))

        for t in q_tokens:
            if t in t_clean:
                token_hits += 1.0
            elif t in c_clean:
                token_hits += 0.85
            elif t in d_clean:
                token_hits += 0.65
            elif t in e_clean:
                token_hits += 0.50

        token_score = min(1.0, token_hits / total_tokens)

        # 4. Chequeo de sinónimos si los tokens directos no alcanzaron el 100%
        synonym_bonus = 0.0
        for syn in expanded_tokens:
            if syn not in q_tokens:
                if syn in t_clean:
                    synonym_bonus = max(synonym_bonus, 0.80)
                elif syn in c_clean:
                    synonym_bonus = max(synonym_bonus, 0.75)
                elif syn in d_clean:
                    synonym_bonus = max(synonym_bonus, 0.60)

        # 5. Similitud trigrama / difusa con el título para mitigar errores ortográficos
        fuzzy_sim = difflib.SequenceMatcher(None, q_clean, t_clean).ratio()
        fuzzy_score = (fuzzy_sim * 0.85) if fuzzy_sim >= 0.45 else 0.0

        best_score = max(token_score, synonym_bonus, fuzzy_score)
        return round(min(1.0, max(0.0, best_score)), 3)

    def _calculate_distance_and_score(
        self,
        user_lat: Optional[float],
        user_lon: Optional[float],
        item_lat: Optional[float],
        item_lon: Optional[float],
        radius_km: Optional[float] = None,
    ) -> Tuple[Optional[float], Optional[float], float, bool]:
        """
        Retorna (distance_km, distance_meters, distance_score, within_radius).
        - Mide la distancia real en metros entre el GPS del usuario y las coordenadas de la publicación o vecino.
        - Excluye resultados fuera del radio seleccionado (mínimo 1 km o superior).
        - No inventa distancias ficticias cuando no hay coordenadas GPS.
        """
        if user_lat is None or user_lon is None or item_lat is None or item_lon is None:
            if radius_km is not None:
                # Con radio de filtrado estricto, sin GPS se descarta
                return None, None, 0.0, False
            return None, None, 0.50, True

        dist_meters = haversine_distance_meters(user_lat, user_lon, item_lat, item_lon)
        dist_km = round(dist_meters / 1000.0, 3)

        # Excluir resultados fuera del radio seleccionado
        if radius_km is not None:
            max_meters = radius_km * 1000.0
            if dist_meters > max_meters:
                return dist_km, dist_meters, 0.0, False

        # Normalización continua y equitativa de proximidad (0.0 a 1.0)
        eff_radius_m = (radius_km * 1000.0) if radius_km else 5000.0
        # A 0 m -> 1.0; a eff_radius_m -> 0.0
        dist_score = max(0.0, min(1.0, 1.0 - (dist_meters / eff_radius_m)))

        return dist_km, dist_meters, round(dist_score, 4), True

    def _calculate_bayesian_reputation(
        self,
        reviews_count: int,
        rating_avg: float,
        prior_mean: float = 4.2,
        min_reviews_threshold: int = 3,
    ) -> Tuple[float, float, bool]:
        """
        Calcula el promedio ponderado bayesiano de reputación y detecta usuarios nuevos.
        Retorna (bayesian_rating_1_to_5, reputation_score_0_to_1, is_new).
        No penaliza a nuevos vecinos (les asigna línea base justa de 4.2 estrellas / 0.84).
        """
        if reviews_count == 0:
            return prior_mean, 0.84, True

        v = float(reviews_count)
        r = float(rating_avg)
        m = float(min_reviews_threshold)
        c = float(prior_mean)

        bayesian_rating = (v * r + m * c) / (v + m)
        reputation_score = bayesian_rating / 5.0
        return round(bayesian_rating, 2), round(min(1.0, max(0.1, reputation_score)), 3), False

    def _calculate_experience_score(self, completed_interactions: int, is_new: bool = False) -> float:
        """Puntúa la experiencia comprobada sin penalizar a nuevos vecinos."""
        if is_new or completed_interactions <= 0:
            return 0.70  # Línea base positiva para nuevos vecinos
        # 1 trabajo = 0.73 | 5 trabajos = 0.85 | 10+ trabajos = 1.0
        score = 0.70 + 0.03 * min(10, completed_interactions)
        return round(min(1.0, score), 3)

    # ------------------------------------------------------------------
    # 1. BÚSQUEDA DE SERVICIOS
    # ------------------------------------------------------------------
    async def search_services(
        self,
        query: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius_km: Optional[float] = None,
        category_id: Optional[uuid.UUID] = None,
        community_id: Optional[uuid.UUID] = None,
        sort: SearchSort = SearchSort.RECOMMENDED,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedServicesSearch:
        """Búsqueda especializada en oficios y servicios comunitarios."""
        raw_items = await self.repository.search_services_raw(
            query=query,
            category_id=category_id,
            community_id=community_id,
        )

        ranked: List[ServiceSearchResult] = []

        for item in raw_items:
            dist_km, dist_meters, dist_score, within_radius = self._calculate_distance_and_score(
                latitude, longitude, item["latitude"], item["longitude"], radius_km
            )
            if not within_radius:
                continue

            match_score = self._calculate_text_match_score(
                query,
                item["title"],
                item["description"],
                item["category_name"],
                item["provider_name"],
            )

            # Si se buscó un término específico y la coincidencia es nula, descartar
            if query and query.strip() and match_score < 0.15:
                continue

            bayes_rating, rep_score, is_new = self._calculate_bayesian_reputation(
                item["reviews_count"], item["rating_avg"]
            )

            completed = item["reviews_count"] + item["provider_helped_count"]
            exp_score = self._calculate_experience_score(completed, is_new=is_new)

            # Ponderación requerida:
            # 55% Proximidad
            # 25% Relevancia
            # 15% Reputación
            # 5% Experiencia
            final_score = (
                0.55 * dist_score
                + 0.25 * match_score
                + 0.15 * rep_score
                + 0.05 * exp_score
            )

            if item["ai_score"] is not None:
                final_score = min(1.0, final_score + 0.03 * item["ai_score"])

            final_score = min(1.0, max(0.0, final_score))
            score_val = round(final_score, 4)
            is_verified = item["provider_status"] in ("verified", "active")

            ranked.append(
                ServiceSearchResult(
                    id=item["id"],
                    title=item["title"],
                    description=item["description"],
                    category_id=item["category_id"],
                    category_name=item["category_name"],
                    category_icon=item["category_icon"],
                    price_from=item["price_from"],
                    price_unit=item["price_unit"],
                    availability=item["availability"],
                    provider_id=item["provider_id"],
                    provider_name=item["provider_name"],
                    provider_avatar=item["provider_avatar"],
                    provider_phone=item["provider_phone"],
                    is_verified=is_verified,
                    is_new=is_new,
                    rating_avg=item["rating_avg"],
                    reviews_count=item["reviews_count"],
                    bayesian_rating=bayes_rating,
                    completed_interactions=completed,
                    distance_km=dist_km,
                    distance_meters=dist_meters,
                    community_id=item["community_id"],
                    community_name=item["community_name"],
                    district_name=item["district_name"],
                    score=score_val,
                    ranking_score=score_val,
                    score_breakdown={
                        "match_score": match_score,
                        "distance_score": dist_score,
                        "reputation_score": rep_score,
                        "experience_score": exp_score,
                        "distance_meters": dist_meters,
                        "final_score": score_val,
                        "algorithm_notes": f"55% prox ({dist_meters}m), 25% rel, 15% rep, 5% exp",
                    },
                    created_at=item["created_at"],
                )
            )

        # Ordenamiento
        self._sort_items(ranked, sort)

        # Paginación
        total = len(ranked)
        skip = (page - 1) * page_size
        paginated_items = ranked[skip : skip + page_size]
        total_pages = max(1, math.ceil(total / page_size))

        return PaginatedServicesSearch(
            items=paginated_items,
            meta=SearchPaginationMeta(
                total=total,
                page=page,
                limit=page_size,
                total_pages=total_pages,
            ),
            location_applied=SearchLocationMeta(
                latitude=latitude,
                longitude=longitude,
                radius_km=radius_km,
            ),
            sort_applied=sort.value,
        )

    # ------------------------------------------------------------------
    # 2. BÚSQUEDA DE PRODUCTOS
    # ------------------------------------------------------------------
    async def search_products(
        self,
        query: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius_km: Optional[float] = None,
        category_id: Optional[uuid.UUID] = None,
        community_id: Optional[uuid.UUID] = None,
        sort: SearchSort = SearchSort.RECOMMENDED,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedProductsSearch:
        """Búsqueda especializada en productos y comercios barriales."""
        raw_items = await self.repository.search_products_raw(
            query=query,
            category_id=category_id,
            community_id=community_id,
        )

        ranked: List[ProductSearchResult] = []

        for item in raw_items:
            dist_km, dist_meters, dist_score, within_radius = self._calculate_distance_and_score(
                latitude, longitude, item["latitude"], item["longitude"], radius_km
            )
            if not within_radius:
                continue

            match_score = self._calculate_text_match_score(
                query,
                item["name"],
                item["description"],
                item["category_name"],
                item["business_name"],
            )

            if query and query.strip() and match_score < 0.15:
                continue

            bayes_rating, rep_score, is_new = self._calculate_bayesian_reputation(
                item["reviews_count"], item["rating_avg"]
            )

            exp_score = self._calculate_experience_score(item["reviews_count"], is_new=is_new)
            # Ponderación requerida: 55% Proximidad, 25% Relevancia, 15% Reputación, 5% Experiencia
            final_score = (
                0.55 * dist_score
                + 0.25 * match_score
                + 0.15 * rep_score
                + 0.05 * exp_score
            )

            if item["ai_score"] is not None:
                final_score = min(1.0, final_score + 0.03 * item["ai_score"])

            final_score = min(1.0, max(0.0, final_score))
            score_val = round(final_score, 4)
            is_verified = item["owner_status"] in ("verified", "active")

            ranked.append(
                ProductSearchResult(
                    id=item["id"],
                    name=item["name"],
                    description=item["description"],
                    price=item["price"],
                    stock=item["stock"],
                    image_url=item["image_url"],
                    business_id=item["business_id"],
                    business_name=item["business_name"],
                    category_id=item["category_id"],
                    category_name=item["category_name"],
                    owner_id=item["owner_id"],
                    owner_name=item["owner_name"],
                    is_verified=is_verified,
                    is_new=is_new,
                    rating_avg=item["rating_avg"],
                    reviews_count=item["reviews_count"],
                    bayesian_rating=bayes_rating,
                    distance_km=dist_km,
                    distance_meters=dist_meters,
                    community_name=item["community_name"],
                    district_name=item["district_name"],
                    score=score_val,
                    ranking_score=score_val,
                    score_breakdown={
                        "match_score": match_score,
                        "distance_score": dist_score,
                        "reputation_score": rep_score,
                        "experience_score": exp_score,
                        "distance_meters": dist_meters,
                        "final_score": score_val,
                        "algorithm_notes": f"55% prox ({dist_meters}m), 25% rel, 15% rep, 5% exp",
                    },
                    created_at=item["created_at"],
                )
            )

        self._sort_items(ranked, sort)

        total = len(ranked)
        skip = (page - 1) * page_size
        paginated_items = ranked[skip : skip + page_size]
        total_pages = max(1, math.ceil(total / page_size))

        return PaginatedProductsSearch(
            items=paginated_items,
            meta=SearchPaginationMeta(
                total=total,
                page=page,
                limit=page_size,
                total_pages=total_pages,
            ),
            location_applied=SearchLocationMeta(
                latitude=latitude,
                longitude=longitude,
                radius_km=radius_km,
            ),
            sort_applied=sort.value,
        )

    # ------------------------------------------------------------------
    # 3. BÚSQUEDA DE SOLIDARIDAD
    # ------------------------------------------------------------------
    async def search_solidarity(
        self,
        query: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius_km: Optional[float] = None,
        post_type: Optional[str] = None,
        community_id: Optional[uuid.UUID] = None,
        sort: SearchSort = SearchSort.RECOMMENDED,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedSolidaritySearch:
        """Búsqueda en el muro solidario. No usa estrellas para ordenar necesidades urgentes."""
        raw_items = await self.repository.search_solidarity_raw(
            query=query,
            post_type=post_type,
            community_id=community_id,
        )

        ranked: List[SolidaritySearchResult] = []

        for item in raw_items:
            dist_km, dist_meters, dist_score, within_radius = self._calculate_distance_and_score(
                latitude, longitude, item["latitude"], item["longitude"], radius_km
            )
            if not within_radius:
                continue

            match_score = self._calculate_text_match_score(
                query,
                item["title"],
                item["description"],
                item["category"],
            )

            if query and query.strip() and match_score < 0.15:
                continue

            # Prioridad de urgencia: pedidos de auxilio tienen mayor ponderación que ofertas
            is_urgent = item["post_type"] in ("request", "necesidad", "urgencia")
            type_weight = 1.0 if is_urgent else 0.70
            status_weight = 1.0 if item["status"] in ("open", "active") else 0.40
            urgency_score = round(type_weight * status_weight, 3)

            # Fórmula Solidaridad: 55% Proximidad, 25% Coincidencia, 20% Urgencia
            final_score = (
                0.55 * dist_score
                + 0.25 * match_score
                + 0.20 * urgency_score
            )
            final_score = min(1.0, max(0.0, final_score))
            score_val = round(final_score, 4)

            is_verified = item["author_status"] in ("verified", "active")

            ranked.append(
                SolidaritySearchResult(
                    id=item["id"],
                    title=item["title"],
                    description=item["description"],
                    category=item["category"],
                    post_type=item["post_type"],
                    status=item["status"],
                    author_id=item["author_id"],
                    author_name=item["author_name"],
                    author_avatar=item["author_avatar"],
                    is_verified=is_verified,
                    is_urgent=is_urgent,
                    distance_km=dist_km,
                    distance_meters=dist_meters,
                    community_name=item["community_name"],
                    district_name=item["district_name"],
                    score=score_val,
                    ranking_score=score_val,
                    score_breakdown={
                        "match_score": match_score,
                        "distance_score": dist_score,
                        "urgency_score": urgency_score,
                        "distance_meters": dist_meters,
                        "final_score": score_val,
                        "algorithm_notes": f"55% prox ({dist_meters}m), 25% rel, 20% urgencia",
                    },
                    created_at=item["created_at"],
                )
            )

        self._sort_items(ranked, sort)

        total = len(ranked)
        skip = (page - 1) * page_size
        paginated_items = ranked[skip : skip + page_size]
        total_pages = max(1, math.ceil(total / page_size))

        return PaginatedSolidaritySearch(
            items=paginated_items,
            meta=SearchPaginationMeta(
                total=total,
                page=page,
                limit=page_size,
                total_pages=total_pages,
            ),
            location_applied=SearchLocationMeta(
                latitude=latitude,
                longitude=longitude,
                radius_km=radius_km,
            ),
            sort_applied=sort.value,
        )

    # ------------------------------------------------------------------
    # 4. BÚSQUEDA DE EMERGENCIAS
    # ------------------------------------------------------------------
    async def search_emergencies(
        self,
        query: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius_km: Optional[float] = None,
        severity: Optional[str] = None,
        community_id: Optional[uuid.UUID] = None,
        sort: SearchSort = SearchSort.RECOMMENDED,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedEmergenciesSearch:
        """Búsqueda en emergencias. Prioriza gravedad, cercanía y estado. NUNCA reputación."""
        raw_items = await self.repository.search_emergencies_raw(
            query=query,
            severity=severity,
            community_id=community_id,
        )

        ranked: List[EmergencySearchResult] = []

        SEVERITY_WEIGHTS = {
            "critical": 1.0,
            "high": 0.85,
            "medium": 0.55,
            "low": 0.30,
        }

        STATUS_WEIGHTS = {
            "active": 1.0,
            "reported": 1.0,
            "in_progress": 0.65,
            "resolved": 0.15,
            "closed": 0.10,
        }

        for item in raw_items:
            dist_km, dist_meters, dist_score, within_radius = self._calculate_distance_and_score(
                latitude, longitude, item["latitude"], item["longitude"], radius_km
            )
            if not within_radius:
                continue

            match_score = self._calculate_text_match_score(
                query,
                item["title"],
                item["description"],
                item["emergency_type"],
            )

            if query and query.strip() and match_score < 0.15:
                continue

            sev_val = str(item["severity"]).lower()
            sev_score = SEVERITY_WEIGHTS.get(sev_val, 0.40)

            stat_val = str(item["status"]).lower()
            stat_score = STATUS_WEIGHTS.get(stat_val, 0.40)

            severity_composite = round(sev_score * 0.70 + stat_score * 0.30, 3)

            # Fórmula Emergencias: 50% Gravedad/Estado, 35% Cercanía, 15% Coincidencia
            final_score = (
                0.50 * severity_composite
                + 0.35 * dist_score
                + 0.15 * match_score
            )
            final_score = min(1.0, max(0.0, final_score))
            score_val = round(final_score, 4)

            ranked.append(
                EmergencySearchResult(
                    id=item["id"],
                    title=item["title"],
                    description=item["description"],
                    emergency_type=item["emergency_type"],
                    severity=item["severity"],
                    status=item["status"],
                    reported_by=item["reported_by"],
                    reporter_name=item["reporter_name"],
                    occurred_at=item["occurred_at"],
                    distance_km=dist_km,
                    distance_meters=dist_meters,
                    community_name=item["community_name"],
                    district_name=item["district_name"],
                    score=score_val,
                    ranking_score=score_val,
                    score_breakdown={
                        "severity_score": severity_composite,
                        "distance_score": dist_score,
                        "match_score": match_score,
                        "distance_meters": dist_meters,
                        "final_score": score_val,
                        "algorithm_notes": f"50% gravedad ({item['severity']}), 35% prox ({dist_meters}m), 15% rel",
                    },
                    created_at=item["created_at"],
                )
            )

        # Para emergencias por defecto ordenar por gravedad/score
        if sort == SearchSort.DISTANCE:
            ranked.sort(key=lambda x: (x.distance_meters is None, x.distance_meters or 9999999.0, -x.score))
        else:
            # RECOMMENDED: Críticas activas conservan máxima prioridad, priorizando cercanía dentro de cada nivel
            ranked.sort(
                key=lambda x: (
                    -round(x.score_breakdown.get("severity_score", 0.0) if x.score_breakdown else 0.0, 2),
                    x.distance_meters is None,
                    x.distance_meters or 9999999.0,
                    -x.score,
                )
            )

        total = len(ranked)
        skip = (page - 1) * page_size
        paginated_items = ranked[skip : skip + page_size]
        total_pages = max(1, math.ceil(total / page_size))

        return PaginatedEmergenciesSearch(
            items=paginated_items,
            meta=SearchPaginationMeta(
                total=total,
                page=page,
                limit=page_size,
                total_pages=total_pages,
            ),
            location_applied=SearchLocationMeta(
                latitude=latitude,
                longitude=longitude,
                radius_km=radius_km,
            ),
            sort_applied=sort.value,
        )

    # ------------------------------------------------------------------
    # 5. BÚSQUEDA GLOBAL / CONSOLIDADA (GET /api/v1/search)
    # ------------------------------------------------------------------
    async def search_all(
        self,
        query: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        radius_km: Optional[float] = None,
        community_id: Optional[uuid.UUID] = None,
        sort: SearchSort = SearchSort.RECOMMENDED,
        page: int = 1,
        page_size: int = 20,
    ) -> GlobalSearchResponse:
        """Búsqueda general transversal que combina e intercala servicios, productos, solidaridad y emergencias."""
        # Ejecutar búsquedas en paralelo conceptual en cada módulo
        services_res = await self.search_services(
            query=query,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            community_id=community_id,
            sort=sort,
            page=1,
            page_size=30,
        )

        products_res = await self.search_products(
            query=query,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            community_id=community_id,
            sort=sort,
            page=1,
            page_size=30,
        )

        solidarity_res = await self.search_solidarity(
            query=query,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            community_id=community_id,
            sort=sort,
            page=1,
            page_size=30,
        )

        emergencies_res = await self.search_emergencies(
            query=query,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
            community_id=community_id,
            sort=sort,
            page=1,
            page_size=30,
        )

        unified_list: List[UnifiedSearchResultItem] = []

        # 1. Adaptar Servicios
        for s in services_res.items:
            price_str = f"S/ {s.price_from}" if s.price_from else "A cotizar"
            if s.price_unit:
                price_str += f" /{s.price_unit}"

            unified_list.append(
                UnifiedSearchResultItem(
                    id=s.id,
                    module="services",
                    title=s.title,
                    subtitle=s.provider_name,
                    description=s.description,
                    category=s.category_name,
                    icon=s.category_icon or "🛠️",
                    badge="Verificado" if s.is_verified else ("Nuevo" if s.is_new else None),
                    price_label=price_str,
                    distance_km=s.distance_km,
                    distance_meters=s.distance_meters,
                    location_label=s.district_name or s.community_name,
                    rating=s.rating_avg if s.reviews_count > 0 else None,
                    reviews_count=s.reviews_count,
                    is_new=s.is_new,
                    is_verified=s.is_verified,
                    score=s.score,
                    ranking_score=s.ranking_score,
                    score_breakdown=s.score_breakdown,
                    detail_path=f"/services/{s.id}",
                )
            )

        # 2. Adaptar Productos
        for p in products_res.items:
            unified_list.append(
                UnifiedSearchResultItem(
                    id=p.id,
                    module="products",
                    title=p.name,
                    subtitle=p.business_name,
                    description=p.description,
                    category=p.category_name,
                    icon="🛒",
                    badge="En Stock" if (p.stock is None or p.stock > 0) else "Agotado",
                    price_label=f"S/ {p.price}",
                    distance_km=p.distance_km,
                    distance_meters=p.distance_meters,
                    location_label=p.district_name or p.community_name,
                    rating=p.rating_avg if p.reviews_count > 0 else None,
                    reviews_count=p.reviews_count,
                    is_new=p.is_new,
                    is_verified=p.is_verified,
                    score=p.score,
                    ranking_score=p.ranking_score,
                    score_breakdown=p.score_breakdown,
                    detail_path=f"/products/{p.id}",
                )
            )

        # 3. Adaptar Solidaridad
        for sol in solidarity_res.items:
            type_label = "Necesidad de Ayuda" if sol.is_urgent else "Ofrecimiento Solidario"
            unified_list.append(
                UnifiedSearchResultItem(
                    id=sol.id,
                    module="solidarity",
                    title=sol.title,
                    subtitle=f"{type_label} • {sol.author_name}",
                    description=sol.description,
                    category=sol.category or "Solidaridad",
                    icon="🤝",
                    badge="URGENTE" if sol.is_urgent else "Muro Comunal",
                    price_label="Gratuito",
                    distance_km=sol.distance_km,
                    distance_meters=sol.distance_meters,
                    location_label=sol.district_name or sol.community_name,
                    rating=None,
                    reviews_count=None,
                    is_new=False,
                    is_verified=sol.is_verified,
                    score=sol.score,
                    ranking_score=sol.ranking_score,
                    score_breakdown=sol.score_breakdown,
                    detail_path=f"/solidarity/posts/{sol.id}",
                )
            )

        # 4. Adaptar Emergencias
        for emg in emergencies_res.items:
            unified_list.append(
                UnifiedSearchResultItem(
                    id=emg.id,
                    module="emergencies",
                    title=f"🚨 {emg.title}",
                    subtitle=f"Tipo: {emg.emergency_type} • Estado: {emg.status}",
                    description=emg.description,
                    category=emg.emergency_type,
                    icon="🚨",
                    badge=f"Severidad: {emg.severity.upper()}",
                    price_label="Emergencia Activa",
                    distance_km=emg.distance_km,
                    distance_meters=emg.distance_meters,
                    location_label=emg.district_name or emg.community_name,
                    rating=None,
                    reviews_count=None,
                    is_new=False,
                    is_verified=True,
                    score=emg.score,
                    ranking_score=emg.ranking_score,
                    score_breakdown=emg.score_breakdown,
                    detail_path=f"/emergencies/{emg.id}",
                )
            )

        # Ordenar lista consolidada
        if sort == SearchSort.DISTANCE:
            unified_list.sort(key=lambda x: (x.distance_meters is None, x.distance_meters or 9999999.0, -x.score))
        else:
            # RECOMMENDED: Emergencias críticas activas conservan máxima prioridad;
            # el resto se ordena principalmente por cercanía y score
            def unified_sort_key(item: UnifiedSearchResultItem):
                is_crit_emergency = (
                    item.module == "emergencies"
                    and "CRITICAL" in (item.badge or "").upper()
                )
                return (
                    not is_crit_emergency,  # 0 para emergencias críticas, 1 para el resto
                    -round(item.score, 2),
                    item.distance_meters is None,
                    item.distance_meters or 9999999.0,
                    -item.score,
                )
            unified_list.sort(key=unified_sort_key)

        total = len(unified_list)
        skip = (page - 1) * page_size
        paginated_items = unified_list[skip : skip + page_size]
        total_pages = max(1, math.ceil(total / page_size))

        return GlobalSearchResponse(
            query=query,
            location_applied=SearchLocationMeta(
                latitude=latitude,
                longitude=longitude,
                radius_km=radius_km,
            ),
            sort_applied=sort.value,
            total_results=total,
            page=page,
            limit=page_size,
            total_pages=total_pages,
            items=paginated_items,
            sections_summary={
                "services": services_res.meta.total,
                "products": products_res.meta.total,
                "solidarity": solidarity_res.meta.total,
                "emergencies": emergencies_res.meta.total,
            },
            top_sections={
                "services": [s.model_dump() for s in services_res.items[:3]],
                "products": [p.model_dump() for p in products_res.items[:3]],
                "solidarity": [sol.model_dump() for sol in solidarity_res.items[:3]],
                "emergencies": [emg.model_dump() for emg in emergencies_res.items[:3]],
            },
        )

    def _sort_items(self, items: List[Any], sort: SearchSort) -> None:
        """Aplica la estrategia de ordenamiento sobre los resultados rankeados."""
        if sort == SearchSort.DISTANCE:
            # Estrictamente por distancia ascendente en metros
            items.sort(
                key=lambda x: (
                    x.distance_meters is None,
                    x.distance_meters or 9999999.0,
                    -getattr(x, "score", 0.0),
                )
            )
        elif sort == SearchSort.RELEVANCE:
            # Mayor coincidencia textual, luego proximidad
            items.sort(
                key=lambda x: (
                    -(x.score_breakdown.get("match_score", 0.0) if x.score_breakdown else 0.0),
                    -round(getattr(x, "score", 0.0), 2),
                    x.distance_meters is None,
                    x.distance_meters or 9999999.0,
                )
            )
        else:  # RECOMMENDED
            # Proximidad (55%) + Relevancia (25%) + Reputación (15%) + Experiencia (5%)
            # Si dos vecinos tienen puntuaciones similares, prioriza al más cercano
            items.sort(
                key=lambda x: (
                    -round(getattr(x, "score", 0.0), 2),
                    x.distance_meters is None,
                    x.distance_meters or 9999999.0,
                    -getattr(x, "score", 0.0),
                )
            )
